"""Local SMS simulator — same payload shape as Twilio, zero external deps."""

from __future__ import annotations

from collections.abc import Mapping

from ..schemas import InboundMessage
from ..services.parser import parse_body


def to_message(payload: Mapping[str, str]) -> InboundMessage:
    sender = payload.get("from") or payload.get("From") or ""
    body = payload.get("body") or payload.get("Body") or ""
    return parse_body(body, identifier=sender, source="sms")
