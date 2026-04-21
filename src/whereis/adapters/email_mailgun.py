"""Parse a Mailgun/SendGrid-style inbound email webhook.

Mailgun sends ``multipart/form-data`` with fields including ``sender``,
``From``, ``subject``, ``body-plain``. Both shapes are accepted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ..schemas import InboundMessage
from ..services.parser import parse_body

_EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _extract_email(value: str) -> str:
    m = _EMAIL_RX.search(value or "")
    return m.group(0) if m else (value or "")


def to_message(payload: Mapping[str, str]) -> InboundMessage:
    sender = (
        payload.get("sender")
        or payload.get("From")
        or payload.get("from")
        or payload.get("email")
        or ""
    )
    body = (
        payload.get("body-plain")
        or payload.get("stripped-text")
        or payload.get("text")
        or payload.get("body")
        or ""
    )
    return parse_body(body, identifier=_extract_email(sender), source="email")
