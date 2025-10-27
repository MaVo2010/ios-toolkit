# PROGRESS

## M0 - Bootstrap
- Virtuelle Umgebung unter `.venv` angelegt und `pip` aktualisiert.
- Projektabhaengigkeiten aus `requirements.txt` installiert, zusaetzlich `pytest` ergaenzt.
- `pytest -q` ausgefuehrt (gruen).
- `py -m ios_toolkit.cli --help` geprueft.

## M1 - Geraeteerkennung & Info
- `ios_toolkit/device.py` um robuste Discovery-Logik erweitert (pymobiledevice3 mit Fallback auf `idevice_id`/`ideviceinfo`), inklusive Fehlerklassen und JSON-Normalisierung.
- CLI-Befehle `list` und `info` aktualisiert: konsistente JSON-Ausgabe (`--json`), klare Exit-Codes, Fehlerbehandlung.
- Unit-Tests fuer Parser/CLI ergaenzt (`tests/test_device.py`, `tests/test_cli.py`).

## Schema-Logging & CI Erweiterung
- Pydantic-Modelle fuer Geraete und Restore-Resultate hinzugefuegt (`ios_toolkit/models.py`) und CLI/Device/Restore-Endpunkte darauf umgestellt.
- Globales Logging mit Rotations-Handler und UDID-Redaktion (`ios_toolkit/utils.py`), CLI-Callback stellt `--log-dir` und `--verbose` bereit.
- Restore-Flow liefert jetzt `models.RestoreResult` mit Zeitstempeln (`ios_toolkit/restore.py`).
- Dev-/CI-Rahmen ergaenzt: `.editorconfig`, `.gitattributes`, `requirements-dev.txt`, GitHub Actions Workflow (`.github/workflows/ci.yml`), PR-Template.
- Ruff-Konfiguration in `pyproject.toml`, Lint-Fehler in bestehenden Modulen (Logs/Recovery) behoben.

### Tests
- `pytest -q`
- `.venv\Scripts\ruff.exe check .`

### Beispielausgaben
- `py -m ios_toolkit.cli list --json`  
  ```json
  [
    {
      "udid": "0000...",
      "product_type": "iPhone12,8",
      "product_version": "26.0.1",
      "device_name": "iPhone",
      "mode": "normal",
      "connection": "usb"
    }
  ]
  ```
- `py -m ios_toolkit.cli info --json`  
  ```json
  {
    "udid": "0000...",
    "product_type": "iPhone12,8",
    "product_version": "26.0.1",
    "device_name": "iPhone",
    "mode": "normal",
    "connection": "usb",
    "details": { "...": "..." }
  }
  ```

### Bekannte Punkte
- Fehlende libimobiledevice-Binaries werden per Fehlerklassen gemeldet; pymobiledevice3 deckt Discovery/Info aktuell ab.
- CI-Workflow laeuft nur auf Windows-Runnern; weitere Plattformen optional.

## M4 - Restore/Flash
- `ios_toolkit/restore.py` um Preflight-Checks, Dry-Run und Timeout erweitert; Schritte/Progress werden aus dem idevicerestore-Stream erkannt.
- CLI `flash` bietet jetzt `--preflight-only`, `--dry-run`, `--timeout` sowie stabile Exit-Codes (0 Erfolg, 2 Validierungsfehler, 1 sonstige Fehler).
- Neue Tests (`tests/test_restore.py`) decken Tool-Fehlen, IPSW-Validierung, Preflight, Dry-Run, Erfolg und Timeout ab.
- `.gitignore` enth�lt tempor�re Testverzeichnisse.

### Tests
- `py -m ruff check .`
- `py -m pytest -q`

### Beispielausgaben
- `py -m ios_toolkit.cli flash --preflight-only --ipsw C:\Firmware\iPhone_123.ipsw --json`
- `py -m ios_toolkit.cli flash --dry-run --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw`
- `py -m ios_toolkit.cli flash --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw --timeout 3600 --json`
\n## M5 - IPSW Management
- ios_toolkit/ipsw.py hinzugefuegt: lokale Validierung (SHA1, ZIP-Test, Manifest) und Produkt-Typ-Auslese.
- Neues CLI-Kommando ipsw verify prueft Dateien und liefert Exit-Code 2 bei Validierungsfehlern.
- Restore-Preflight nutzt nun validate_ipsw(); Checks enthalten SHA1/Manifest-Details.
\n### Tests
- `py -m ruff check .`
- `py -m pytest -q`
\n### Beispielausgaben
- `py -m ios_toolkit.cli ipsw verify --file C:\Firmware\iPhone_123.ipsw --json`
- `py -m ios_toolkit.cli flash --latest --ipsw C:\Firmware\iPhone_123.ipsw --json`
