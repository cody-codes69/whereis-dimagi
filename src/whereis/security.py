"""Shared webhook-security helper: X-Shared-Secret header gate."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from . import config as _config_mod


def require_shared_secret(x_shared_secret: str | None = Header(default=None)) -> None:
    """FastAPI dependency. No-op when WHEREIS_SHARED_SECRET is unset."""
    expected = _config_mod.settings.shared_secret
    if not expected:
        return
    if not x_shared_secret or not hmac.compare_digest(expected, x_shared_secret):
        raise HTTPException(status_code=401, detail="invalid or missing X-Shared-Secret")
