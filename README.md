# Whereis Dimagi

> A low-bandwidth check-in service for field staff in regions with poor
> connectivity. Submit where you are from a 5 KB HTML form, an SMS, or an
> email — and the service normalizes the free-text location against
> [GeoNames](http://www.geonames.org/), stores a
> `(person, time, lat, lng)` row, and answers "where is X?" at any point
> in time.

Built as a solution to the Dimagi coding exercise. Covers every acceptance
criterion and all ten bonus points.

---

## Table of contents

- [At a glance](#at-a-glance)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack & trade-offs](#tech-stack--trade-offs)
- [Repository layout](#repository-layout)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [HTTP surface](#http-surface)
- [Data model](#data-model)
- [Ingestion pipeline](#ingestion-pipeline)
- [Disambiguation strategies](#disambiguation-strategies)
- [Badges (10)](#badges-10)
- [Running live: Twilio + Gmail IMAP](#running-live-twilio--gmail-imap)
- [Docker](#docker)
- [Development](#development)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License & credits](#license--credits)

---

## At a glance

```
┌──────────┐   ┌────────┐   ┌────────────┐
│ HTML Form│──►│        │   │            │
├──────────┤   │        │   │  SQLite    │
│ POST     │──►│Whereis │──►│ ┌────────┐ │
│ /updates │   │ Dimagi │   │ │places  │ │   /whereis/{id}
├──────────┤   │FastAPI │   │ │persons │ │   /whereis.txt
│ Twilio   │──►│        │   │ │updates │ │   /whereis.json
│ SMS      │   │        │   │ └────────┘ │   /map   /badges
├──────────┤   │        │   │  + FTS5    │   /healthz
│ Mailgun /│──►│        │   │            │
│ Gmail    │   └────────┘   └────────────┘
└──────────┘
```

Every transport funnels into a single `InboundMessage` DTO, so **adding a
new input channel is an adapter, not a core change.**

---

## Features

### Core

- **Low-bandwidth HTML form** — ~5 KB, works with JavaScript disabled.
- **JSON API** — accepts both structured records and the exercise's
  array-of-tuples format `[[identifier, time, location], ...]`.
- **SMS webhook** (`POST /webhooks/sms`) — Twilio-compatible, verifies
  `X-Twilio-Signature` with your auth token; returns TwiML or JSON based
  on `Accept`.
- **Email webhook** (`POST /webhooks/email`) — Mailgun / SendGrid shape
  (form-encoded) plus JSON; extracts email from `"Name <a@b>"`.
- **Gmail IMAP poller** — background task when `WHEREIS_EMAIL_ADAPTER=imap`;
  skips silently if credentials look like placeholders; exponential backoff
  (cap 30 min) on auth errors; structured INFO log on first successful auth.

### Geocoding

- **Exact match** on `name` / `asciiname`.
- **FTS5 token/prefix match** (e.g. `Dod` → Dodoma).
- **Fuzzy match** via `rapidfuzz` with a Unicode-safe prefix filter; the
  similarity score (0..100) is carried through to `match_confidence`.
- **Regex mode** — `/^San .*/` runs inside SQLite via a user-defined
  `REGEXP` function and orders by population so demos pick the big cities first.

### Disambiguation (three strategies, one interface)

- `population` *(default)* — largest population wins.
- `proximity` — nearest to the person's last-known location.
- `first` — first hit.

Strategy is picked per-request with `?strategy=...`; invalid values return
422 thanks to a Pydantic `Literal`.

### Analytics

- **Time-travel** — `GET /whereis/{id}?at=<ISO-8601>` returns the most
  recent update ≤ timestamp.
- **Physics validator** — flags `implausible_speed` and `non_monotonic_time`
  between consecutive updates; opt-in hard-fail with `WHEREIS_PHYSICS_ENFORCE=true`
  (returns HTTP 422).
- **10 creative badges** — Most Distance, Biggest Homebody, Globe Trotter,
  Red-Eye Rocket (with sanity cap), Time Bender, Phantom, Groundhog Day,
  Jet-Lagger, Equator Crosser, The Phoenix.

### Output surface

- `GET /` — HTML form.
- `GET /whereis/{identifier}` — HTML (with `<meta>` status tag).
- `GET /whereis.txt` — tab-separated plaintext latest-locations (2G / `curl`-friendly).
- `GET /whereis.json` — machine-readable sibling.
- `GET /map` — Leaflet map; static `map_fallback.png` served when tiles fail
  or JavaScript is off.
- `GET /badges` + `GET /badges.json`.
- `GET /healthz` — liveness probe with row counts + active adapters.
- `GET /docs` — auto-generated OpenAPI UI.

### Security & ops

- **Shared-secret gate** — set `WHEREIS_SHARED_SECRET`, clients pass
  `X-Shared-Secret` on all webhook / API routes.
- **Twilio HMAC signature verification** — enabled by
  `WHEREIS_TWILIO_VERIFY_SIGNATURE=true` + `WHEREIS_TWILIO_AUTH_TOKEN`.
- **Deterministic fixture generator** — `python -m whereis.tools.generate_fixtures`,
  either direct-to-DB or against a running instance (honours the shared
  secret + Twilio signing automatically).
- **GitHub Actions CI** — ruff + pytest on every push.
- **Docker + docker-compose** — non-root image, `HEALTHCHECK`, named data
  volume, `.env` forwarded.

---

## Architecture

```
┌────────────────────────── routers/ (HTTP) ───────────────────────────┐
│   form.py   api.py   sms.py   email.py   query.py   map.py           │
│   badges.py   health.py                                              │
└──────────┬───────────────────────┬───────────────────────────────────┘
           │                       │
           │                       ▼
           │            ┌────────────────────────── adapters/ ─────────┐
           │            │   sms_twilio   sms_simulator                 │
           │            │   email_mailgun   email_imap                 │
           │            └──────────────────────────────────────────────┘
           │                       │   (InboundMessage DTO)
           ▼                       ▼
    ┌─────────────────────── services/ (domain) ──────────────────────┐
    │ parser.py    geocoder.py    strategies.py                       │
    │ validator.py ingest.py      history.py       badges.py          │
    └──────────┬──────────────────────────────────────────────────────┘
               ▼
    ┌────────────────────────── db.py + models.py ────────────────────┐
    │     SQLAlchemy 2.0 ORM  →  SQLite (+ FTS5, +REGEXP function)    │
    └─────────────────────────────────────────────────────────────────┘
```

**SOLID:**

- **S**ingle-responsibility: routers do HTTP only; adapters translate
  vendor payloads; services own business rules.
- **O**pen/closed: adding a new SMS provider means one new file in
  `adapters/`; a new disambiguation strategy means one class + a registry
  entry in `services/strategies.py`.
- **L**iskov / **I**SP: `MatchStrategy` is a one-method `Protocol`;
  `PhysicsRejected` is a clean subtype of `HTTPException`.
- **D**ependency inversion: `services.ingest.ingest(session, msg, strategy)`
  depends on abstractions, not concretes.

**KISS:** total source ~1,500 LOC; every module earns its place. Spatial
index was provisioned but removed once it became clear FTS candidate sets
are tiny and haversine in Python is plenty.

**DRY:** datetime parsing, ISO rendering, and display-name derivation live
in `utils.py`; `schemas.StrategyName` is a re-export of `config.StrategyName`.

---

## Tech stack & trade-offs

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | `Literal`, `from __future__ import annotations`, modern typing |
| Framework | FastAPI | OpenAPI for free, async-ready, excellent DX |
| DB | SQLite + FTS5 | Zero-ops, ships with Python, handles 1M+ rows at this scale. Swappable for Postgres via SQLAlchemy URL. |
| ORM | SQLAlchemy 2.0 | Typed models, connection-pool-friendly, migratable |
| Templating | Jinja2 + vanilla CSS | 5 KB form, no build step |
| Fuzzy | rapidfuzz | C-speed, no C toolchain at install time |
| Maps | Leaflet (CDN) + static fallback | Works online; degrades gracefully when it isn't |
| Testing | pytest + httpx TestClient | Fast, hermetic, isolated from `.env` |
| Lint | ruff | Fast, single-tool |

**Deliberately not used:** PostGIS, Redis, Celery, OpenAI-powered anything.
None are justified at this scale and they would increase the deployment
footprint disproportionately for a field-ops service.

**Scaling path** (discussed in the review): swap SQLite for Postgres 16,
replace FTS5 with `tsvector` + GIN, use PostGIS R-tree indexes if we ever
need kNN across >100k places per query, wrap the IMAP poller in a Celery
beat, and put the service behind a CDN for `/whereis.txt`.

---

## Repository layout

```
whereis-dimagi/
├── Dockerfile
├── docker-compose.yml
├── Makefile                        # install / seed / run / test / lint / fixtures
├── pyproject.toml                  # deps, pytest, ruff
├── README.md
├── TESTING.md                      # full end-to-end walkthrough
├── .env.example
├── .github/workflows/ci.yml        # ruff + pytest
├── data/                           # gitignored; holds cities15000.{zip,txt}, whereis.db
├── src/whereis/
│   ├── main.py                     # FastAPI app factory, lifespan, logger wiring
│   ├── config.py                   # pydantic-settings (WHEREIS_* env vars)
│   ├── db.py                       # engine, session, raw_connection, REGEXP
│   ├── models.py                   # Place, Person, LocationUpdate
│   ├── schemas.py                  # InboundMessage, *Out DTOs, Source, StrategyName
│   ├── security.py                 # require_shared_secret
│   ├── templating.py               # Jinja2Templates instance
│   ├── utils.py                    # parse_iso_utc, to_naive_utc, derive_display_name
│   ├── adapters/                   # sms_twilio, sms_simulator, email_mailgun, email_imap
│   ├── data/loader.py              # GeoNames download + SQLite ETL + FTS5 setup
│   ├── routers/                    # form, api, sms, email, query, map, badges, health
│   ├── services/                   # parser, geocoder, strategies, validator,
│   │                               # ingest, history, badges
│   ├── static/                     # style.css, map_fallback.png
│   ├── templates/                  # base, form, whereis, map, badges
│   └── tools/generate_fixtures.py  # demo-data generator
└── tests/                          # 62 tests: unit, integration, end-to-end
```

---

## Quick start

```bash
# 1. Clone and install into a local venv.
git clone https://github.com/cody-codes69/whereis-dimagi.git
cd whereis-dimagi
make install

# 2. Download + load the GeoNames dump (~3 MB, ~33,560 rows).
make seed

# 3. Run tests (optional but recommended).
make test

# 4. Start the server.
make run
# → http://localhost:8000
#   http://localhost:8000/docs   (OpenAPI)
```

Or with Docker:

```bash
docker compose up --build
```

---

## Configuration

All environment variables are prefixed `WHEREIS_`. Copy `.env.example` to
`.env` and edit what you need; tests ignore your `.env` entirely.

| Variable | Default | Notes |
|---|---|---|
| `WHEREIS_DB_PATH` | `data/whereis.db` | SQLite file path |
| `WHEREIS_GEONAMES_DUMP_URL` | `https://download.geonames.org/export/dump/cities15000.zip` | |
| `WHEREIS_GEONAMES_DUMP_FILE` | `cities15000.txt` | |
| `WHEREIS_DEFAULT_STRATEGY` | `population` | `population` \| `proximity` \| `first` |
| `WHEREIS_MAX_SPEED_KMH` | `950` | physics threshold |
| `WHEREIS_HOMEBODY_RADIUS_KM` | `200` | badge threshold |
| `WHEREIS_PHYSICS_ENFORCE` | `false` | `true` ⇒ 422 on implausible travel |
| `WHEREIS_SHARED_SECRET` | _(unset)_ | required `X-Shared-Secret` on API/webhooks |
| `WHEREIS_SMS_ADAPTER` | `simulator` | `simulator` \| `twilio` |
| `WHEREIS_TWILIO_AUTH_TOKEN` | — | enables Twilio HMAC signature check |
| `WHEREIS_TWILIO_VERIFY_SIGNATURE` | `false` | turn on for production Twilio use |
| `WHEREIS_EMAIL_ADAPTER` | `simulator` | `simulator` \| `mailgun` \| `imap` |
| `WHEREIS_IMAP_HOST` | `imap.gmail.com` | |
| `WHEREIS_IMAP_USER` | — | |
| `WHEREIS_IMAP_PASSWORD` | — | Gmail app password |
| `WHEREIS_IMAP_MAILBOX` | `INBOX` | |
| `WHEREIS_IMAP_POLL_SECONDS` | `60` | |

---

## HTTP surface

| Method + path | Purpose | Notes |
|---|---|---|
| `GET /` | HTML form | Works w/o JS |
| `POST /` | Form submit | Fields: `identifier`, `location`, `observed_at?`, `strategy?` |
| `GET /whereis/{identifier}` | HTML "whereis X?" | `?at=<ISO>` for time-travel; `<meta name="whereis-status">` reflects state |
| `GET /whereis.txt` | Plaintext dump | Tab-separated, `curl`-friendly |
| `GET /whereis.json` | JSON dump | Machine-readable sibling of `.txt` |
| `POST /updates` | JSON API | Accepts `UpdateIn`, `list[UpdateIn]`, or `list[list[...]]`; `?strategy=`; batch-committed |
| `POST /webhooks/sms` | Twilio webhook | HMAC-verified, TwiML or JSON response |
| `POST /webhooks/email` | Mailgun/SendGrid webhook | form-encoded or JSON |
| `GET /map` | Leaflet map | `?at=<ISO>` rewinds; falls back to static image |
| `GET /badges` + `GET /badges.json` | Creative awards | 10 slugs, in-process cache |
| `GET /healthz` | Liveness | Counts + adapters in JSON |
| `GET /docs`, `GET /openapi.json` | API UI & spec | |

Every `POST` route respects `X-Shared-Secret` when
`WHEREIS_SHARED_SECRET` is configured.

---

## Data model

```
persons                      places                          location_updates
─────────                    ──────                          ────────────────
id (pk)                      geonameid (pk)                  id (pk)
identifier UNIQ IDX          name IDX                        person_id FK→persons.id
display_name                 asciiname IDX                   observed_at IDX
created_at                   alternatenames (Text)           raw_input
                             country_code IDX                place_id FK→places.geonameid (nullable)
                             admin1                          lat, lng (nullable)
                             lat, lng                        source  (form|sms|email|api)
                             population                      match_confidence  (0..1)
                             timezone                        warnings  (JSON list)
```

Plus an FTS5 virtual table `places_fts(name, asciiname, alternatenames)`
with `content='places'` contentless-mapping, and a SQLite `REGEXP`
user-defined function registered on every connection.

---

## Ingestion pipeline

Every transport produces a single `InboundMessage` and calls one of:

- `services.ingest.ingest(session, msg, strategy=...)` — commits immediately.
  Used by single-row paths (form, SMS, email).
- `services.ingest.ingest_batch(session, msgs, strategy=...)` — flushes
  per row and commits once. Used by `POST /updates` to avoid N fsyncs.

Steps inside `_build_update`:

1. `find_or_create(Person)` — derives a display name from the identifier if
   none was provided (`anna.li@dimagi.com` → `"Anna Li"`).
2. `geocode(session, raw_location, ctx, strategy)` — exact → FTS5 →
   fuzzy → regex. Returns a `Match` with candidates, `how`, and `confidence`.
3. `validate_physics(...)` — flags `implausible_speed` and
   `non_monotonic_time` based on Haversine km ÷ hours vs `MAX_SPEED_KMH`.
4. If `PHYSICS_ENFORCE=true` and implausible, raise `PhysicsRejected` (422).
5. `session.add(LocationUpdate(...))`; commit once (or via batch caller).

---

## Disambiguation strategies

```python
class MatchStrategy(Protocol):
    name: str
    def pick(self, candidates: list[Place], ctx: LookupContext) -> Place | None: ...
```

- **PopulationStrategy** — `max(candidates, key=population)`.
- **ProximityStrategy** — `min(candidates, key=haversine_km(ctx.last, p))`;
  falls back to population if there's no prior update.
- **FirstHitStrategy** — `candidates[0]`.

Adding a new strategy:

```python
class MyStrategy:
    name = "mine"
    def pick(self, candidates, ctx): ...
# register once:
STRATEGIES["mine"] = MyStrategy()
# and add "mine" to StrategyName in config.py
```

---

## Badges (10)

| Slug | Awarded for |
|---|---|
| `most-distance` | Largest summed Haversine across legs |
| `biggest-homebody` | Highest share of updates within `HOMEBODY_RADIUS_KM` of centroid |
| `globe-trotter` | Most distinct country codes touched |
| `red-eye-rocket` | Fastest leg (with sanity cap 2500 km/h, min-Δt 60 s, excludes implausible legs) |
| `time-bender` | Most distinct IANA timezones |
| `phantom` | Longest gap between updates |
| `groundhog-day` | Most consecutive updates at the same place within 24 h |
| `jet-lagger` | Largest sum of `abs(tz_offset delta)` across consecutive updates |
| `equator-crosser` | Most hemisphere changes |
| `phoenix` | Longest *past* silence a person broke (uses `max(gaps[:-1])` to avoid tying Phantom) |

Results are cached on `(count, max_id)` of `location_updates` — invalidates
automatically on any write.

---

## Running live: Twilio + Gmail IMAP

1. Get a Twilio trial phone number + auth token, point your number's
   **Messaging webhook** at `https://<public-host>/webhooks/sms`
   (HTTP POST, URL-encoded).
2. Generate a Gmail **app password** (Google Account → Security → 2-step
   verification → App passwords).
3. Put them in `.env`:

    ```bash
    WHEREIS_SMS_ADAPTER=twilio
    WHEREIS_TWILIO_AUTH_TOKEN=<your token>
    WHEREIS_TWILIO_VERIFY_SIGNATURE=true

    WHEREIS_EMAIL_ADAPTER=imap
    WHEREIS_IMAP_USER=you@gmail.com
    WHEREIS_IMAP_PASSWORD="abcd efgh ijkl mnop"
    ```

4. Restart: `make run`.
   - `GET /healthz` now reports `"sms_adapter":"twilio","email_adapter":"imap"`.
   - The IMAP logger prints `[imap] connected as you@gmail.com, mailbox=INBOX, poll=60s` on first successful poll.
   - Unsigned POSTs to `/webhooks/sms` → 403; Twilio-signed → 200.

See [`TESTING.md`](./TESTING.md#live-mode-twilio--gmail-imap) for the full
live-mode demo, including expected console output and how to simulate a
Twilio signature with `curl`.

---

## Docker

```bash
docker compose up --build
```

Characteristics:

- **Non-root** (`USER nobody`).
- `HEALTHCHECK CMD curl -fsS http://127.0.0.1:8000/healthz`.
- DB persisted in a **named volume** (`whereis-data`) — no host dir to
  create.
- `.env` is forwarded via `env_file: { path: .env, required: false }` so
  you can turn on live mode without changing compose.
- Seeds the GeoNames dump on container startup
  (`python -m whereis.data.loader && uvicorn ...`).

---

## Development

Common commands (all via `make`):

| Command | Does |
|---|---|
| `make install` | Create `.venv`, `pip install -e .[dev]` |
| `make seed` | Download + load GeoNames `cities15000` |
| `make run` | Launch uvicorn with auto-reload |
| `make test` | Run the full `pytest` suite |
| `make lint` | Run `ruff check src tests` |
| `make fixtures` | Generate 20 deterministic demo updates |
| `make docker` | `docker compose up --build` |
| `make clean` | Wipe venv, caches, DB |

Python entry points (also exposed as console scripts after `pip install -e .`):

```bash
whereis-seed         # == python -m whereis.data.loader
whereis-fixtures     # == python -m whereis.tools.generate_fixtures
```

---

## Testing

**62 tests, all green, ~1 s** (pytest + httpx `TestClient`):

```
tests/
├── test_parser.py                 4 tests   # body/date parsing
├── test_geocoder.py              10 tests   # exact / FTS / fuzzy / regex + API confidence & regex ordering
├── test_strategies.py             7 tests   # pop / proximity / first + StrategyName re-export
├── test_validator.py              5 tests   # physics warnings + enforce-422 via API
├── test_badges.py                 5 tests   # unit badges + Red-Eye/Phoenix regression + all slugs
├── test_query_as_of.py            7 tests   # time-travel, /healthz, /whereis.json, ISO-Z, unknown meta
├── test_api_form.py              10 tests   # HTML form, /updates batch & strategy, shared-secret, tab /whereis.txt
├── test_api_sms.py                5 tests   # webhook, TwiML escape, JSON Accept, display name
├── test_api_email.py              4 tests   # mailgun JSON/form + simulator module removed
└── test_end_to_end.py             5 tests   # physics warning, map+badges, R*Tree migration, fixture auth
```

Tests are **fully isolated from `.env`** — `conftest.py` wipes `WHEREIS_*`
env vars and instantiates `Settings(_env_file=None)` before anything
imports the app. So `make test` works even when you have live Twilio or
IMAP credentials on disk.

For a step-by-step manual test walkthrough covering every endpoint, see
**[TESTING.md](./TESTING.md)**.

---

## Troubleshooting

| Symptom | Likely cause & fix |
|---|---|
| `sqlite3.OperationalError: no such table: places_fts` | You didn't run `make seed`. |
| `make seed` fails to download | Check your connection; the dump is at `https://download.geonames.org/export/dump/cities15000.zip`. You can also seed by dropping the file into `data/cities15000.txt` manually. |
| Webhooks return 401 | `WHEREIS_SHARED_SECRET` is set; clients must send `X-Shared-Secret`. |
| SMS webhook returns 403 | `WHEREIS_TWILIO_VERIFY_SIGNATURE=true`. Either turn it off or send a valid `X-Twilio-Signature` HMAC of the POST body. |
| IMAP poller silently does nothing | Your creds look like placeholders (contain `<`, `your-`, `app-password`, etc.) or are missing. See the `[imap] skipping poll loop` warning at startup. |
| Map renders a gray box | No internet → tile CDN failed; Leaflet's `onerror` swaps in `static/map_fallback.png`. |
| Tests fail with `ModuleNotFoundError: whereis` | You skipped `pip install -e .`; run `make install`. |

---

## Roadmap

Nice-to-haves beyond the exercise, intentionally not shipped:

- Postgres + PostGIS deployment target (config flip; FTS replaced with `tsvector`).
- Per-person audit trail at `/whereis/{id}/history`.
- Rate-limiting on webhook routes.
- Alerting when a person triggers `phantom` threshold.
- PWA / offline-first front end.
- Badge history (not just current leader) with dated ledger.
- First-class `Depends(settings)` injection to replace `_config_mod.settings`
  indirection used for test-time monkeypatching.

---

## License & credits

- Exercise code — do what you like with it.
- GeoNames data — © GeoNames, licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Map tiles (when online) — © OpenStreetMap contributors.
- Map fallback image — the screenshot provided with the exercise.
