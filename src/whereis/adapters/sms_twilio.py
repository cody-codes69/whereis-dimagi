"""Parse a Twilio-compatible inbound SMS webhook payload into InboundMessage."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping

from ..config import settings
from ..schemas import InboundMessage
from ..services.parser import parse_body


def verify_signature(url: str, payload: Mapping[str, str], signature: str | None) -> bool:
    """Twilio signature check. Returns True if disabled in config."""
    if not settings.twilio_verify_signature:
        return True
    if not (signature and settings.twilio_auth_token):
        return False
    data = url + "".join(k + payload[k] for k in sorted(payload))
    mac = hmac.new(settings.twilio_auth_token.encode(), data.encode(), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


def to_message(payload: Mapping[str, str]) -> InboundMessage:
    sender = payload.get("From") or payload.get("from") or ""
    body = payload.get("Body") or payload.get("body") or ""
    return parse_body(body, identifier=sender, source="sms")
