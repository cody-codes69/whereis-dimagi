"""Parse free-text inbound messages into an ``InboundMessage``.

Accepts:
* SMS body:   ``@nick Dodoma`` or ``Dodoma`` (identifier taken from the SMS ``From`` field)
* Email body: ``Dodoma`` or ``location: Dodoma`` (identifier = sender)
* Form:       structured fields, no parsing needed — caller builds InboundMessage directly.

Kept deliberately small + deterministic; one regex, tested.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from ..schemas import InboundMessage, Source
from ..utils import parse_iso_utc

_PREFIX_RX = re.compile(
    r"^\s*(?:here[:\s]+|loc(?:ation)?[:\s]+|i[' ]?m\s+in\s+|at\s+)",
    flags=re.IGNORECASE,
)
_DATE_RX = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\b"
)


def parse_body(body: str, identifier: str, source: Source) -> InboundMessage:
    body = (body or "").strip()
    observed_at = datetime.now(tz=UTC)

    m = _DATE_RX.search(body)
    if m:
        try:
            parsed = parse_iso_utc(m.group(1))
            if parsed is not None:
                observed_at = parsed.replace(tzinfo=UTC)
                body = (body[: m.start()] + body[m.end():]).strip()
        except (ValueError, TypeError):
            pass

    body = _PREFIX_RX.sub("", body).strip().strip(".,!")

    return InboundMessage(
        identifier=identifier.strip().lower(),
        observed_at=observed_at,
        raw_location=body,
        source=source,
    )
