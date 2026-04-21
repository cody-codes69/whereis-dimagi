"""Generate deterministic demo data.

Two modes:

* ``--target URL`` → POSTs to the running app's webhooks (form / sms / email)
  to exercise the full pipeline end-to-end. Honours ``WHEREIS_SHARED_SECRET``
  (sent as ``X-Shared-Secret``) and, when ``WHEREIS_TWILIO_VERIFY_SIGNATURE``
  is true, computes a valid Twilio HMAC-SHA1 signature for ``/webhooks/sms``.
* default      → writes records directly to the local SQLite DB via ``ingest``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

import httpx

from ..db import session_scope
from ..schemas import InboundMessage
from ..services.ingest import ingest

SAMPLE_PEOPLE = [
    ("nick@dimagi.com", "Nick"),
    ("alex@dimagi.com", "Alex"),
    ("rosa@dimagi.com", "Rosa"),
    ("hilary@dimagi.com", "Hilary"),
    ("jeremy@dimagi.com", "Jeremy"),
    ("+15551110001", "Ben"),
    ("+15551110002", "Mohini"),
    ("+15551110003", "Saijai"),
]
SAMPLE_PLACES = [
    "Dodoma", "Lusaka", "Boston", "Delhi", "Cape Town", "Bhopal",
    "Kampala", "Maputo", "Dakar", "Nairobi", "Dublin", "Amsterdam",
    "Trondheim", "Acadia", "Bangkok", "Pondicherry",
]


def _gen_messages(count: int, seed: int) -> list[tuple[InboundMessage, str]]:
    rng = random.Random(seed)
    t = datetime.now(tz=UTC) - timedelta(days=30)
    msgs: list[tuple[InboundMessage, str]] = []
    for _ in range(count):
        ident, _name = rng.choice(SAMPLE_PEOPLE)
        place = rng.choice(SAMPLE_PLACES)
        t += timedelta(hours=rng.randint(4, 48))
        source = "sms" if ident.startswith("+") else rng.choice(["form", "email"])
        msgs.append((
            InboundMessage(
                identifier=ident,
                observed_at=t,
                raw_location=place,
                source=source,  # type: ignore[arg-type]
            ),
            place,
        ))
    return msgs


def _auth_headers() -> dict[str, str]:
    h: dict[str, str] = {}
    secret = os.environ.get("WHEREIS_SHARED_SECRET")
    if secret:
        h["X-Shared-Secret"] = secret
    return h


def _twilio_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(
        hmac.new(auth_token.encode(), data.encode(), hashlib.sha1).digest()
    ).decode()


def _post_to(target: str, msg: InboundMessage) -> httpx.Response:
    headers = _auth_headers()
    with httpx.Client(base_url=target, timeout=10, headers=headers) as cx:
        if msg.source == "sms":
            params = {"From": msg.identifier, "Body": msg.raw_location}
            sms_headers: dict[str, str] = {}
            token = os.environ.get("WHEREIS_TWILIO_AUTH_TOKEN")
            verify = os.environ.get("WHEREIS_TWILIO_VERIFY_SIGNATURE", "").lower() == "true"
            if token and verify:
                full_url = urljoin(target.rstrip("/") + "/", "webhooks/sms")
                sms_headers["X-Twilio-Signature"] = _twilio_signature(full_url, params, token)
            return cx.post("/webhooks/sms", data=params, headers=sms_headers)
        if msg.source == "email":
            return cx.post(
                "/webhooks/email",
                data={"sender": msg.identifier, "body-plain": msg.raw_location},
            )
        return cx.post(
            "/updates",
            json=[{
                "identifier": msg.identifier,
                "observed_at": msg.observed_at.isoformat(),
                "location": msg.raw_location,
            }],
        )


def cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate demo location updates.")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target", help="Base URL of running app; if omitted, writes directly to DB.")
    args = parser.parse_args(argv)

    msgs = _gen_messages(args.count, args.seed)
    if args.target:
        ok = 0
        for msg, _p in msgs:
            r = _post_to(args.target, msg)
            if 200 <= r.status_code < 300:
                ok += 1
            else:
                print(f"[fixtures] {msg.source} {msg.identifier} -> {r.status_code} {r.text[:120]}",
                      file=sys.stderr)
        print(f"[fixtures] posted {ok}/{len(msgs)} updates to {args.target}", file=sys.stderr)
    else:
        with session_scope() as s:
            for msg, _p in msgs:
                ingest(s, msg)
        print(f"[fixtures] wrote {len(msgs)} updates to DB", file=sys.stderr)


if __name__ == "__main__":
    cli()
