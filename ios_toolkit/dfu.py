from __future__ import annotations

import time
from typing import Dict, List, Optional

import typer

from . import device, utils

log = utils.get_logger(__name__)

# DFU instructions mapping: product type -> dict with friendly name and steps.
_DFU_MAP: Dict[str, Dict[str, object]] = {
    "iPhone12,8": {
        "model": "iPhone SE (2./3. Generation)",
        "steps": [
            {"order": 1, "description": "Verbinde das Geraet mit dem PC und schalte es aus."},
            {
                "order": 2,
                "description": "Halte Side Button und Volume Down gleichzeitig gedrueckt.",
                "duration": 10,
            },
            {
                "order": 3,
                "description": "Halte Volume Down weiter gedrueckt und lasse den Side Button los.",
                "duration": 5,
            },
            {
                "order": 4,
                "description": (
                    "Halte Volume Down bis der Bildschirm dunkel bleibt."
                    " Windows meldet anschliessend ein neues USB-Geraet."
                ),
            },
        ],
    },
    "iPad11,7": {
        "model": "iPad (8. Generation, Home Button)",
        "steps": [
            {"order": 1, "description": "Verbinde das Geraet mit dem PC und schalte es aus."},
            {
                "order": 2,
                "description": "Halte Top Button und Home Button gleichzeitig gedrueckt.",
                "duration": 10,
            },
            {
                "order": 3,
                "description": "Halte Home weiter gedrueckt und lasse den Top Button los.",
                "duration": 5,
            },
            {
                "order": 4,
                "description": (
                    "Halte Home bis der Bildschirm dunkel bleibt."
                    " Windows meldet anschliessend ein neues USB-Geraet."
                ),
            },
        ],
    },
}


def _resolve_model(product_type: str) -> Optional[Dict[str, object]]:
    if product_type in _DFU_MAP:
        return _DFU_MAP[product_type]
    # Allow partial matching on prefix (e.g. iPhone12,*)
    for key, value in _DFU_MAP.items():
        if product_type.startswith(key.split(",")[0]):
            return value
    return None


def get_instructions(product_type: str) -> Dict[str, object]:
    """
    Return DFU instructions metadata for the given product type.
    Raises ValueError for unknown models.
    """
    mapping = _resolve_model(product_type)
    if not mapping:
        raise ValueError(f"Keine DFU-Anleitung fuer {product_type}")

    steps: List[dict] = [dict(step) for step in mapping["steps"]]  # type: ignore[index]
    timings = [step["duration"] for step in steps if "duration" in step]
    return {
        "product_type": product_type,
        "model": mapping.get("model"),
        "steps": steps,
        "timings": timings,
        "total_duration": sum(timings),
    }


def _countdown(duration: int, message: str, sound: bool = False) -> None:
    try:
        if sound:
            import winsound  # type: ignore

            winsound.Beep(750, 200)
    except Exception:  # pragma: no cover - winsound possibly unavailable
        log.debug("winsound not available for countdown start")

    for remaining in range(duration, 0, -1):
        typer.echo(f"{message} ({remaining}s)")
        time.sleep(1)


def guide(
    *,
    product_type: Optional[str] = None,
    udid: Optional[str] = None,
    countdown: bool = True,
    sound: bool = False,
) -> Dict[str, object]:
    """
    Run the interactive DFU guide. Returns instruction metadata.
    """
    if udid:
        try:
            info = device.get_info(udid=udid)
            product_type = info.product_type or product_type
        except device.DeviceError as exc:
            log.warning("Konnte Gerateinformationen nicht abrufen: %s", exc)

    if not product_type:
        raise ValueError("Produkt-Typ konnte nicht bestimmt werden. Bitte --model angeben.")

    instructions = get_instructions(product_type)
    typer.echo(f"DFU-Assistent fuer {instructions.get('model') or product_type}")
    for step in instructions["steps"]:
        desc = step["description"]
        duration = step.get("duration")
        if countdown and duration:
            _countdown(int(duration), desc, sound=sound)
        else:
            typer.echo(desc)

    typer.echo("Sobald das Geraet in DFU erkannt wird, pruefe mit `ios-toolkit recovery status --json`.")
    return instructions
