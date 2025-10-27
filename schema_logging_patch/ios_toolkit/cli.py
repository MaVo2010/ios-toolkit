# Windows CLI für iOS-Geräte
from __future__ import annotations
import json
from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from . import device, logs, recovery, restore, __version__
from . import models, utils

app = typer.Typer(help="Windows CLI-Tool: iOS-Geräte erkennen, Logs, Recovery/DFU, Flashen")
console = Console()

def echo_json(data):
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))

@app.callback()
def _main(
    ctx: typer.Context,
    log_dir: Path = typer.Option(Path("logs"), "--log-dir", help="Log-Verzeichnis"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Mehr Details im Log"),
):
    utils.configure_logging(log_dir=log_dir, verbose=verbose)

@app.command()
def version(json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe")):
    if json_out:
        echo_json({"version": __version__})
    else:
        typer.echo(f"ios-toolkit v{__version__}")

@app.command(name="list")
def list_cmd(json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe")):
    devices = device.list_devices()  # -> list[models.Device]
    if json_out:
        echo_json([d.model_dump() for d in devices])
        raise typer.Exit(0)
    if not devices:
        typer.echo("Keine Geräte erkannt.")
        raise typer.Exit(1)
    table = Table(title="Verbundene iOS-Geräte")
    table.add_column("UDID")
    table.add_column("Produkt")
    table.add_column("iOS")
    table.add_column("Name")
    table.add_column("Modus")
    table.add_column("Conn")
    for d in devices:
        table.add_row(
            d.udid or "?",
            d.product_type or "?",
            d.product_version or "?",
            d.device_name or "?",
            d.mode or "unknown",
            d.connection or "unknown",
        )
    console.print(table)

@app.command()
def info(
    udid: str = typer.Option(None, "--udid", help="UDID wählen, wenn mehrere"),
    json_out: bool = typer.Option(False, "--json", help="JSON-Ausgabe"),
):
    data = device.get_info(udid=udid)  # -> models.Device | None
    if data is None:
        typer.echo("Kein Gerät gefunden oder UDID ungültig.", err=True)
        raise typer.Exit(1)
    if json_out:
        echo_json(data.model_dump())
    else:
        for k, v in data.model_dump().items():
            typer.echo(f"{k}: {v}")

@app.command(name="logs")
def logs_cmd(
    udid: str = typer.Option(None, "--udid"),
    save: str = typer.Option(None, "--save", help="Dateipfad zum Mitschreiben"),
    filter_expr: str = typer.Option(None, "--filter", help="Regex-Filter"),
    duration: int = typer.Option(None, "--duration", help="Sekunden, optional"),
):
    rc = logs.stream_syslog(udid=udid, save_path=save, filter_expr=filter_expr, duration=duration)
    raise typer.Exit(rc)

@app.command(name="recovery")
def recovery_cmd(
    action: str = typer.Argument(..., help="enter | status | kickout"),
    udid: str = typer.Option(None, "--udid"),
    json_out: bool = typer.Option(False, "--json"),
):
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
    udid: str = typer.Option(None, "--udid"),
    ipsw: str = typer.Option(None, "--ipsw", help="Pfad zur IPSW-Datei"),
    latest: bool = typer.Option(False, "--latest", help="Neueste Firmware (später)"),
    wipe: bool = typer.Option(True, "--wipe", help="Werkseinstellung"),
    keep_logs: bool = typer.Option(False, "--keep-logs"),
    json_out: bool = typer.Option(False, "--json"),
):
    result = restore.restore(udid=udid, ipsw_path=ipsw, latest=latest, wipe=wipe, keep_logs=keep_logs)
    if json_out:
        echo_json(result.model_dump())
    else:
        typer.echo(f"Status: {result.status} | Log: {result.logfile}")
    raise typer.Exit(0 if result.status == "success" else 1)

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
