from __future__ import annotations

import os
import re
import time
from functools import lru_cache
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from database import engine, fetch_rows

# Mounted under /chat/... so the existing nginx `location /chat` already proxies it.
router = APIRouter(prefix="/chat/faculty-edit")

FACULTY_FIELDS = [
    "name", "email", "phone", "cabin", "designation",
    "qualification", "phd_subject", "college", "research_interest",
]
TT_FIELDS = [
    "day_of_week", "start_time", "end_time", "subject",
    "school", "branch", "division", "group_name", "classroom", "semester",
]
TT_PK = "timetable_id"   # primary key column of the timetable table
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MAX_LEN = 255
EDIT_PURPOSE = "academic-edit"

_used_jti: dict[str, float] = {}  # single-use edit tokens (single-instance deploy)


# ── auth ────────────────────────────────────────────────────────────────────
def _decode(token: str) -> dict:
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])


def _faculty_claims(authorization: Optional[str], cookie: Optional[str]) -> dict:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif cookie:
        token = cookie
    if not token:
        raise HTTPException(401, "Authentication required.")
    try:
        claims = _decode(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired session.")
    if str(claims.get("role", "")).lower() != "faculty":
        raise HTTPException(403, "Only faculty accounts can edit data.")
    return claims


def _norm_name(s: str) -> str:
    s = re.sub(r"\b(dr|prof|mr|mrs|ms)\b\.?", " ", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@lru_cache(maxsize=1)
def _columns(table: str) -> dict[str, str]:
    """{column: data_type} straight from the DB, so allow-lists never name a missing column."""
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT column_name, data_type FROM information_schema.columns "
                 "WHERE table_schema='public' AND table_name=:t"), {"t": table},
        ).all()
    return {r[0]: r[1] for r in rows}


def _my_faculty(claims: dict) -> dict[str, Any]:
    """Map the logged-in user to exactly one faculty row, or refuse."""
    rows = fetch_rows("faculty")
    username = str(claims.get("username") or "").strip().lower()
    # Preferred: explicit link column faculty.login_username (see README steps).
    if "login_username" in _columns("faculty"):
        hit = [r for r in rows if str(r.get("login_username") or "").strip().lower() == username]
        if len(hit) == 1:
            return hit[0]
    # Fallback: unique exact match between login display name and faculty.name.
    want = _norm_name(claims.get("name") or "")
    hit = [r for r in rows if want and _norm_name(r.get("name")) == want]
    if len(hit) == 1:
        return hit[0]
    raise HTTPException(403, "Could not link your login to a single faculty record.")


# ── validation ──────────────────────────────────────────────────────────────
def _mins(v: Any) -> Optional[int]:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(v or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _clean(table: str, col: str, raw: Any, old: Any) -> str:
    v = str(raw).strip()
    if not v:
        raise HTTPException(422, f"'{col}' cannot be empty.")
    if len(v) > MAX_LEN:
        raise HTTPException(422, f"'{col}' is too long.")
    if col == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
        raise HTTPException(422, "Enter a valid email address.")
    if col == "day_of_week":
        if v.lower() not in DAYS:
            raise HTTPException(422, "Day must be Monday–Sunday.")
        return v.title()
    if col in ("start_time", "end_time"):
        m = _mins(v)
        if m is None or m >= 24 * 60:
            raise HTTPException(422, f"'{col}' must look like 09:00.")
        out = f"{m // 60:02d}:{m % 60:02d}"
        return out + ":00" if str(old or "").count(":") == 2 else out
    if col == "semester" and not re.fullmatch(r"\d{1,2}", v):
        raise HTTPException(422, "Semester must be a number.")
    return v


def _check_clash(fid: Any, row_id: Any, new: dict[str, Any]) -> None:
    mine = [r for r in fetch_rows("timetable") if str(r.get("faculty_id")) == str(fid)
            and str(r.get(TT_PK)) != str(row_id)]
    day = str(new.get("day_of_week", "")).lower()
    s, e = _mins(new.get("start_time")), _mins(new.get("end_time"))
    if s is None or e is None:
        return
    if e <= s:
        raise HTTPException(422, "End time must be after start time.")
    for r in mine:
        rs, re_ = _mins(r.get("start_time")), _mins(r.get("end_time"))
        if str(r.get("day_of_week", "")).lower() == day and rs is not None and s < re_ and rs < e:
            raise HTTPException(409, f"Clashes with your other lecture on {r['day_of_week']} "
                                     f"({r['start_time']}–{r['end_time']}).")


def _redeem_edit_token(token: Optional[str], claims: dict) -> None:
    if not token:
        raise HTTPException(401, "Password confirmation required.")
    try:
        t = _decode(token)
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Password confirmation expired. Please confirm again.")
    if t.get("purpose") != EDIT_PURPOSE or str(t.get("sub")) != str(claims.get("sub")):
        raise HTTPException(401, "Invalid confirmation token.")
    now = time.time()
    for k in [k for k, exp in _used_jti.items() if exp < now]:
        del _used_jti[k]
    jti = str(t.get("jti") or "")
    if not jti or jti in _used_jti:
        raise HTTPException(401, "Confirmation already used. Please confirm again.")
    _used_jti[jti] = float(t.get("exp", now + 120))


# ── routes ──────────────────────────────────────────────────────────────────
class UpdateBody(BaseModel):
    target: str                      # "faculty" | "timetable"
    row_id: Optional[str] = None     # timetable row id (must belong to caller)
    changes: dict[str, str]


@router.get("/me")
def me(authorization: Optional[str] = Header(default=None),
       authToken: Optional[str] = Cookie(default=None)):
    claims = _faculty_claims(authorization, authToken)
    fac = _my_faculty(claims)
    fcols, tcols = _columns("faculty"), _columns("timetable")
    tt = [r for r in fetch_rows("timetable") if str(r.get("faculty_id")) == str(fac["id"])]
    order = {d: i for i, d in enumerate(DAYS)}
    tt.sort(key=lambda r: (order.get(str(r.get("day_of_week", "")).lower(), 9), _mins(r.get("start_time")) or 0))
    return {
        "faculty": {k: ("" if fac.get(k) is None else str(fac.get(k))) for k in FACULTY_FIELDS if k in fcols},
        "faculty_fields": [f for f in FACULTY_FIELDS if f in fcols],
        "timetable": [
            {"id": r.get(TT_PK), **{k: ("" if r.get(k) is None else str(r.get(k)))
                                    for k in TT_FIELDS if k in tcols}} for r in tt
        ],
        "timetable_fields": [f for f in TT_FIELDS if f in tcols],
    }


@router.post("/update")
def update(body: UpdateBody,
           authorization: Optional[str] = Header(default=None),
           authToken: Optional[str] = Cookie(default=None),
           x_edit_token: Optional[str] = Header(default=None)):
    claims = _faculty_claims(authorization, authToken)
    fac = _my_faculty(claims)
    fid = fac["id"]

    if body.target not in {"faculty", "timetable"}:
        raise HTTPException(400, "Unknown target.")
    allowed = FACULTY_FIELDS if body.target == "faculty" else TT_FIELDS
    types = _columns(body.target)
    changes = {k: v for k, v in body.changes.items() if k in allowed and k in types}
    if not changes or len(changes) != len(body.changes):
        raise HTTPException(400, "No valid fields to change.")

    # Current row (ownership enforced here, not trusted from the client).
    if body.target == "faculty":
        current = fac
    else:
        current = next((r for r in fetch_rows("timetable")
                        if str(r.get(TT_PK)) == str(body.row_id) and str(r.get("faculty_id")) == str(fid)), None)
        if current is None:
            raise HTTPException(404, "That lecture is not in your timetable.")

    clean = {k: _clean(body.target, k, v, current.get(k)) for k, v in changes.items()}
    if body.target == "timetable":
        merged = {**{k: current.get(k) for k in TT_FIELDS}, **clean}
        _check_clash(fid, body.row_id, merged)

    _redeem_edit_token(x_edit_token, claims)   # only after validation, so typos don't burn it

    # Column names are allow-listed above; types come from information_schema.
    sets = ", ".join(f'"{c}" = CAST(:v_{i} AS {types[c]})' for i, c in enumerate(clean))
    params: dict[str, Any] = {f"v_{i}": v for i, v in enumerate(clean.values())}
    if body.target == "faculty":
        sql = f'UPDATE "faculty" SET {sets} WHERE id::text = :fid RETURNING *'
        params["fid"] = str(fid)
    else:
        sql = (f'UPDATE "timetable" SET {sets} '
               f'WHERE "{TT_PK}"::text = :rid AND faculty_id::text = :fid RETURNING *')
        params.update(rid=str(body.row_id), fid=str(fid))

    with engine.begin() as conn:       # commits on success -> chatbot sees it on the next query
        row = conn.execute(text(sql), params).mappings().first()
    if row is None:
        raise HTTPException(404, "Nothing was updated.")
    return {"status": "updated", "changed": list(clean.keys())}
