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

## M2 - Logs
- `ios_toolkit/logs.py` erweitert: Streaming via `idevicesyslog` mit Regex-Filter, optionaler Speicherung, Dauerbegrenzung und Logging.
- Crashlog-Export umgesetzt (`export_crashlogs`) mit `idevicecrashreport`, Limitierung und JSON-Rueckgabe.
- Neues CLI-Kommando `logs-crash` fuer Crash-Exports (`ios_toolkit/cli.py`).
- Neue Tests (`tests/test_logs.py`) mocken Tools und pruefen Filter/Export-Logik.
- Build-System (`pyproject.toml`) ergaenzt, damit nur `ios_toolkit` installiert wird, plus erweiterte `.gitignore`.

### Tests
- `py -m ruff check .`
- `py -m pytest -q`

### Beispielausgaben
- `py -m ios_toolkit.cli logs --duration 2 --save logs\\syslog.log`
- `py -m ios_toolkit.cli logs-crash --out crash_exports --limit 5 --json`
 
## M3 - Recovery/DFU
- `ios_toolkit/recovery.py` implementiert: enter (idevicediagnostics), status (irecovery -q), kickout (irecovery -n) mit Logging und robustem Parser.
- CLI `recovery status` setzt Exit-Codes (0=ok, 1=unknown/Fehler, 2=Tool fehlt) und gibt Fehlerhinweise aus.
- Neue Tests (`tests/test_recovery.py`) decken Parser, Tool-Missing und Erfolgs-/Fehlerpfade ab.

### Tests
- `py -m ruff check .`
- `py -m pytest -q`

### Beispielausgaben
- `py -m ios_toolkit.cli recovery status --json`
- `py -m ios_toolkit.cli recovery enter --udid <UDID>`
- `py -m ios_toolkit.cli recovery kickout --udid <UDID>`
