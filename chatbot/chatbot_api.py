from fastapi import FastAPI, Header, HTTPException, Cookie, UploadFile, File
from google import genai
from google.genai import types
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from academic_helpers import (
    ConversationState, is_greeting, is_academic_query,
    _name_tokens, _append_history,
)
from llama_handler import LlamaHandler
from langfuse_integration import tracker
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

import jwt

app = FastAPI()


_allowed_origins = [
    o.strip() for o in os.environ.get("FRONTEND_ORIGIN", "http://localhost").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from faculty_edit import router as faculty_edit_router
app.include_router(faculty_edit_router)


def _verify_token(token: str) -> dict:
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])


def _authenticate(authorization: Optional[str], auth_cookie: Optional[str]) -> dict:
    """Accept the session either via httpOnly cookie (normal browser flow)
    or an Authorization: Bearer header (useful for non-browser/API clients).
    """
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif auth_cookie:
        token = auth_cookie

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        return _verify_token(token)
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")

# Academic records are queried live through MCP tools backed by PostgreSQL.
# Single shared instance for the whole process lifetime — this is what makes
# the persistent MCP session in LlamaHandler actually pay off. Do NOT
# instantiate a new LlamaHandler per-request, or every request pays the
# subprocess-spawn + initialize() cost again.
llama_handler   = LlamaHandler()
use_llm = LlamaHandler.is_available()
genai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# ── "my lecture" / "right now" personalization ─────────────────────────────
IST = ZoneInfo("Asia/Kolkata")

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_RELATIVE_DAY_RE = re.compile(r"\b(today|tonight|tomorrow|yesterday)\b", re.IGNORECASE)
_NOW_RE = re.compile(r"\b(right now|just now|at the moment|currently|now)\b", re.IGNORECASE)
_FIRST_PERSON_RE = re.compile(r"\b(my|mine|me|i|myself)\b", re.IGNORECASE)
_POSSESSIVE_FIRST_PERSON_RE = re.compile(r"\b(my|mine)\b", re.IGNORECASE)


_SEM_RE = re.compile(
    r"\bsem(?:ester)?\.?\s*-?\s*(\d)\b|\b(\d)(?:st|nd|rd|th)\s*sem",
    re.IGNORECASE,
)


def _requested_sem(question: str) -> Optional[int]:
    m = _SEM_RE.search(question)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def _personalize_query(question: str, user_name: str | None) -> str:
    """Rewrite pronouns/relative time into concrete text the existing
    name + day/time matching in mapping_handler already understands.

    - "my" / "mine"           -> the logged-in user's name
    - "today" / "tonight"     -> current weekday name
    - "tomorrow" / "yesterday"-> relative weekday name
    - "now" / "right now" /
      "currently" / etc.      -> current HH:MM (IST), plus today's weekday
                                  if no day was already mentioned
    """
    q = question
    now = datetime.now(IST)

    def _day_repl(m: "re.Match[str]") -> str:
        word = m.group(1).lower()
        if word in ("today", "tonight"):
            return now.strftime("%A")
        if word == "tomorrow":
            return (now + timedelta(days=1)).strftime("%A")
        return (now - timedelta(days=1)).strftime("%A")  # yesterday

    q = _RELATIVE_DAY_RE.sub(_day_repl, q)

    if _NOW_RE.search(q):
        q = _NOW_RE.sub(now.strftime("%H:%M"), q)
        if not re.search(r"\b(" + "|".join(_DAY_NAMES) + r")\b", q, re.IGNORECASE):
            q = f"{q} {now.strftime('%A')}"

    if user_name and user_name.strip():
        identity = user_name.strip()
        # Keep subject/object pronouns natural for the LLM, while still
        # making ownership queries such as "my timetable" searchable.
        q = _POSSESSIVE_FIRST_PERSON_RE.sub(identity, q)
        if _FIRST_PERSON_RE.search(question):
            q = f'{q} [The first-person speaker is {identity}; "I", "me", "my", "mine", and "myself" refer to this user.]'

    return q


# Per-session state (keyed by session_id)
sessions: dict = {}

def get_session(session_id: str):
    if session_id not in sessions:
        sessions[session_id] = {
            "history": [],
            "state": ConversationState(),
            "cancelled_requests": set(),
        }
    return sessions[session_id]


def _remove_request_history(history: list, request_id: str) -> None:
    history[:] = [
        item for item in history
        if item.get("request_id") != request_id
    ]


# ── Request/response schemas ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: Optional[str] = None
    session_id: str = "default"
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    trace_id: Optional[str] = None


class ResetRequest(BaseModel):
    session_id: str = "default"

class CancelRequest(BaseModel):
    session_id: str = "default"
    request_id: str

class FeedbackRequest(BaseModel):
    trace_id: str
    rating: str

class TranscribeResponse(BaseModel):
    text: str


class ResetResponse(BaseModel):
    status: str


@app.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(default=None),
    authToken: Optional[str] = Cookie(default=None),
):
    claims = _authenticate(authorization, authToken)

    role = str(claims.get("role") or "").strip().lower()
    allowed_sem = claims.get("allowed_sem")
    if role not in {"student", "faculty", "admin"}:
        raise HTTPException(status_code=403, detail="Unsupported account role.")
    if role == "student" and allowed_sem not in {5, 7}:
        raise HTTPException(status_code=403, detail="Student account has no valid semester scope.")
    if role != "student":
        allowed_sem = None

    user_q     = (body.message or "").strip()
    session_id = body.session_id or "default"
    user_id    = str(claims.get("username") or claims.get("sub") or "").strip().lower()
    user_name  = claims.get("name")

    if not user_q:
        return ChatResponse(reply="Please type a message.")

    # Resolve "my"/"mine" to the logged-in user's name, and "now"/"today"/etc.
    # to a concrete day/time, before anything else looks at the question.
    resolved_q = _personalize_query(user_q, user_name)

    sess    = get_session(session_id)
    history = sess["history"]
    state   = sess["state"]
    request_id = body.request_id or ""

    history.append({"role": "user", "content": resolved_q, "request_id": request_id})

    langfuse_trace_id = None
    with tracker.trace(
        name="handle-chatbot-message",
        input_str=resolved_q,
        session_id=session_id,
        user_id=user_id,
        tags=["qa-chatbot"]
    ) as trace:
        if trace is not None:
            langfuse_trace_id = (
                getattr(trace, "trace_id", None)
                or getattr(trace, "id", None)
            )
        if user_q.lower() in {"exit", "quit", "bye"}:
            reply = "Bye! Have a great day!"

        elif is_greeting(resolved_q):
            reply = "Hi! How can I help you with student and faculty info?"

        elif (
            not is_academic_query(resolved_q)
            and not _name_tokens(resolved_q)
            and not state.pending_matches
            and not re.fullmatch(r"\s*\d+\s*", resolved_q)
        ):
            reply = "I'm designed only for academic queries about PDEU students and faculty."

       
        elif (
            role == "student"
            and allowed_sem is not None
            and (requested_sem := _requested_sem(resolved_q)) is not None
            and requested_sem != int(allowed_sem)
        ):
            reply = (
                f"You're only able to view semester {allowed_sem} student data. "
                f"Faculty information is always available."
            )

        elif use_llm:
            
            reply = await llama_handler.handle(
                resolved_q, history[:-1], trace_id=None,
                role=role, allowed_sem=allowed_sem, user_name=user_name,
            ) or "I couldn't generate an answer. Please try rephrasing."

        else:
            reply = "I could not find that information in the database."

        if request_id in sess["cancelled_requests"]:
            _remove_request_history(history, request_id)
            return ChatResponse(reply="", trace_id=langfuse_trace_id)

        if trace:
            trace.update(output=reply)

    if request_id in sess["cancelled_requests"]:
        _remove_request_history(history, request_id)
        return ChatResponse(reply="", trace_id=langfuse_trace_id)

    history.append({"role": "bot", "content": reply, "request_id": request_id})
    return ChatResponse(reply=reply, trace_id=langfuse_trace_id)


@app.post("/feedback", response_model=ResetResponse)
def feedback(
    body: FeedbackRequest,
    authorization: Optional[str] = Header(default=None),
    authToken: Optional[str] = Cookie(default=None),
):
    _authenticate(authorization, authToken)
    rating = body.rating.strip().lower()
    if rating not in {"good", "bad"}:
        raise HTTPException(status_code=400, detail="Rating must be 'good' or 'bad'.")
    if not body.trace_id.strip():
        raise HTTPException(status_code=400, detail="A trace_id is required.")
    tracker.record_feedback(body.trace_id, rating)
    return ResetResponse(status="recorded")


@app.post("/cancel", response_model=ResetResponse)
def cancel(
    body: CancelRequest,
    authorization: Optional[str] = Header(default=None),
    authToken: Optional[str] = Cookie(default=None),
):
    _authenticate(authorization, authToken)
    session_id = body.session_id or "default"
    sess = get_session(session_id)
    sess["cancelled_requests"].add(body.request_id)
    _remove_request_history(sess["history"], body.request_id)
    return ResetResponse(status="cancelled")


@app.post("/reset", response_model=ResetResponse)
def reset(
    body: ResetRequest,
    authorization: Optional[str] = Header(default=None),
    authToken: Optional[str] = Cookie(default=None),
):
    # Require a valid session so a guessed/sniffed session_id alone can't be
    # used to wipe someone else's in-progress conversation.
    _authenticate(authorization, authToken)
    session_id = body.session_id or "default"
    if session_id in sessions:
        del sessions[session_id]
    return ResetResponse(status="reset")

@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    authorization: Optional[str] = Header(default=None),
    authToken: Optional[str] = Cookie(default=None),
):
    _authenticate(authorization, authToken)
    audio_bytes = await audio.read()

    resp = genai_client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            "Transcribe the following speech segment in its original language. "
            "Only output the transcription, with no extra commentary.",
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/webm"),
        ],
    )
    return TranscribeResponse(text=resp.text.strip())


@app.on_event("shutdown")
async def _shutdown_llama_handler():
    """Close the persistent MCP subprocess/session cleanly when the API
    process shuts down, instead of leaving mcp_tools.py orphaned."""
    await llama_handler.close()


if __name__ == "__main__":
    import uvicorn
    print(f"[OK] LLM {'ON' if use_llm else 'OFF - mapping only'}")
    print("[OK] Chatbot API running on http://localhost:5001")
    uvicorn.run(app, host="0.0.0.0", port=5001)
