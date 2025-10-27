# Agentisches Entwicklungs-Playbook: Windows CLI-Tool für iOS-Geräte (Erkennen, Logs, Recovery/DFU, Flashen)

**Stand:** 2025-10-27 18:27  
**Zielgruppe:** Entwickler:innen, DevOps, und KI-Agenten (z. B. Codex)  
**Plattform:** Windows (Intel/AMD x64)  
**Kurzfassung:** Dieses Dokument liefert eine vollständige, agentenfreundliche Spezifikation mit Schritt-für-Schritt-Anweisungen, Akzeptanzkriterien und einem Start-Repository (CLI-Skeleton), damit ein Agent das Tool eigenständig entwickeln, testen und paketieren kann.

---

## 1) Executive Summary

Wir bauen ein Windows-basiertes CLI-Tool (Python), das iPhones/iPads
- **erkennt** (UDID, Modell, iOS-Version),
- **Logs** ausliest (Syslog/Crashlogs/Restore-Logs),
- **Recovery/DFU** unterstützt (enter/erkennen/kickout),
- optional **Firmware wiederherstellen (flashen)** kann (über bestehende Tools/APIs).

**Prinzip:** So viel wie möglich auf bestehende, bewährte Werkzeuge stützen (z. B. libimobiledevice-Tools wie `idevice_id`, `ideviceinfo`, `idevicesyslog`, `irecovery`, `idevicerestore` sowie die Python-Bibliothek `pymobiledevice3`). Das CLI liefert klare, maschinenlesbare Ausgaben (`--json`) und persistente Logs für forensische Analysen.

---

## 2) Scope & Non-Goals

### Im Scope
- Windows-CLI mit sauberem UX (Typer/Click).
- Geräteerkennung per USB (usbmux) und Basisinfos.
- Live-Log-Streaming (Syslog) + optionaler Export/Filter.
- Recovery/DFU: in Recovery versetzen, Modus erkennen, „kickout“ (Neustart).
- Flash (Restore) via `idevicerestore` **oder** `pymobiledevice3`-Restore-API.
- Stabiles Logging, Exit-Codes, JSON-Ausgaben → für Automatisierung/KI.

### Nicht im Scope (v1)
- iCloud-Lock-Umgehung, SIM-/Carrier-Unlocks oder sonstige Umgehungen von Schutzmechanismen.
- macOS-Unterstützung (Windows only v1).
- Apple-internen/undokumentierten Low-Level-Exploit-Support.
- MDM-Enrollment/DEP-Workflows (können später ergänzt werden).

**Compliance-Hinweis:** Nur offizielle IPSWs verwenden, keine Sicherheitsmechanismen umgehen. Unternehmensrichtlinien beachten.

---

## 3) Umgebungs- und Installations-Checkliste (Windows)

1. **Adminrechte** für Treiberinstallation, wo nötig.
2. **Apple Mobile Device Support** (durch iTunes oder die „Apple-Geräte“-Windows-App).  
   - Der Dienst „Apple Mobile Device Service“ muss laufen.
3. **Python 3.10–3.12** installieren (64‑bit).
4. **Paketabhängigkeiten** per `pip`:
   - `typer[all]`, `rich`, `pydantic`, `pyyaml`, `psutil`, `colorama` (UX/CLI).
   - `pymobiledevice3` (Geräte-API, DFU/Restore-Unterstützung).
5. **libimobiledevice-Tools (Windows-Binaries)** optional installieren und in `PATH` aufnehmen:  
   - `idevice_id`, `ideviceinfo`, `idevicesyslog`, `irecovery`, `idevicerestore`.
6. **libusb** (falls DFU/Restore benötigt) installieren. Ggf. mit **Zadig** passenden Treiber binden.
7. **Firewall/Proxy-Policy** prüfen (für IPSW-Downloads, wenn implementiert).
8. **Testgerät** (z. B. iPhone SE 2./3. Gen, iPad 2020) + USB‑Kabel bereitstellen.

---

## 4) Architekturübersicht

**Sprache:** Python  
**CLI-Framework:** Typer (freundlich für Menschen & Maschinen)  
**Module (Beispiel):**
- `device.py` → Discovery, Info, Verbindungs-Checks.
- `logs.py` → Syslog-Streaming, Crashlogs sammeln, Restore-Log persistieren.
- `recovery.py` → enter_recovery, DFU/Recovery-Erkennung, kickout.
- `restore.py` → Flash/Restore (via `idevicerestore` oder PyMobileDevice-API).
- `utils.py` → Subprocess-Wrapper, Pfad-/Treiber-Checks, JSON/Schema.
- `cli.py` → Top-Level Typer-Befehle, gemeinsame Optionen, Exception-Handling.

**Design-Prinzipien:**
- Dünne Schicht über bewährten Tools.
- Alle Befehle liefern klare **Exit-Codes** (0=OK, >0 Fehler).
- `--json`-Flag liefert **Machine-Readable**-Ausgaben (Schemas unten).
- Persistente Logfiles mit Zeitstempeln pro Lauf.

---

## 5) CLI-Spezifikation (v1)

### 5.1 Commands

- `ios-toolkit list [--json]`  
  Listet angeschlossene Geräte.  
  **JSON-Schema (array):**  
  ```json
  [{"udid": "str", "product_type": "str", "product_version": "str", "device_name": "str"}]
  ```

- `ios-toolkit info [--udid <id>] [--json]`  
  Zeigt Detailinfos; bei mehreren Geräten ist `--udid` nötig.

- `ios-toolkit logs [--udid <id>] [--save path] [--filter <regex>] [--duration <sec>]`  
  Streamt Syslog (stdout) und speichert optional. Abbruch mit Ctrl+C oder `--duration`.

- `ios-toolkit recovery enter [--udid <id>]`  
  Versetzt das Gerät in den Recovery-Modus (falls möglich).

- `ios-toolkit recovery status [--udid <id>] [--json]`  
  Erkennt, ob **normal / recovery / dfu**.

- `ios-toolkit recovery kickout [--udid <id>]`  
  Startet das Gerät aus Recovery/DFU neu.

- `ios-toolkit flash [--udid <id>] (--ipsw PATH | --latest) [--wipe] [--keep-logs]`  
  Führt einen Restore durch. `--wipe` ist Standard (Werkseinstellung).  
  `--latest` (optional): neueste passende Firmware (später via API).  
  **Ergebnis-JSON:**  
  ```json
  {"status":"success|failure","steps":[{"name":"str","ok":true}], "logfile":"path"}
  ```

- `ios-toolkit diag usb`  
  Prüft Treiber, laufende Dienste, PATH, verfügbare Tools (iTunes/AMDS, libimobiledevice, libusb).

### 5.2 Optionen / Defaults
- Global: `--verbose/-v`, `--json`, `--log-dir <path>`
- Standard-Timeouts: Discover 5s, Subprozess 300s, Restore 3600s (konfigurierbar).

---

## 6) Schritt-für-Schritt Roadmap (für Agenten)

### Meilenstein 0 – Repo & Bootstrap
1. Repo-Gerüst anlegen (siehe Scaffold).
2. `pyproject.toml` / `requirements.txt` erstellen.
3. `cli.py` mit Typer-Basis + Befehl `version`.
4. CI (lokal) mit `pytest -q` + Lint (`ruff` optional).

**Akzeptanz:** `python -m ios_toolkit.cli --help` funktioniert; `pytest` grün.

### Meilenstein 1 – Geräteerkennung & Info
1. `device.list_devices()` implementieren:  
   - Primär: `pymobiledevice3`-usbmux Discovery.  
   - Fallback: `idevice_id -l` parsen (wenn vorhanden).
2. `device.get_info(udid)` implementieren:  
   - `pymobiledevice3` oder `ideviceinfo` (Fallback).
3. `ios-toolkit list` und `ios-toolkit info` verdrahten; `--json`-Ausgabe testen.

**Akzeptanz:** Gerät wird erkannt; Detailinfos sind konsistent.

### Meilenstein 2 – Logs
1. `logs.stream_syslog(udid, filter, duration, save_path)` implementieren:  
   - Primär: `pymobiledevice3` Syslog; Fallback: `idevicesyslog` Subprozess.  
   - Save-to-File (rotierende Logs `logs/{udid}/syslog-YYYYmmdd-HHMMSS.log`).
2. `ios-toolkit logs` implementieren; Tests mit echtem Gerät.

**Akzeptanz:** Live-Log sichtbar, Filter greift, Datei wird geschrieben.

### Meilenstein 3 – Recovery/DFU
1. `recovery.enter(udid)` (Lockdown/Diagnostics) – wenn möglich.  
2. `recovery.status(udid)` – USB-Produkt-IDs erkennen oder via Tools (`irecovery -q`).  
3. `recovery.kickout(udid)` – `irecovery -n` oder API.

**Akzeptanz:** Moduswechsel erkennbar, Kickout funktioniert (wo möglich).

### Meilenstein 4 – Flash/Restore
1. `restore.restore(udid, ipsw_path, wipe=True)` implementieren:  
   - Variante A: Subprozess `idevicerestore -w <IPSW>` (Logs abgreifen).  
   - Variante B: `pymobiledevice3`-Restore (später).  
2. Fortschritt und Fehlerparsing in JSON Ergebnis.
3. `--latest` (optional): IPSW-Auswahl vorbereiten (API-Integration später).

**Akzeptanz:** Erfolgreicher Restore auf Testgerät; Fehlerfälle liefern saubere Meldungen + Logfile.

### Meilenstein 5 – Packaging & DX
1. `pyinstaller`-Build zu `ios-toolkit.exe`.  
2. Startskript `.cmd` + README mit Admin-/Treiber-Hinweisen.  
3. Beispiel-Automationsskripte (PowerShell) für IT-Teams.

**Akzeptanz:** Einzelne EXE, die auf frischem Windows mit iTunes-Treibern läuft.

---

## 7) Fehlerbehandlung & Troubleshooting-Playbooks

- **Kein Gerät erkannt:**  
  - Prüfe AMDS-Dienst, USB-Kabel/Port, Treiber, anderes Kabel/Port/PC.  
  - `ios-toolkit diag usb` ausführen und Resultat befolgen.
- **Beim Flash bricht ab (Reboot hängt):**  
  - `recovery status` prüfen; ggf. `recovery kickout`.  
  - Syslog/Restore-Log analysieren (APFS/NAND Hinweise).  
  - Anderes Kabel/Port; USB 2.0 Hub (manchmal stabiler); Virenscanner temporär deaktivieren (Policy!).
- **DFU nicht erreichbar:**  
  - Manuelle Tastenkombination nach Modell; Countdown-Anleitung ausgeben.  
  - Prüfe libusb-Bindung (Zadig), wenn Advanced DFU-Funktionen nötig.
- **Tools fehlen:**  
  - `diag usb` meldet, was im PATH fehlt und wie zu beheben.

Alle Fehlerpfade müssen **nicht-0 Exit-Codes** und eine **präzise Abschlussmeldung** liefern, inkl. Pfad zum Logfile.

---

## 8) Observability & Logging

- Pro Lauf ein Session-Log: `logs/session-YYYYmmdd-HHMMSS.log` (+ pro Gerät Unterordner).
- CLI-Option `--log-dir` überschreibt Standardort.
- Konsolen-Output stets „kurz & klar“; ausführliche Details im Logfile.
- Bei `--json` werden Status/Ergebnisse als JSON auf stdout ausgegeben (Logs weiterhin in Datei).

---

## 9) Sicherheit, Compliance, Policy

- Nur offizielle Firmware (IPSW). Keine Bypass-/Exploit-Funktionalität.  
- Respektiere Unternehmensrichtlinien (USB-Device-Policy, Treiber-Install).  
- Logs können sensible Daten enthalten → sichere Ablage, Retention-Policy (z. B. 30 Tage), optional Redaction.

---

## 10) Testplan

- **Unit-Tests:** Parsing, JSON-Schemas, Subprozess-Wrapper (mit Mocks).  
- **Integrationstests (manuell):** Mit Testgerät alle Befehle durchspielen.  
- **Regression:** Wiederholte Restore-Läufe, unterschiedliche Kabel/Ports.  
- **Smoke-Test-Skripte:** `scripts/smoke_windows.ps1` (List→Info→Logs→Recovery→Kickout).

**Abnahme für v1:**  
- `list/info/logs/recovery/flash/diag` funktionieren auf mind. 2 Gerätemodellen.  
- Saubere Exit-Codes, JSON-Ausgaben, Logs.

---

## 11) Packaging & Distribution

- `pyinstaller --onefile --name ios-toolkit ios_toolkit/cli.py`  
- Beipacken: README, Hinweise zu iTunes/libusb, Beispiel-PS-Skripte.  
- Optional: MSI mit `wix` oder `msi-packager`.

---

## 12) Agenten-Gebrauchsanleitung (für Codex)

### 12.1 System-Prompt (Beispiel)
> Du bist ein vorsichtiger, deterministischer Software-Agent. Du arbeitest lokal, führst schrittweise Änderungen am Repo aus, startest Tests und passt Code an, bis alle Akzeptanzkriterien erfüllt sind. Du erzeugst klare Commits und erklärst kurz Zweck und Auswirkungen.

### 12.2 Arbeitsprinzip
1. **Planen:** Welche Datei/Änderung als Nächstes? Akzeptanzkriterium klar?  
2. **Implementieren:** Kleine, überprüfbare Änderungen.  
3. **Testen:** Unit/Smoke-Tests ausführen, Output verifizieren.  
4. **Reflektieren:** Fehler fixen, Logs prüfen.  
5. **Dokumentieren:** README/CHANGELOG aktualisieren.

### 12.3 Checkliste je Änderung
- [ ] Lint/Typecheck lokal grün  
- [ ] `pytest` grün  
- [ ] CLI-Befehl `--help` zeigt erwartete Optionen  
- [ ] Exit-Code korrekt, `--json` validiert gegen Schema  
- [ ] Relevante Logs werden geschrieben

### 12.4 Command-Palette (Beispiele)
```powershell
# Geräte
ios-toolkit list --json
ios-toolkit info --udid <UDID> --json

# Logs
ios-toolkit logs --udid <UDID> --save logs\%USERNAME%\syslog.log --duration 60

# Recovery/DFU
ios-toolkit recovery enter --udid <UDID>
ios-toolkit recovery status --json
ios-toolkit recovery kickout --udid <UDID>

# Restore
ios-toolkit flash --udid <UDID> --ipsw C:\Firmware\iPhone_*.ipsw --wipe --keep-logs

# Diagnose
ios-toolkit diag usb --json
```

---

## 13) Backlog (nach v1)
- IPSW-Autodownload per API (Modell ↔ BuildMapping).  
- Mehr Geräte-Telemetrie (Batteriestatus, NAND SMART falls verfügbar).  
- Crashlog-Analyse heuristisch (APFS/NAND-Indikatoren markieren).  
- Windows-Dienst (Agent) + GUI Frontend.  
- MDM/DEP Hooks.

---

## 14) JSON-Schemas (Beispiele)

**Device (list/info):**
```json
{
  "udid": "string",
  "product_type": "string",
  "product_version": "string",
  "device_name": "string",
  "connection": "usb|wifi",
  "mode": "normal|recovery|dfu"
}
```

**Restore-Result:**
```json
{
  "status": "success|failure",
  "udid": "string",
  "ipsw": "string",
  "wipe": true,
  "steps": [{"name": "download", "ok": true}],
  "logfile": "string",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "duration_sec": 0
}
```

---

## 15) Sicherheitsnotizen für Agenten
- Verändere keine Treiber automatisch ohne ausdrückliche Freigabe.  
- Prüfe Schreibrechte in `log-dir`.  
- Niemals sensible Logs unverschlüsselt in öffentliche Orte schreiben.

---

## 16) Anhang A – Projektstruktur (vorgeschlagen)

```
ios_toolkit/
  __init__.py
  cli.py
  device.py
  logs.py
  recovery.py
  restore.py
  utils.py
tests/
  test_cli.py
pyproject.toml
requirements.txt
README.md
LICENSE
Makefile
.gitignore
```

---

## 17) Anhang B – Quickstart (Konzise)

```powershell
# 1) Python & Tools
py -m pip install -r requirements.txt

# 2) Dev-Run
py -m ios_toolkit.cli --help

# 3) Build EXE
py -m pip install pyinstaller
py -m PyInstaller --onefile --name ios-toolkit ios_toolkit/cli.py
```
