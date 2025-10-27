from __future__ import annotations
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

Mode = Literal["normal", "recovery", "dfu", "unknown"]
Conn = Literal["usb", "wifi", "unknown"]
Status = Literal["success", "failure"]

class Device(BaseModel):
    udid: str = Field(..., description="Unique Device Identifier")
    product_type: Optional[str] = None
    product_version: Optional[str] = None
    device_name: Optional[str] = None
    connection: Optional[Conn] = "unknown"
    mode: Optional[Mode] = "unknown"

class Step(BaseModel):
    name: str
    ok: bool

class RestoreResult(BaseModel):
    status: Status
    udid: Optional[str] = None
    ipsw: Optional[str] = None
    wipe: bool = True
    steps: List[Step] = []
    logfile: str
    started_at: str
    finished_at: str
    duration_sec: int
