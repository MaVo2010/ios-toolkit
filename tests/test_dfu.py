
from __future__ import annotations

import types

import pytest

from ios_toolkit import dfu, device


def test_get_instructions_known():
    info = dfu.get_instructions("iPhone12,8")
    assert info["model"]
    assert info["timings"] == [10, 5]
    assert len(info["steps"]) >= 3


def test_get_instructions_unknown():
    with pytest.raises(ValueError):
        dfu.get_instructions("UnknownModel,1")


def test_guide_without_countdown(monkeypatch):
    captured = []
    monkeypatch.setattr(dfu.typer, "echo", lambda msg: captured.append(msg))
    result = dfu.guide(product_type="iPhone12,8", countdown=False, sound=False)
    assert result["product_type"] == "iPhone12,8"
    assert any("DFU-Assistent" in msg for msg in captured)


def test_guide_with_udid(monkeypatch):
    captured = []
    monkeypatch.setattr(dfu.typer, "echo", lambda msg: captured.append(msg))
    monkeypatch.setattr(dfu.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        device,
        "get_info",
        lambda udid: types.SimpleNamespace(product_type="iPhone12,8"),
    )
    result = dfu.guide(udid="dummy", countdown=True, sound=False)
    assert result["product_type"] == "iPhone12,8"
