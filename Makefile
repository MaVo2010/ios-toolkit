PY=python

.PHONY: venv install test run build

venv:
	$(PY) -m venv .venv

install:
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest -q

run:
	$(PY) -m ios_toolkit.cli --help

build:
	$(PY) -m pip install pyinstaller
	$(PY) -m PyInstaller --onefile --name ios-toolkit ios_toolkit/cli.py
