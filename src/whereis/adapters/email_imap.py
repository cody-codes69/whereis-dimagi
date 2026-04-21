"""Optional Gmail IMAP poller — runs as a background task when configured.

Enabled by setting ``WHEREIS_EMAIL_ADAPTER=imap`` plus IMAP creds. Keeps the
flow identical to the webhook path: each new message is converted to an
``InboundMessage`` and piped through ``services.ingest.ingest``.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import logging
from email.utils import parseaddr

from ..config import settings
from ..db import session_scope
from ..schemas import InboundMessage
from ..services.ingest import ingest
from ..services.parser import parse_body

log = logging.getLogger("whereis.imap")

_PLACEHOLDER_HINTS = ("<", ">", "your-", "app-password", "changeme", "example.com")
_BACKOFF_CAP_SECS = 30 * 60


def _looks_like_placeholder(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.lower()
    return any(h in lowered for h in _PLACEHOLDER_HINTS)


def _credentials_ok() -> bool:
    return not (
        _looks_like_placeholder(settings.imap_user)
        or _looks_like_placeholder(settings.imap_password)
    )


def _fetch_unseen() -> list[tuple[str, str]]:
    msgs: list[tuple[str, str]] = []
    with imaplib.IMAP4_SSL(settings.imap_host) as m:
        m.login(settings.imap_user, settings.imap_password)  # type: ignore[arg-type]
        m.select(settings.imap_mailbox)
        _, data = m.search(None, "UNSEEN")
        for num in data[0].split():
            _, raw = m.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            sender = parseaddr(msg.get("From", ""))[1]
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", "replace"
                        )
                        break
            else:
                body = msg.get_payload(decode=True).decode(
                    msg.get_content_charset() or "utf-8", "replace"
                )
            m.store(num, "+FLAGS", "\\Seen")
            msgs.append((sender, body))
    return msgs


async def poll_loop(interval_seconds: int | None = None) -> None:
    base_interval = interval_seconds or settings.imap_poll_seconds
    if not _credentials_ok():
        log.warning(
            "[imap] skipping poll loop: missing or placeholder credentials "
            "(set WHEREIS_IMAP_USER / WHEREIS_IMAP_PASSWORD)"
        )
        return

    backoff = base_interval
    first_success_logged = False
    while True:
        try:
            fetched = _fetch_unseen()
            if not first_success_logged:
                log.info(
                    "[imap] connected as %s, mailbox=%s, poll=%ds",
                    settings.imap_user,
                    settings.imap_mailbox,
                    base_interval,
                )
                first_success_logged = True
            for sender, body in fetched:
                msg: InboundMessage = parse_body(body, identifier=sender, source="email")
                with session_scope() as s:
                    ingest(s, msg)
                log.info("[imap] ingested update from %s", sender)
            backoff = base_interval  # success -> reset
        except imaplib.IMAP4.error as e:
            log.warning("[imap] auth/protocol error: %s — backing off %ds", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(_BACKOFF_CAP_SECS, backoff * 2)
            continue
        except Exception as e:  # noqa: BLE001
            log.warning("[imap] transient error: %s", e)
        await asyncio.sleep(base_interval)
