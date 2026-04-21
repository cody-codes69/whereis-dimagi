"""POST /webhooks/email — Mailgun / SendGrid / simulator-compatible email webhook."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..adapters import email_mailgun
from ..db import get_session
from ..security import require_shared_secret
from ..services.ingest import ingest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# The "simulator" and "mailgun" email adapters speak the same wire format
# (form-encoded ``sender`` / ``body-plain`` or JSON). The IMAP adapter never
# hits this route. So we always use ``email_mailgun.to_message``.
_adapter = email_mailgun


@router.post("/email", dependencies=[Depends(require_shared_secret)])
async def email_webhook(request: Request, session: Session = Depends(get_session)) -> dict:
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        payload = await request.json()
    else:
        form = await request.form()
        payload = {k: str(v) for k, v in form.items()}

    msg = _adapter.to_message(payload)
    if not msg.identifier or not msg.raw_location:
        raise HTTPException(400, "missing sender or body")
    upd = ingest(session, msg)
    return {
        "id": upd.id,
        "identifier": msg.identifier,
        "place": upd.place.name if upd.place else None,
        "warnings": list(upd.warnings or []),
    }
