param(
    [string]$Name = "ios-toolkit",
    [string]$Entry = "ios_toolkit/cli.py"
)

$ErrorActionPreference = "Stop"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt

if (Test-Path dist) { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }

py -m PyInstaller --noconfirm --clean --onefile --name $Name --collect-all pymobiledevice3 --collect-submodules ios_toolkit $Entry

Write-Host "Built dist\$Name.exe"
Get-ChildItem dist
