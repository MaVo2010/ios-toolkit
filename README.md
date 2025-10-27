# ios-toolkit (Scaffold)

Starter-Repository fuer ein Windows-CLI zur iOS-Geraeteverwaltung.
Siehe das ausfuehrliche Playbook: `iOS-Toolkit-Agent-Plan.md` (liegt separat).

## Quickstart
```powershell
py -m pip install -r requirements.txt
py -m ios_toolkit.cli --help
```

## Restore/Flash (M4)
- Vorabpruefung: `py -m ios_toolkit.cli flash --preflight-only --ipsw C:\Firmware\iPhone_123.ipsw --json`
- Dry-Run (zeigt nur den Befehl): `py -m ios_toolkit.cli flash --dry-run --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw`
- Voller Restore mit Timeout: `py -m ios_toolkit.cli flash --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw --wipe --timeout 3600 --json`

## IPSW-Tools (M5)
- Integritaetscheck: `py -m ios_toolkit.cli ipsw verify --file C:\Firmware\iPhone_123.ipsw --json`
- Ausgabe enthaelt SHA1, Dateigroesse und Manifest-Status.

## Troubleshooting (M6)
- Diagnose USB: `py -m ios_toolkit.cli diag usb --json`
- DFU-Anleitung: `py -m ios_toolkit.cli dfu guide --model iPhone12,8`
- Status pruefen: `py -m ios_toolkit.cli recovery status --json`