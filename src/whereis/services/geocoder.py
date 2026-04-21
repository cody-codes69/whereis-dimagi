"""Geocoding pipeline: exact -> FTS5 -> fuzzy -> regex.

The geocoder returns a ranked list of candidate ``Place`` rows. A
``MatchStrategy`` decides which one wins when multiple are plausible.
``Match.confidence`` reflects both how the match was found and (for fuzzy)
the rapidfuzz similarity score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from ..models import Place
from .strategies import LookupContext, MatchStrategy

_FTS_SAFE = re.compile(r"[^\w\s\-]", flags=re.UNICODE)
_MAX_FUZZY_CANDIDATES = 40
_FTS_LIMIT = 20
_REGEX_LIMIT = 500  # REGEXP scans the full table; cap high but bounded.
_FUZZY_SCAN_LIMIT = 2000
_FUZZY_MIN_SCORE = 80


@dataclass(frozen=True)
class Match:
    place: Place | None
    candidates: list[Place]
    confidence: float  # 0.0 .. 1.0
    how: str = ""  # "exact" | "fts" | "fuzzy" | "regex" | ""

    @classmethod
    def none(cls) -> Match:
        return cls(None, [], 0.0, "")


def _exact(session: Session, q: str) -> list[Place]:
    rows = session.scalars(
        select(Place).where((Place.name == q) | (Place.asciiname == q))
    ).all()
    return list(rows)


def _fts_search(session: Session, q: str) -> list[Place]:
    safe = _FTS_SAFE.sub(" ", q).strip()
    if not safe:
        return []
    tokens = [t for t in safe.split() if t]
    if not tokens:
        return []
    match_expr = " ".join(f'"{t}"*' for t in tokens)
    rows = session.execute(
        text("SELECT rowid FROM places_fts WHERE places_fts MATCH :q LIMIT :lim"),
        {"q": match_expr, "lim": _FTS_LIMIT},
    ).scalars().all()
    if not rows:
        return []
    return list(session.scalars(select(Place).where(Place.geonameid.in_(rows))).all())


def _fuzzy(session: Session, q: str) -> tuple[list[Place], float]:
    """Return (top matches, best score 0..100). Unicode-safe prefix filter."""
    head = q[:1].lower()
    if not head:
        return [], 0.0
    head_hi = head + "\uffff"  # open-ended upper bound for range scan
    candidates = session.scalars(
        select(Place)
        .where(or_(
            func.lower(Place.asciiname).between(head, head_hi),
            func.lower(Place.name).between(head, head_hi),
        ))
        .limit(_FUZZY_SCAN_LIMIT)
    ).all()
    scored = sorted(
        ((max(fuzz.WRatio(q.lower(), p.asciiname.lower()),
              fuzz.WRatio(q.lower(), p.name.lower())), p)
         for p in candidates),
        key=lambda t: t[0],
        reverse=True,
    )
    top = [p for score, p in scored[:_MAX_FUZZY_CANDIDATES] if score >= _FUZZY_MIN_SCORE]
    best = scored[0][0] if scored else 0.0
    return top, best


def _regex(session: Session, pattern: str) -> list[Place]:
    try:
        re.compile(pattern)
    except re.error:
        return []
    rows = session.scalars(
        select(Place)
        .where(or_(
            Place.name.op("REGEXP")(pattern),
            Place.asciiname.op("REGEXP")(pattern),
        ))
        .order_by(Place.population.desc())
        .limit(_REGEX_LIMIT)
    ).all()
    return list(rows)


def geocode(session: Session, query: str, ctx: LookupContext, strategy: MatchStrategy) -> Match:
    q = (query or "").strip()
    if not q:
        return Match.none()

    # Regex mode: /pattern/
    if q.startswith("/") and q.endswith("/") and len(q) >= 3:
        candidates = _regex(session, q[1:-1])
        return _resolve(candidates, ctx, strategy, how="regex", base_conf=0.6)

    candidates = _exact(session, q)
    if candidates:
        return _resolve(candidates, ctx, strategy, how="exact", base_conf=1.0)

    candidates = _fts_search(session, q)
    if candidates:
        return _resolve(candidates, ctx, strategy, how="fts", base_conf=0.85)

    fuzzy_cands, best_score = _fuzzy(session, q)
    if fuzzy_cands:
        # Map rapidfuzz 80..100 -> 0.5..0.85 band.
        conf = 0.5 + (best_score - _FUZZY_MIN_SCORE) / (100 - _FUZZY_MIN_SCORE) * 0.35
        return _resolve(fuzzy_cands, ctx, strategy, how="fuzzy", base_conf=conf)

    return Match.none()


def _resolve(
    candidates: list[Place],
    ctx: LookupContext,
    strategy: MatchStrategy,
    *,
    how: str,
    base_conf: float,
) -> Match:
    if not candidates:
        return Match.none()
    if len(candidates) == 1:
        return Match(candidates[0], candidates, min(base_conf, 1.0), how)
    choice = strategy.pick(candidates, ctx)
    # Disambiguation costs a little confidence.
    return Match(choice, candidates, max(0.0, base_conf - 0.15), how)
