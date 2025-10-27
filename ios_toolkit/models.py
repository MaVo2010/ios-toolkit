from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_serializer

Mode = Literal["normal", "recovery", "dfu", "unknown"]
Connection = Literal["usb", "wifi", "unknown"]
Status = Literal["success", "failure"]


class Device(BaseModel):
    udid: str = Field(..., description="Unique Device Identifier")
    product_type: Optional[str] = Field(None, description="Apple internal product identifier (e.g. iPhone12,8)")
    product_version: Optional[str] = Field(None, description="Installed firmware version (e.g. 17.0)")
    device_name: Optional[str] = Field(None, description="User-visible device name")
    connection: Connection = Field("unknown", description="Connection transport (usb|wifi|unknown)")
    mode: Mode = Field("unknown", description="Current device mode (normal|recovery|dfu|unknown)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Raw key/value properties from discovery")


class Step(BaseModel):
    name: str
    ok: bool
    detail: Optional[str] = None


class RestoreResult(BaseModel):
    status: Status
    udid: Optional[str] = None
    ipsw: Optional[str] = None
    wipe: bool = True
    steps: list[Step] = Field(default_factory=list)
    logfile: str
    started_at: datetime
    finished_at: datetime
    duration_sec: int

    @field_serializer("started_at", "finished_at")
    def _serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()
