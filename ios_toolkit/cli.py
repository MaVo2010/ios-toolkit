# Windows CLI fuer iOS-Geraete
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__, device, logs, recovery, restore, models, utils

app = typer.Typer(help="Windows CLI-Tool: iOS-Geraete erkennen, Logs, Recovery/DFU, Flashen")
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
def list_cmd(json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe")):
    try:
        devices = device.list_devices()
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
        data = device.diag_usb()
        if json_out:
            echo_json(data)
        else:
            for k, v in data.items():
                typer.echo(f"{k}: {v}")
    else:
        typer.echo("Unbekannte Diagnose. Nutze: usb")
        raise typer.Exit(2)

def main():
    app()

if __name__ == "__main__":
    main()
