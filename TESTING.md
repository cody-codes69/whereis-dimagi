# Whereis Dimagi — Full Testing & Demo Guide

The goal of this document is to leave no stone unturned. If you execute it
top-to-bottom in a fresh clone, you will have:

1. installed the project,
2. seeded the GeoNames database,
3. exercised every HTTP endpoint from both the browser *and* `curl`,
4. verified every acceptance criterion and bonus point in the brief,
5. seen the physics validator, time-travel, fuzzy/regex geocoding, the
   map fallback, and all 10 creative badges fire,
6. tested the service against **real Twilio SMS signing** and **real
   Gmail IMAP** when you're ready,
7. run the automated suite (63 tests) and the linter.

Total wall-clock time with a good connection: **~15 minutes**.

---

## Table of contents

- [0. Pre-flight checklist](#0-pre-flight-checklist)
- [1. Install & seed](#1-install--seed)
- [2. Run the service](#2-run-the-service)
- [3. Smoke test: healthz + OpenAPI](#3-smoke-test-healthz--openapi)
- [4. The HTML form (browser)](#4-the-html-form-browser)
- [5. The HTML form (curl)](#5-the-html-form-curl)
- [6. JSON API `POST /updates`](#6-json-api-post-updates)
- [7. SMS webhook](#7-sms-webhook)
- [8. Email webhook](#8-email-webhook)
- [9. Time-travel queries](#9-time-travel-queries)
- [10. Fuzzy / prefix / regex geocoding](#10-fuzzy--prefix--regex-geocoding)
- [11. Disambiguation strategies](#11-disambiguation-strategies)
- [12. Physics validator (soft + hard-fail)](#12-physics-validator-soft--hard-fail)
- [13. The map (`/map`) + offline fallback](#13-the-map-map--offline-fallback)
- [14. The 10 creative badges](#14-the-10-creative-badges)
- [15. Plaintext & JSON dumps](#15-plaintext--json-dumps)
- [16. Shared-secret gate](#16-shared-secret-gate)
- [17. Live mode: Twilio + Gmail IMAP](#17-live-mode-twilio--gmail-imap)
- [18. Fixture generator (direct DB + `--target`)](#18-fixture-generator-direct-db--target)
- [19. Automated test suite](#19-automated-test-suite)
- [20. Docker end-to-end](#20-docker-end-to-end)
- [21. Cleanup](#21-cleanup)
- [Appendix A: One-shot demo script](#appendix-a-one-shot-demo-script)
- [Appendix B: Scenario coverage matrix](#appendix-b-scenario-coverage-matrix)

---

## 0. Pre-flight checklist

You need:

- **Python ≥ 3.11** — `python3 --version`.
- **Internet access** the first time you seed (to download GeoNames ~3 MB).
- A shell — examples use Bash/Zsh; `curl` + `jq` are used throughout.

```bash
python3 --version   # ≥ 3.11
which curl jq       # both installed; jq is pretty-printing only
```

Optional for live mode in §17:

- A Twilio account + trial phone number + auth token.
- A Gmail account with 2FA + an app password.

---

## 1. Install & seed

```bash
git clone https://github.com/<you>/whereis-dimagi.git
cd whereis-dimagi

# Creates .venv, installs the package editable with dev deps.
make install

# Downloads https://download.geonames.org/export/dump/cities15000.zip,
# unpacks into data/cities15000.txt, loads into data/whereis.db,
# and builds the FTS5 index. Expect ~33,560 places.
make seed
```

Verify the DB:

```bash
sqlite3 data/whereis.db "SELECT COUNT(*) FROM places;"       # 33560
sqlite3 data/whereis.db "SELECT COUNT(*) FROM places_fts;"   # 33560
```

> If you have no internet, drop `cities15000.txt` into `data/` manually
> and re-run `make seed` — it will skip the download.

---

## 2. Run the service

```bash
make run
# Uvicorn running on http://0.0.0.0:8000  (auto-reload on)
```

Leave this terminal open. Open a second one for the `curl` examples.

---

## 3. Smoke test: healthz + OpenAPI

```bash
curl -s http://localhost:8000/healthz | jq
```

Expected:

```json
{
  "status": "ok",
  "places_count": 33560,
  "people_count": 0,
  "updates_count": 0,
  "sms_adapter": "simulator",
  "email_adapter": "simulator",
  "default_strategy": "population"
}
```

Open `http://localhost:8000/docs` in a browser — every route shows up in
OpenAPI with its schema.

---

## 4. The HTML form (browser)

1. Open `http://localhost:8000/`.
2. Disable JavaScript in DevTools — the form is fully server-rendered.
3. Submit:

    | Field | Value |
    |---|---|
    | identifier | `anna.li@dimagi.com` |
    | location | `Dodoma` |
    | observed_at | leave blank |
    | strategy | `population` |

4. Result card should show:

   > Matched: **Dodoma, TZ** — lat 6.173..., lng 35.741...
   > Confidence: `1.00` — Source: `form`

5. Submit another for the same identifier: location `Kampala`.
6. Navigate to `http://localhost:8000/whereis/anna.li@dimagi.com` — you
   should see **Kampala**, last-known.
7. View source: there's a `<meta name="whereis-status" content="ok">` tag.
8. Submit `Springfield` — with the default `population` strategy, Anna
   lands in **Springfield, MO** (pop. 169k).

---

## 5. The HTML form (curl)

```bash
curl -i -X POST http://localhost:8000/ \
  -d 'identifier=bob@dimagi.com' \
  -d 'location=Boston' \
  -d 'strategy=population'
```

`200 OK`, rendered HTML, the form is now pre-filled with Bob's identifier.

---

## 6. JSON API `POST /updates`

The API accepts three shapes on the same endpoint.

### 6a. Single record

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{
    "identifier": "alex@dimagi.com",
    "location": "Nairobi",
    "observed_at": "2026-04-20T09:30:00Z"
  }' | jq
```

### 6b. List of records

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    {"identifier":"carol@dimagi.com","location":"Lagos"},
    {"identifier":"david@dimagi.com","location":"Kigali"}
  ]' | jq 'length'  # 2
```

### 6c. Exercise brief's array format

This is the `[[identifier, time, location], ...]` shape called out in
`coding_exercise.txt`:

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["eve@dimagi.com",  "2026-04-20T10:00:00Z", "Dakar"],
    ["eve@dimagi.com",  "2026-04-20T18:00:00Z", "Accra"],
    ["frank@dimagi.com","2026-04-20T08:00:00Z", "Johannesburg"]
  ]' | jq 'map({identifier, place: .place.name, country: .place.country_code})'
```

Expected:

```json
[
  {"identifier":"eve@dimagi.com","place":"Dakar","country":"SN"},
  {"identifier":"eve@dimagi.com","place":"Accra","country":"GH"},
  {"identifier":"frank@dimagi.com","place":"Johannesburg","country":"ZA"}
]
```

### 6d. Invalid strategy → 422

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST 'http://localhost:8000/updates?strategy=bogus' \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"x@y","location":"Boston"}'
# → 422
```

### 6e. Invalid timestamp in tuple form → 400

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[["x@y","NOT-A-DATE","Boston"]]'
# → 400
```

---

## 7. SMS webhook

The default SMS adapter is `simulator` — no signing required — so this
works out of the box.

```bash
curl -s -X POST http://localhost:8000/webhooks/sms \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'From=+15551234567' \
  --data-urlencode 'Body=Mombasa'
# → TwiML XML response with <Message>ok: Mombasa (KE) ...
```

Request JSON instead:

```bash
curl -s -X POST http://localhost:8000/webhooks/sms \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'From=+15551234567' \
  --data-urlencode 'Body=Kisumu' | jq
```

Empty body → 400:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8000/webhooks/sms \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'From=+15551234567' \
  --data-urlencode 'Body='
# → 400
```

(The Twilio-signed variant is covered in §17.)

---

## 8. Email webhook

### 8a. Mailgun form shape

```bash
curl -s -X POST http://localhost:8000/webhooks/email \
  -F 'sender=jane@ngo.org' \
  -F 'subject=checkin' \
  -F 'body-plain=at Dodoma for the clinic run' | jq
```

### 8b. Simulator JSON shape

```bash
curl -s -X POST http://localhost:8000/webhooks/email \
  -H 'Content-Type: application/json' \
  -d '{"from":"jane@ngo.org","text":"Greetings from Nairobi"}' | jq
```

### 8c. `"Name <email>"` format

```bash
curl -s -X POST http://localhost:8000/webhooks/email \
  -F 'From=Jane Doe <jane@ngo.org>' \
  -F 'body-plain=now in Kampala' | jq '.identifier'
# → "jane@ngo.org"
```

---

## 9. Time-travel queries

Seed a small timeline for Eve:

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["eve2@dimagi.com","2011-04-01T10:00:00Z","Lusaka"],
    ["eve2@dimagi.com","2011-06-15T10:00:00Z","Nairobi"],
    ["eve2@dimagi.com","2026-01-01T10:00:00Z","Boston"]
  ]' > /dev/null
```

Then:

```bash
# Latest — Boston.
curl -s 'http://localhost:8000/whereis/eve2@dimagi.com' | grep -E '(Boston|Nairobi|Lusaka)'

# As-of 2011-06-15 — Nairobi.
curl -s 'http://localhost:8000/whereis/eve2@dimagi.com?at=2011-06-15T00:00:00Z' | grep -E 'Nairobi|Lusaka'

# As-of 2010 — unknown (before first update).
curl -s 'http://localhost:8000/whereis/eve2@dimagi.com?at=2010-01-01T00:00:00Z' | grep -i 'no updates'
```

Bad `at` → 400:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  'http://localhost:8000/whereis/eve2@dimagi.com?at=not-a-date'
# → 400
```

Unknown person (meta tag):

```bash
curl -s 'http://localhost:8000/whereis/ghost@nowhere.com' | grep 'whereis-status'
# → <meta name="whereis-status" content="unknown">
```

---

## 10. Fuzzy / prefix / regex geocoding

```bash
# Exact — 1.00 confidence.
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"g1@dimagi.com","location":"Dodoma"}' | jq '.[0].match_confidence'

# Prefix via FTS5 — still 1.00.
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"g2@dimagi.com","location":"Dod"}' | jq '.[0].place.name'

# Fuzzy typo — confidence in the 0.5..0.85 band.
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"g3@dimagi.com","location":"Dodomma"}' \
  | jq '{place: .[0].place.name, conf: .[0].match_confidence}'

# Regex, ordered by population (San Francisco, US comes first).
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"g4@dimagi.com","location":"/^San .*/"}' \
  | jq '.[0].place | {name, country_code, population}'
```

---

## 11. Disambiguation strategies

### 11a. Population (default)

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"s1@dimagi.com","location":"Springfield"}' \
  | jq '.[0].place | {name, admin1, country_code}'
# → Springfield, MO, US (largest by population)
```

### 11b. Proximity

Anchor `s2` in Boston first, then send `Springfield` with proximity —
Springfield, MA wins over the larger Springfield, MO.

```bash
# Anchor: last-known = Boston.
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"s2@dimagi.com","location":"Boston"}' > /dev/null

# Ambiguous follow-up under ?strategy=proximity.
curl -s -X POST 'http://localhost:8000/updates?strategy=proximity' \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"s2@dimagi.com","location":"Springfield"}' \
  | jq '.[0].place | {name, admin1, country_code}'
# → {"name":"Springfield","admin1":"MA","country_code":"US"}
```

### 11c. First hit

```bash
curl -s -X POST 'http://localhost:8000/updates?strategy=first' \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"s3@dimagi.com","location":"Springfield"}' \
  | jq '.[0].place.name'
```

---

## 12. Physics validator (soft + hard-fail)

### 12a. Soft — warning stored

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["speedy@dimagi.com","2026-04-20T08:00:00Z","Delhi"],
    ["speedy@dimagi.com","2026-04-20T08:15:00Z","Seattle"]
  ]' | jq '.[1].warnings'
# → ["implausible_speed"]
```

### 12b. Hard-fail — HTTP 422

Stop the server (Ctrl-C in terminal 1) and relaunch with enforcement:

```bash
WHEREIS_PHYSICS_ENFORCE=true make run
```

Re-run the same curl — you'll get:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["strict@dimagi.com","2026-04-20T08:00:00Z","Delhi"],
    ["strict@dimagi.com","2026-04-20T08:15:00Z","Seattle"]
  ]'
# → 422
```

Stop and restart without the flag for the rest of the walkthrough.

---

## 13. The map (`/map`) + offline fallback

1. Open `http://localhost:8000/map`.
2. You should see coloured pins for every person with a known location.
   Hover — popups link to `/whereis/{id}`.
3. Block the tile CDN: DevTools → Network → block request URL matching
   `tile.openstreetmap`. Reload the page. Leaflet's `onerror` swaps in
   `static/map_fallback.png` (the screenshot shipped with the exercise).
4. Disable JavaScript entirely. Reload — the `<noscript>` block renders
   the same fallback image, so 2G users still get *something*.
5. Rewind via query string: `http://localhost:8000/map?at=2011-06-15T00:00:00Z`
   — only the two people known by that date show pins.

---

## 14. The 10 creative badges

Seed a little history so badges are interesting:

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["b1@dimagi.com","2026-04-01T08:00:00Z","Reykjavik"],
    ["b1@dimagi.com","2026-04-02T08:00:00Z","Cape Town"],
    ["b1@dimagi.com","2026-04-03T08:00:00Z","Tokyo"],
    ["b1@dimagi.com","2026-04-04T08:00:00Z","Lima"],
    ["b2@dimagi.com","2026-04-01T08:00:00Z","Boston"],
    ["b2@dimagi.com","2026-04-02T08:00:00Z","Cambridge"],
    ["b2@dimagi.com","2026-04-03T08:00:00Z","Boston"],
    ["b2@dimagi.com","2026-04-04T08:00:00Z","Boston"],
    ["b3@dimagi.com","2020-01-01T08:00:00Z","Dodoma"],
    ["b3@dimagi.com","2026-04-04T08:00:00Z","Dodoma"]
  ]' > /dev/null

curl -s http://localhost:8000/badges.json | jq 'keys'
```

Expected slugs (exactly 10):

```json
[
  "biggest-homebody",
  "equator-crosser",
  "globe-trotter",
  "groundhog-day",
  "jet-lagger",
  "most-distance",
  "phantom",
  "phoenix",
  "red-eye-rocket",
  "time-bender"
]
```

Verify the cosmic-speed bug fix (this is the original reason the
second-pass review shipped a patch): the `red-eye-rocket` value should
**never exceed ~2,500 km/h** even if you POST two updates seconds apart.

```bash
curl -s -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '[
    ["cosmic@dimagi.com","2026-04-20T10:00:00.000Z","Delhi"],
    ["cosmic@dimagi.com","2026-04-20T10:00:01.000Z","Seattle"]
  ]' > /dev/null

curl -s http://localhost:8000/badges.json \
  | jq '.["red-eye-rocket"]'
# value is a sane number (< 2500 km/h) or a different winner entirely.
```

Open `http://localhost:8000/badges` for the human-readable view.

---

## 15. Plaintext & JSON dumps

```bash
# Tab-separated, 2G-friendly.
curl -s http://localhost:8000/whereis.txt | head
# # whereis — latest known locations (UTC, tab-separated)
# anna.li@dimagi.com   2026-04-21 10:22   Kampala (UG)
# ...

# Machine-readable sibling.
curl -s http://localhost:8000/whereis.json | jq '.[0]'
# Notice observed_at ends in exactly one trailing "Z".
curl -s http://localhost:8000/whereis.json \
  | jq -r '.[] | .observed_at' \
  | grep -vE 'Z$' | wc -l
# → 0   (all timestamps end in Z; none double-stamped)
```

---

## 16. Shared-secret gate

Stop the server and relaunch with a shared secret:

```bash
WHEREIS_SHARED_SECRET=s3cret make run
```

Without the header — 401:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -d '{"identifier":"x@y","location":"Boston"}'
# → 401
```

With the header — 200:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/updates \
  -H 'Content-Type: application/json' \
  -H 'X-Shared-Secret: s3cret' \
  -d '{"identifier":"x@y","location":"Boston"}'
# → 200
```

The same gate protects `/webhooks/sms` and `/webhooks/email`.

Stop the server and unset the variable for the rest of the walkthrough.

---

## 17. Live mode: Twilio + Gmail IMAP

Edit `.env`:

```bash
WHEREIS_SMS_ADAPTER=twilio
WHEREIS_TWILIO_AUTH_TOKEN=<your real token>
WHEREIS_TWILIO_VERIFY_SIGNATURE=true

WHEREIS_EMAIL_ADAPTER=imap
WHEREIS_IMAP_USER=you@gmail.com
WHEREIS_IMAP_PASSWORD="abcd efgh ijkl mnop"
```

Restart:

```bash
make run
```

Verify:

```bash
curl -s http://localhost:8000/healthz | jq '{sms_adapter, email_adapter}'
# → {"sms_adapter":"twilio", "email_adapter":"imap"}
```

Within ~60 s you'll see in the server log:

```
[imap] connected as you@gmail.com, mailbox=INBOX, poll=60s
```

### 17a. Unsigned Twilio POST → 403

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST http://localhost:8000/webhooks/sms \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'From=+15551234567' \
  --data-urlencode 'Body=Nairobi'
# → 403
```

### 17b. Signed Twilio POST → 200

Compute the signature exactly as Twilio does: `base64(hmac_sha1(token,
url + concat(sorted(key+value))))`.

```bash
URL='http://localhost:8000/webhooks/sms'
FROM='+15551234567'
BODY='Kampala'
TOKEN=$(grep WHEREIS_TWILIO_AUTH_TOKEN .env | cut -d= -f2-)

# Payload keys sorted alphabetically: Body, From.
SIG=$(python3 - <<PY
import base64, hashlib, hmac, os
url  = "$URL"
body = "$BODY"
frm  = "$FROM"
token = "$TOKEN"
data  = url + "Body" + body + "From" + frm
mac = hmac.new(token.encode(), data.encode(), hashlib.sha1)
print(base64.b64encode(mac.digest()).decode())
PY
)

curl -s -X POST "$URL" \
  -H "X-Twilio-Signature: $SIG" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode "From=$FROM" \
  --data-urlencode "Body=$BODY"
# → <Response><Message>ok: Kampala (UG)...
```

### 17c. Gmail IMAP poller

Send yourself an email from another account with subject "checkin" and
body `now in Mombasa`. Within `WHEREIS_IMAP_POLL_SECONDS` (default 60s)
the server ingests it and the log shows:

```
[imap] ingested 1 message(s); subject="checkin"
```

Then `curl -s http://localhost:8000/whereis.json | jq '.[] | select(.identifier=="<your sender>")'`.

### 17d. Placeholder creds are detected

Set `WHEREIS_IMAP_PASSWORD='<app-password>'` literally and restart —
the server logs:

```
[imap] skipping poll loop: credentials look like placeholders
```

and never attempts Gmail auth.

### 17e. Backoff on bad creds

Set `WHEREIS_IMAP_PASSWORD=wrongwrong` — the server retries with
exponential backoff capped at 30 minutes and keeps serving HTTP.

> Remember to rotate your Twilio auth token and Gmail app password when
> you're done demoing.

---

## 18. Fixture generator (direct DB + `--target`)

### 18a. Direct DB mode — deterministic

```bash
python -m whereis.tools.generate_fixtures --count 20 --seed 42
# [fixtures] wrote 20 updates across 6 people to data/whereis.db
```

### 18b. `--target` mode — honours shared secret + Twilio signature

```bash
# With shared-secret gate.
WHEREIS_SHARED_SECRET=s3cret make run   # in another terminal

python -m whereis.tools.generate_fixtures \
  --count 5 --seed 7 \
  --target http://localhost:8000

curl -s http://localhost:8000/healthz | jq .people_count
```

If `WHEREIS_TWILIO_VERIFY_SIGNATURE=true` and the generator targets
`/webhooks/sms`, it attaches a valid `X-Twilio-Signature` automatically.

---

## 19. Automated test suite

```bash
make test
# 62 passed in ~1s
```

Coverage summary:

| File | Tests | What it proves |
|---|---:|---|
| `test_parser.py` | 4 | ISO / natural-language date + body parsing |
| `test_geocoder.py` | 10 | exact / FTS / fuzzy / regex paths + confidence band + regex population ordering + scan cap |
| `test_strategies.py` | 7 | population / proximity / first + `StrategyName` re-export + haversine sanity |
| `test_validator.py` | 5 | physics warnings (speed, non-monotonic) + `PHYSICS_ENFORCE=true` → 422 |
| `test_badges.py` | 5 | all 10 slugs + `_fastest_leg` sanity cap + sub-minute skip + phoenix tiebreak |
| `test_query_as_of.py` | 7 | time-travel, `/healthz`, `/whereis.json`, ISO-Z format, tz-aware handling, unknown-person meta tag |
| `test_api_form.py` | 10 | HTML form, array-of-tuples ingest, single object, invalid/valid strategy literals, shared-secret gate, tab-separated `/whereis.txt`, batch single-commit |
| `test_api_sms.py` | 5 | webhook happy path, 400 on empty body, TwiML XML escape, JSON on `Accept`, display-name derivation |
| `test_api_email.py` | 4 | mailgun form shape, JSON shape, `email_simulator` removal, simulator shape still accepted |
| `test_end_to_end.py` | 5 | ingest → validate physics, R*Tree cleanup migration, fixture generator sends `X-Shared-Secret` + Twilio signature, map+badges end-to-end |

Lint:

```bash
make lint
# ruff: all checks passed
```

The test suite is **hermetic** — it purges all `WHEREIS_*` env vars and
constructs `Settings(_env_file=None)` before app import, so `make test`
works unchanged on a machine with live Twilio/IMAP creds in `.env`.

---

## 20. Docker end-to-end

```bash
docker compose up --build
```

From another terminal:

```bash
# Seeded on container start, healthcheck is live, non-root.
docker inspect -f '{{.Config.User}}' $(docker compose ps -q whereis)   # nobody
curl -s http://localhost:8000/healthz | jq .status                     # "ok"
curl -s http://localhost:8000/whereis.json | jq 'length'
```

The DB lives in the named volume `whereis-data` — surviving
`docker compose down` (remove with `docker volume rm`).

---

## 21. Cleanup

```bash
# Stop the server (Ctrl-C in terminal 1).
make clean                          # removes venv, caches, data/
docker compose down -v              # removes named volume
# Rotate Twilio token + Gmail app password if you used live mode.
```

---

## Appendix A: One-shot demo script

Paste this into a fresh shell after `make install && make seed && make run` — it
exercises 90 % of the walkthrough in ~20 seconds:

```bash
B=http://localhost:8000

# Core ingest + time-travel timeline.
curl -s -X POST $B/updates -H 'Content-Type: application/json' -d '[
  ["anna.li@dimagi.com","2026-04-20T08:00:00Z","Dodoma"],
  ["anna.li@dimagi.com","2026-04-20T14:00:00Z","Kampala"],
  ["bob@dimagi.com",    "2026-04-20T09:00:00Z","Boston"],
  ["carol@dimagi.com",  "2011-06-15T10:00:00Z","Lusaka"],
  ["carol@dimagi.com",  "2026-01-01T10:00:00Z","Boston"]
]' > /dev/null

# Fuzzy + regex.
curl -s -X POST $B/updates -H 'Content-Type: application/json' \
  -d '{"identifier":"d@d.com","location":"Dodomma"}' > /dev/null
curl -s -X POST $B/updates -H 'Content-Type: application/json' \
  -d '{"identifier":"e@d.com","location":"/^San .*/"}' > /dev/null

# Proximity vs population.
curl -s -X POST $B/updates -H 'Content-Type: application/json' \
  -d '{"identifier":"bob@dimagi.com","location":"Springfield"}' \
  > /dev/null   # population → MO
curl -s -X POST "$B/updates?strategy=proximity" -H 'Content-Type: application/json' \
  -d '{"identifier":"bob@dimagi.com","location":"Springfield"}' \
  | jq '.[0].place | {name,admin1}'       # proximity → MA

# Physics (soft).
curl -s -X POST $B/updates -H 'Content-Type: application/json' \
  -d '[
    ["speedy@d.com","2026-04-20T08:00:00Z","Delhi"],
    ["speedy@d.com","2026-04-20T08:15:00Z","Seattle"]
  ]' | jq '.[1].warnings'

# Output surfaces.
curl -s $B/healthz        | jq '{status,places_count,people_count,updates_count}'
curl -s $B/whereis.txt    | head
curl -s $B/whereis.json   | jq 'length'
curl -s $B/badges.json    | jq 'keys'

# Time-travel.
curl -s "$B/whereis/carol@dimagi.com?at=2012-01-01T00:00:00Z" | grep -Eo 'Lusaka|Boston'
```

---

## Appendix B: Scenario coverage matrix

Every bullet in `coding_exercise.txt` (core + bonus) has at least one
checkbox below.

| Requirement | Section | Automated test |
|---|---|---|
| Web form for field check-ins | §4, §5 | `test_api_form.py::test_form_get`, `::test_form_post_records_update` |
| Array-format ingest `[[id,time,loc], ...]` | §6c | `test_api_form.py::test_api_batch_tuple_format` |
| Single-object + list-of-objects ingest | §6a, §6b | `test_api_form.py::test_api_single_object` |
| GeoNames source | §1 | `data/loader.py` + all `test_geocoder.py` cases |
| Normalized `(person, time, lat, lng)` output | §6 | `test_api_form.py`, `test_end_to_end.py::test_end_to_end_map_and_badges` |
| UI component | §4, §13, §14, §15 | `test_api_form.py`, `test_end_to_end.py::test_end_to_end_map_and_badges` |
| **Bonus:** live email integration | §8, §17c | `test_api_email.py::*` |
| **Bonus:** SMS HTTP API | §7, §17a, §17b | `test_api_sms.py::test_sms_webhook_twilio_shape`, `::test_sms_twiml_escapes_xml`, `::test_sms_webhook_returns_json_on_accept` |
| **Bonus:** partial / regex match | §10 | `test_geocoder.py::test_regex_match`, `::test_regex_search_prefers_high_population`, `::test_regex_search_limits_scan`, `::test_fuzzy_match_confidence_reflects_score` |
| **Bonus:** configurable strategies | §11 | `test_strategies.py::*`, `test_api_form.py::test_api_rejects_invalid_strategy`, `::test_api_accepts_valid_strategy` |
| **Bonus:** time-travel query | §9 | `test_query_as_of.py::test_as_of_returns_most_recent_leq`, `::test_as_of_before_first_update_empty` |
| **Bonus:** map rendering | §13 | `test_end_to_end.py::test_end_to_end_map_and_badges` |
| **Bonus:** creative badges | §14 | `test_badges.py::test_new_badges_present`, `::test_fastest_leg_ignores_sub_minute_legs`, `::test_fastest_leg_ignores_implausible_speed_warnings`, `::test_phoenix_is_second_longest_gap` |
| **Bonus:** location validation | §12 | `test_validator.py::test_implausible_speed`, `::test_non_monotonic_time`, `::test_physics_enforce_returns_422` |
| **Bonus:** source-data generator | §18 | `test_end_to_end.py::test_fixture_generator_includes_shared_secret`, `::test_fixture_generator_signs_twilio_sms` |
| **Bonus:** "roll your own" (plaintext, phantom badge, healthz, shared-secret gate, JSON dump, display name derivation) | §3, §14, §15, §16 | `test_query_as_of.py::test_healthz_reports_counts`, `::test_whereis_json`, `::test_whereis_json_observed_at_ends_in_single_z`, `::test_unknown_person_has_meta_tag`, `test_api_form.py::test_whereis_txt_is_tab_separated`, `::test_shared_secret_blocks_when_missing`, `::test_shared_secret_accepts_when_header_matches`, `::test_batch_commit_single_transaction`, `test_api_sms.py::test_display_name_derived_from_email` |
| **R\*Tree cleanup migration** (internal) | (internal) | `test_end_to_end.py::test_loader_drops_rtree_leftovers` |
| **`email_simulator` removal** (internal) | (internal) | `test_api_email.py::test_email_simulator_module_removed` |
| **`StrategyName` re-export** (internal) | (internal) | `test_strategies.py::test_strategy_name_reexported_from_schemas` |

When every section here passes and `make test && make lint` is green,
you have demonstrated end-to-end coverage of every acceptance criterion
and every bonus item in the exercise.
