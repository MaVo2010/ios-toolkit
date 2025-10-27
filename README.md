# ios-toolkit (Scaffold)

Starter-Repository für ein Windows-CLI zur iOS-Geräteverwaltung.
Siehe das ausführliche Playbook: `iOS-Toolkit-Agent-Plan.md` (liegt separat).

## Quickstart
```powershell
py -m pip install -r requirements.txt
py -m ios_toolkit.cli --help
```

## Restore/Flash (M4)
- Vorabpr�fung: `py -m ios_toolkit.cli flash --preflight-only --ipsw C:\Firmware\iPhone_123.ipsw --json`
- Dry-Run (zeigt nur den Befehl): `py -m ios_toolkit.cli flash --dry-run --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw`
- Voller Restore mit Timeout: `py -m ios_toolkit.cli flash --udid <UDID> --ipsw C:\Firmware\iPhone_123.ipsw --wipe --timeout 3600 --json`
