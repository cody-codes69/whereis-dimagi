"""POST /webhooks/sms — Twilio-compatible SMS webhook.

Returns TwiML by default (so Twilio will read the ack back to the sender).
If the request's ``Accept`` header prefers JSON, returns JSON instead —
handy for curl/debugging.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..adapters import sms_simulator, sms_twilio
from ..config import settings
from ..db import get_session
from ..security import require_shared_secret
from ..services.ingest import ingest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _adapter():
    return sms_twilio if settings.sms_adapter == "twilio" else sms_simulator


def _wants_json(accept: str | None) -> bool:
    if not accept:
        return False
    return "application/json" in accept.lower()


@router.post("/sms", dependencies=[Depends(require_shared_secret)])
async def sms_webhook(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
    accept: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    form = await request.form()
    payload = {k: str(v) for k, v in form.items()}

    if settings.sms_adapter == "twilio" and settings.twilio_verify_signature:
        url = str(request.url)
        if not sms_twilio.verify_signature(url, payload, x_twilio_signature):
            # Be explicit about *why* we rejected — the single most common
            # source of confusion when curling the webhook locally is forgetting
            # that WHEREIS_TWILIO_VERIFY_SIGNATURE is on.
            reason = "missing X-Twilio-Signature header" if not x_twilio_signature else "signature mismatch"
            hint = (
                "set WHEREIS_TWILIO_VERIFY_SIGNATURE=false for local curl, "
                "or use WHEREIS_SMS_ADAPTER=simulator, "
                "or sign the request (see TESTING.md §17b)."
            )
            raise HTTPException(
                status_code=403,
                detail=f"invalid twilio signature: {reason}. {hint}",
            )

    adapter = _adapter()
    msg = adapter.to_message(payload)
    if not msg.identifier or not msg.raw_location:
        raise HTTPException(400, "missing 'From' or 'Body'")
    upd = ingest(session, msg)

    place = f"{upd.place.name} ({upd.place.country_code})" if upd.place else "no match"
    warn_suffix = f" [{','.join(upd.warnings)}]" if upd.warnings else ""
    ack = f"Got it — {place}{warn_suffix}"

    if _wants_json(accept):
        return JSONResponse({
            "id": upd.id,
            "identifier": msg.identifier,
            "place": upd.place.name if upd.place else None,
            "country": upd.place.country_code if upd.place else None,
            "warnings": list(upd.warnings or []),
            "ack": ack,
        })

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(ack)}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")
