# Windows CLI fuer iOS-Geraete
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ios_toolkit import __version__, device, dfu, ipsw, logs, models, recovery, restore, utils

app = typer.Typer(help="Windows CLI-Tool: iOS-Geraete erkennen, Logs, Recovery/DFU, Flashen")
ipsw_app = typer.Typer(help="IPSW Utilities")
dfu_app = typer.Typer(help="DFU-Assistent")
app.add_typer(ipsw_app, name="ipsw")
app.add_typer(dfu_app, name="dfu")
console = Console()


@app.callback()
def _main_callback(
    ctx: typer.Context,
    log_dir: Path = typer.Option(Path("logs"), "--log-dir", help="Directory for log files"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    utils.configure_logging(log_dir=log_dir, verbose=verbose)
    ctx.ensure_object(dict)
    ctx.obj["log_dir"] = str(log_dir) if log_dir else None

def echo_json(data):
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@ipsw_app.command("verify")
def ipsw_verify_cmd(
    file: str = typer.Option(..., "--file", help="Pfad zur IPSW-Datei"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    result = ipsw.validate_ipsw(file)
    if json_out:
        echo_json(result)
    else:
        if result["ok"]:
            typer.echo(f"IPSW OK | size={result['size']} | sha1={result['sha1']}")
            if result.get("has_manifest"):
                product = ipsw.product_from_manifest(file)
                if product:
                    typer.echo(f"Product: {product}")
        else:
            typer.echo(f"Validation failed: {result.get('error', 'unknown error')}", err=True)
    raise typer.Exit(0 if result["ok"] else 2)


@dfu_app.command("guide")
def dfu_guide_cmd(
    ctx: typer.Context,
    udid: str = typer.Option(None, "--udid", help="UDID des Geraets (optional)"),
    model: str = typer.Option(None, "--model", help="Produkt-Typ, z. B. iPhone12,8"),
    countdown: bool = typer.Option(False, "--countdown/--no-countdown", help="Countdown je Schritt anzeigen"),
    sound: bool = typer.Option(False, "--sound/--no-sound", help="Akustische Signale verwenden"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    product_type = model
    if udid and not product_type:
        try:
            info = device.get_info(udid=udid)
            product_type = info.product_type
        except device.DeviceError as exc:
            typer.echo(f"Konnte Geraeteinfo nicht abrufen: {exc}", err=True)
            raise typer.Exit(1)

    if not product_type:
        typer.echo("Bitte --model angeben oder --udid verwenden.", err=True)
        raise typer.Exit(2)

    try:
        if json_out:
            instructions = dfu.get_instructions(product_type)
            echo_json(instructions)
        else:
            dfu.guide(product_type=product_type, udid=udid, countdown=countdown, sound=sound)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    except Exception as exc:  # pragma: no cover - defensive
        log = utils.get_logger(__name__)
        log.error("DFU-Assistent fehlgeschlagen: %s", exc)
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1)


def _emit_device_error(exc: device.DeviceError, json_out: bool) -> None:
    if json_out:
        payload = {"error": str(exc)}
        if exc.payload:
            payload.update(exc.payload)
        echo_json(payload)
    else:
        typer.echo(str(exc), err=True)
        if exc.payload.get("missing_tools"):
            missing = ", ".join(exc.payload["missing_tools"])
            typer.echo(f"Fehlende Tools: {missing}", err=True)
    raise typer.Exit(exc.exit_code)


def _filter_device_summary(entry: models.Device) -> dict:
    keys = ["udid", "product_type", "product_version", "device_name", "mode", "connection"]
    data = entry.model_dump(mode="python", exclude={"details"})
    return {key: data.get(key) for key in keys}

@app.command()
def version(json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe")):
    if json_out:
        echo_json({"version": __version__})
    else:
        typer.echo(f"ios-toolkit v{__version__}")

@app.command(name="list")
def list_cmd(
    json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe"),
    include_dfu: bool = typer.Option(False, "--include-dfu", help="DFU-Geraete via irecovery einbeziehen"),
):
    try:
        devices = device.list_devices(include_dfu=include_dfu)
    except device.DeviceError as exc:
        _emit_device_error(exc, json_out)
        return

    if json_out:
        echo_json([d.model_dump(mode="json", exclude={"details"}) for d in devices])
        raise typer.Exit(0)

    if not devices:
        typer.echo("Keine Geraete erkannt.")
        raise typer.Exit(0)

    table = Table(title="Verbundene iOS-Geraete")
    table.add_column("UDID")
    table.add_column("Produkt")
    table.add_column("iOS")
    table.add_column("Name")
    table.add_column("Modus")
    table.add_column("Verbindung")
    for d in devices:
        summary = _filter_device_summary(d)
        table.add_row(
            summary.get("udid") or "?",
            summary.get("product_type") or "?",
            summary.get("product_version") or "?",
            summary.get("device_name") or "?",
            summary.get("mode") or "unknown",
            summary.get("connection") or "unknown",
        )
    console.print(table)

@app.command()
def info(udid: str = typer.Option(None, "--udid", help="UDID waehlen, wenn mehrere"),
         json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe")):
    try:
        data = device.get_info(udid=udid)
    except device.DeviceError as exc:
        _emit_device_error(exc, json_out)
        return

    if json_out:
        echo_json(data.model_dump(mode="json"))
    else:
        summary = _filter_device_summary(data)
        for key, value in summary.items():
            typer.echo(f"{key}: {value}")
        if data.details:
            typer.echo("details:")
            for key, value in sorted(data.details.items()):
                typer.echo(f"  {key}: {value}")

@app.command(name="logs")
def logs_cmd(udid: str = typer.Option(None, "--udid"),
             save: str = typer.Option(None, "--save", help="Dateipfad zum Mitschreiben"),
             filter_expr: str = typer.Option(None, "--filter", help="Regex-Filter"),
             duration: int = typer.Option(None, "--duration", help="Sekunden, optional")):
    rc = logs.stream_syslog(udid=udid, save_path=save, filter_expr=filter_expr, duration=duration)
    raise typer.Exit(rc)

@app.command(name="recovery")
def recovery_cmd(action: str = typer.Argument(..., help="enter | status | kickout"),
                 udid: str = typer.Option(None, "--udid"),
                 json_out: bool = typer.Option(False, "--json")):
    action = action.lower()
    if action == "enter":
        ok = recovery.enter(udid=udid)
        raise typer.Exit(0 if ok else 1)
    elif action == "status":
        data = recovery.status(udid=udid)
        if json_out:
            echo_json(data)
        else:
            typer.echo(f"Modus: {data.get('mode','unknown')}")
    elif action == "kickout":
        ok = recovery.kickout(udid=udid)
        raise typer.Exit(0 if ok else 1)
    else:
        typer.echo("Unbekannte Aktion. Nutze: enter | status | kickout", err=True)
        raise typer.Exit(2)

@app.command()
def flash(
    ctx: typer.Context,
    udid: str = typer.Option(None, "--udid"),
    ipsw: str = typer.Option(None, "--ipsw", help="Pfad zur IPSW-Datei"),
    latest: bool = typer.Option(False, "--latest", help="Neueste Firmware (spaeter)"),
    wipe: bool = typer.Option(True, "--wipe", help="Werkseinstellung"),
    keep_logs: bool = typer.Option(False, "--keep-logs"),
    preflight_only: bool = typer.Option(False, "--preflight-only", help="Nur Vorabpruefungen ausfuehren"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Befehl anzeigen, aber nicht ausfuehren"),
    timeout: Optional[int] = typer.Option(None, "--timeout", help="Timeout in Sekunden fuer idevicerestore"),
    json_out: bool = typer.Option(False, "--json"),
):
    restore_kwargs = dict(
        udid=udid,
        ipsw_path=ipsw,
        latest=latest,
        wipe=wipe,
        keep_logs=keep_logs,
        preflight_only=preflight_only,
        dry_run=dry_run,
        timeout_sec=timeout,
        log_dir=ctx.obj.get("log_dir") if ctx.obj else None,
    )
    result = restore.restore(**restore_kwargs)

    if json_out:
        echo_json(result.model_dump(mode="json"))
    else:
        typer.echo(f"Status: {result.status}")
        typer.echo(f"Log: {result.logfile}")
        for step in result.steps:
            detail = f" ({step.detail})" if step.detail else ""
            typer.echo(f"- {step.name}: {'ok' if step.ok else 'fail'}{detail}")

    exit_code = 0
    if result.status != "success":
        exit_code = 2 if restore.is_validation_failure(result) else 1
    raise typer.Exit(exit_code)

@app.command()
def diag(sub: str = typer.Argument(..., help="usb"), json_out: bool = typer.Option(False, "--json")):
    if sub == "usb":
        try:
            data = device.diag_usb()
        except Exception as exc:  # pragma: no cover - defensive fallback
            typer.echo(f"Diagnose fehlgeschlagen: {exc}", err=True)
            raise typer.Exit(1)

        if json_out:
            echo_json(data)
            raise typer.Exit(0)

        amds = data.get("amds", {})
        tools = data.get("tools", {})
        usb_info = data.get("usb", {})
        host = data.get("host", {})
        hints = data.get("hints") or []

        status_text = amds.get("status") or "unbekannt"
        running_text = "laufend" if amds.get("running") else "gestoppt"
        typer.echo(f"AMDS: {status_text} ({running_text})")

        found_tools = [
            f"{entry['name']}{' (' + entry['version'] + ')' if entry.get('version') else ''}"
            for entry in tools.get("entries", [])
            if entry.get("found")
        ]
        typer.echo("Gefundene Tools: " + (", ".join(found_tools) if found_tools else "keine"))

        missing = tools.get("missing") or []
        if missing:
            typer.echo("Fehlende Tools: " + ", ".join(missing))

        usb_parts = [
            f"DFU={'ja' if usb_info.get('dfu_detected') else 'nein'}",
            f"Recovery={'ja' if usb_info.get('recovery_detected') else 'nein'}",
            f"irecovery={'verfuegbar' if usb_info.get('irecovery_available') else 'nicht vorhanden'}",
        ]
        typer.echo("USB: " + ", ".join(usb_parts))

        disk_free = host.get("disk_free_gb")
        disk_text = f"{disk_free} GB frei" if disk_free is not None else "unbekannt"
        pnp_text = "ja" if host.get("apple_pnp_present") else "nein"
        typer.echo(f"Host: Speicher {disk_text}, Apple-PnP: {pnp_text}")

        if hints:
            typer.echo("Hinweise:")
            for hint in hints[:3]:
                typer.echo(f"- {hint}")

        raise typer.Exit(0)
    else:
        typer.echo("Unbekannte Diagnose. Nutze: usb")
        raise typer.Exit(2)

def main():
    app()

if __name__ == "__main__":
    main()

