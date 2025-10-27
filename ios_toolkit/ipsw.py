from __future__ import annotations

import hashlib
import plistlib
import zipfile
from pathlib import Path
from typing import Optional

from .utils import get_logger

log = get_logger(__name__)


def validate_ipsw(path: str | Path) -> dict:
    """
    Validate a local IPSW file.
    Returns a dict containing ok flag, size, sha1, manifest presence and optional error message.
    """
    result = {
        "ok": False,
        "size": 0,
        "sha1": None,
        "has_manifest": False,
        "error": None,
    }

    file_path = Path(path)
    if not file_path.exists():
        result["error"] = "IPSW not found"
        return result
    if not file_path.is_file():
        result["error"] = "IPSW path is not a file"
        return result

    size = file_path.stat().st_size
    result["size"] = size
    if size <= 0:
        result["error"] = "IPSW file is empty"
        return result

    sha1 = hashlib.sha1()
    with file_path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            sha1.update(chunk)
    result["sha1"] = sha1.hexdigest()

    try:
        with zipfile.ZipFile(file_path) as zf:
            names = zf.namelist()
            manifest_name = next((name for name in names if name.endswith("BuildManifest.plist")), None)
            result["has_manifest"] = manifest_name is not None
            if manifest_name:
                # Touch the manifest to ensure it is readable.
                with zf.open(manifest_name):
                    pass
    except zipfile.BadZipFile:
        result["error"] = "IPSW is not a valid ZIP archive"
        return result
    except Exception as exc:  # pragma: no cover - unexpected issues
        log.error("Failed to inspect IPSW %s: %s", file_path, exc)
        result["error"] = str(exc)
        return result

    result["ok"] = True
    return result


def product_from_manifest(path: str | Path) -> Optional[str]:
    """
    Try to extract the product type from BuildManifest.plist inside the IPSW.
    Returns the product type string or None if unavailable.
    """
    file_path = Path(path)
    try:
        with zipfile.ZipFile(file_path) as zf:
            manifest_name = next((name for name in zf.namelist() if name.endswith("BuildManifest.plist")), None)
            if not manifest_name:
                return None
            with zf.open(manifest_name) as manifest_fp:
                plist_data = plistlib.load(manifest_fp)
    except Exception as exc:  # pragma: no cover
        log.debug("Manifest parsing failed for %s: %s", file_path, exc)
        return None

    if isinstance(plist_data, dict):
        product = plist_data.get("ProductType")
        if product:
            return product
        identities = plist_data.get("BuildIdentities")
        if isinstance(identities, list) and identities:
            info = identities[0].get("Info") if isinstance(identities[0], dict) else None
            if isinstance(info, dict):
                return info.get("ProductType") or info.get("DeviceClass")
    return None
