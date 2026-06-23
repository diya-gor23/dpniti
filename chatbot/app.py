from __future__ import annotations
import os
import re
import pickle
import json
import difflib
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False

from openai import OpenAI

import time
from dotenv import load_dotenv
load_dotenv()

# ── Observability ─────────────────────────────────────────────────────────────
from langfuse_integration import tracker, trace_function
# ─────────────────────────────────────────────────────────────────────────────

#####  CONFIG
DEBUG              = False                             # Set to True to see debug info
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = "openrouter/free"                 # Free model — ends with :free

SQL_DUMP_PATH   = "dpniti.sql"
TOP_K           = 4
MAX_CONTEXT_CHARS = 20000

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
FAISS_INDEX_PATH = "faiss_index.bin"
FAISS_DOCS_PATH  = "faiss_docs.pkl"

QUERY_STOPWORDS: frozenset = frozenset({
    "who", "is", "are", "what", "which", "roll", "rollno", "roll_no", "no",
    "number", "numbers", "division", "divisions", "div", "divs", "group",
    "groups", "grp", "grps", "batch", "batches", "class", "classes", "for",
    "student", "students", "faculty", "faculties", "professor", "professors",
    "teacher", "teachers", "email", "mail", "phone", "contact", "mobile",
    "cabin", "office", "location", "designation", "department", "dept",
    "qualification", "phd", "research", "resarch", "reseach",
    "reasearch", "resesarch", "rsearch", "interest", "intrest", "intrst",
    "interst", "college", "timetable", "schedule", "post", "title", "of",
    "the", "please", "detail", "details", "info", "information", "can",
    "tell", "give", "all", "about", "find", "get", "me", "us", "you",
    "just", "name", "names", "only", "list", "show", "any", "with", "from",
    "this", "that", "his", "her", "their", "a", "an", "in", "on", "at",
    "to", "and", "or", "by", "his", "her", "hers", "theirs", "my", "mine",
    "our", "ours", "your", "yours",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "today", "tomorrow", "yesterday", "week", "daily", "weekly",
    "dr", "mr", "ms", "mrs", "prof", "sir", "maam", "madam", "mam"
})

ROLL_RE = re.compile(r"\b(\d{2}bcp\d+[a-z]?)\b", re.IGNORECASE)

DEFAULT_WEIGHTS: Dict[str, float] = {
    "token_overlap":  2.0,
    "field_exact":    3.0,
    "semantic_blend": 1.5,
}

FACULTY_KEYWORDS: List[str] = [
    "faculty", "faculties", "professor", "professors",
    "teacher", "teachers", "staff", "lecturer", "lecturers",
]

STUDENT_KEYWORDS: List[str] = [
    "student", "students", "learner", "learners",
]

##### System prompt used by LLM for all its answers
SYSTEM_PROMPT = """You are a friendly academic assistant for PDEU (Pandit Deendayal Energy University).
You ONLY answer using the DATABASE RECORDS provided in each message. Never use outside knowledge.

STRICT RULES:
1. Never invent or guess data - names, roll numbers, emails, phones, cabins, etc.
2. If the answer is not in the records, say exactly: "I don't have that information in the database."
3. Keep answers natural and conversational - like a helpful college staff member.
4. For lists (students in a division, faculty list, etc.) number each item clearly.
5. Never answer questions outside the academic database scope (no general knowledge, no coding help).
6. If a user greets you, reply warmly and ask how you can help.
7. If multiple records match, list all of them clearly.
8. For timetable data, always present it day-by-day in a readable format.
9. Never use raw field names - use plain English. E.g. "Roll Number" not "roll_no".
10. Never repeat information already given unless asked again.
11. For "free slot" queries: look at ALL timetable records for the person, find all busy slots, then list working hours (9:00-17:00) NOT covered as free slots.
12. For "same division" queries: compare the Division field of both students and answer yes/no with their division names.
13. For "first/last roll no" queries: sort all student records in the division alphanumerically by roll number and return the first or last.
14. For "who teaches X subject" or "which subject does X teach": scan ALL timetable records and list every faculty-division-subject combination found.
15. For "who is in room/cabin X": check both classroom field in timetable AND cabin field in faculty records.
16. For "who teaches X in all divisions" or "who teaches X": list EVERY faculty member who teaches that subject along with which division(s) they teach it in. Do NOT say no one teaches it if records exist.

DIVISION & GROUP FORMAT:
- Divisions: "Div-1", "Div-2" etc. Present as "Division 1", "Division 2".
- Groups: "G1", "G2", "G1G2" etc. Present as "Group 1", "Group 2".

IMPORTANT - For cross-table questions always:
- Match faculty_id in timetable to faculty name in faculty records
- List ALL matching records, not just the first one
- If multiple faculty teach the same subject, list ALL of them
- Do NOT say "I don't have that information" if the timetable records contain it
"""

#####  SHARED HELPERS
def _safe_text(v: Any) -> str:
    if v is None:
        return "Not available"
    t = str(v).strip()
    return t if t else "Not available"

def _name_tokens(text: str) -> List[str]:
    return [
        w for w in re.findall(r"[a-z]+", text.lower())
        if w not in QUERY_STOPWORDS and len(w) >= 2
    ]

def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"[a-zA-Z0-9]+", text.lower()))

def _clean_subject_name(raw: str) -> str:
    return re.sub(r"^\d+[A-Z]+\d+[A-Z]*\s*[-–]\s*", "", raw).strip()

def _normalize_key(v: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower().strip())

def _split_group_components(v: Any) -> Set[str]:
    raw = str(v or "").lower().strip()
    c = set(re.findall(r"g\d+", raw))
    return c if c else ({_normalize_key(raw)} if _normalize_key(raw) else set())

def _extract_division_keys(query: str) -> Set[str]:
    return {
        f"div{m.group(1)}"
        for m in re.finditer(r"\b(?:div(?:ision)?)[\s\-]*(\d{1,2})\b", query.lower())
    }

def _extract_group_keys(query: str) -> Set[str]:
    q = query.lower()
    keys: Set[str] = {m.group(0) for m in re.finditer(r"\bg\d+(?:g\d+)?\b", q)}
    keys |= {
        f"g{m.group(1)}"
        for m in re.finditer(r"\b(?:group|grp|batch)[\s\-]*(\d{1,2})\b", q)
    }
    return keys

def _extract_day_filters(query: str) -> Set[str]:
    days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    return {d for d in days if d in query.lower()}

def _time_to_minutes(v: Any) -> Optional[int]:
    t = str(v or "").strip().lower()
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", t)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        return hh * 60 + mm if 0 <= hh <= 23 and 0 <= mm <= 59 else None
    m2 = re.match(r"^(\d{1,2})\s*(am|pm)$", t)
    if not m2:
        return None
    hh = int(m2.group(1))
    if m2.group(2) == "am":
        hh = 0 if hh == 12 else hh
    else:
        hh = 12 if hh == 12 else hh + 12
    return hh * 60

def _extract_time_filters(query: str) -> List[int]:
    q, times = query.lower(), []
    for m in re.finditer(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", q):
        times.append(int(m.group(1)) * 60 + int(m.group(2)))
    for m in re.finditer(r"\b(\d{1,2})\s*(am|pm)\b", q):
        t = _time_to_minutes(f"{m.group(1)} {m.group(2)}")
        if t is not None:
            times.append(t)
    if not times:
        for m in re.finditer(r"\b(?:at|around|by|after|before|from)\s+(\d{1,2})\b", q):
            hh = int(m.group(1))
            if 0 <= hh <= 23:
                times.append(hh * 60)
    seen: Set[int] = set()
    unique = []
    for t in times:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique

def _row_matches_time(row: Dict[str, Any], times: List[int], bare_hour: bool = False) -> bool:
    if not times:
        return True
    s, e = _time_to_minutes(row.get("start_time")), _time_to_minutes(row.get("end_time"))
    if s is None or e is None:
        return False
    for t in times:
        if s <= t < e:
            return True
        if bare_hour and s == t:
            return True
    return False

def _row_matches_groups(group_val: Any, req: Set[str]) -> bool:
    if not req:
        return True
    norm = _normalize_key(group_val)
    comp = _split_group_components(group_val)
    return any(r == norm or r in comp for r in req)

def _format_timetable_entries(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return "Not available"
    sorted_e = sorted(entries, key=lambda entry: (
        str(entry.get("day_of_week", "")), str(entry.get("start_time", "")),
        str(entry.get("subject", ""))
    ))

    def _tl(v: Any) -> str:
        t = _safe_text(v)
        m = re.match(r"^(\d{1,2}:\d{2})(?::\d{2})?$", t)
        return m.group(1) if m else t

    lines = []
    for i, e in enumerate(sorted_e, 1):
        subj = _clean_subject_name(_safe_text(e.get("subject")))
        lines.append(
            f"{i}. {_safe_text(e.get('day_of_week'))} | "
            f"{_tl(e.get('start_time'))}-{_tl(e.get('end_time'))} | "
            f"Subject: {subj} | "
            f"Division: {_safe_text(e.get('division'))} | "
            f"Group: {_safe_text(e.get('group_name'))} | "
            f"Room: {_safe_text(e.get('classroom'))}"
        )
    return "\n".join(lines)

def _append_history(history: List[Dict[str, str]], role: str, content: str) -> None:
    history.append({"role": role, "content": content})

def _last_bot_message(history: List[Dict[str, str]]) -> str:
    for item in reversed(history):
        if item.get("role") == "bot":
            return str(item.get("content", ""))
    return ""

@trace_function()
def is_greeting(user_text: str) -> bool:
    t = user_text.lower().strip()
    greetings = {
        "hi", "hii", "hello", "helo", "heyy", "hey",
        "how are you", "good morning", "good afternoon", "good evening",
    }
    if t in greetings:
        return True
    if len(t.split()) <= 6:
        if re.search(r"\b(hi|hii|hello|helo|heyy|hey)\b", t):
            return True
        if "how are you" in t:
            return True
    return False

@trace_function()
def is_academic_query(user_text: str) -> bool:
    q = user_text.lower()
    if re.search(r"\b\d{2}bcp\d+[a-z]?\b", q):
        return True
    if re.search(r"\b\d{7,}\b", q):
        return True
    keywords = [
        "student", "faculty", "professor", "teacher", "cabin", "office",
        "lecture", "lec", "class", "classroom", "timetable", "schedule", "subject",
        "roll", "roll_no", "division", "group", "department", "email",
        "phone", "research", "resarch", "reseach", "reasearch", "resesarch",
        "interest", "intrest", "intrst", "interst", "lab", "where", "when",
        "who", "teach", "teaches", "teaching", "qualification", "phd",
        "college", "university", "institute",
        "him", "her", "his", "them", "their", "same", "detail", "details",
        "full", "complete", "info", "information", "everything", "about",
    ]
    return any(k in q for k in keywords)

@trace_function()
def is_llama_query(user_text: str) -> bool:
    q = user_text.lower()

    if re.search(r"\b(timetable|schedule|time table)\s+(of|for)\b", q):
        return False
    if re.search(r"\b(what is|show|give)\s+(the\s+)?(timetable|schedule)\s+(of|for)\b", q):
        return False
    if re.search(r"\b(his|her|their|my)\s+(timetable|schedule|time table|tt)\b", q):
        return False
    if re.search(r"\b(timetable|schedule|time table|tt)\s+(of|for)?\s*(him|her|them)\b", q):
        return False

    if _extract_division_keys(user_text) and re.search(r"\b(faculty|teacher|professor|staff)\b", q):
        return False

    if re.search(r"\b(faculty|teacher|professor)\s+(of|for)\b", q):
        return False

    cross_table_keywords = [
        "teach", "teaches", "teaching", "taught",
        "timetable", "time table", "schedule",
        "lecture", "lec", "room", "classroom",
        "subject", "which subject", "what subject",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "when", "where", "same division", "same div", "same group",
        "first roll", "last roll", "how many student", "how many faculty",
        "which division", "which group", "who teach", "who takes",
        "free slot", "free period", "free time", "not teaching", "available",
        "sitting in", "who is in", "who are in", "helding", "holding",
        "same division", "same div", "same group", "same class",
        "lab", "lec", "which subject", "what subject", "which div",
        "first roll", "last roll", "first student", "last student",
    ]
    return any(k in q for k in cross_table_keywords)

##### CONVERSATION STATE
class ConversationState:
    def __init__(self) -> None:
        self.last_table: str = ""
        self.last_row: Optional[Dict[str, Any]] = None
        self.pending_matches: List[Dict[str, Any]] = []
        self.pending_intent: str = ""

    def set_person(self, table: str, row: Dict[str, Any]) -> None:
        self.last_table = table
        self.last_row = dict(row)
        self.pending_matches = []
        self.pending_intent = ""

    def set_pending_matches(self, matches: List[Dict[str, Any]], intent: str = "") -> None:
        self.pending_matches = matches
        self.pending_intent = intent

    def clear_pending(self) -> None:
        self.pending_matches = []
        self.pending_intent = ""

#  SQL DUMP RAG
class SQLDumpRAG:
    def __init__(self, sql_path: str, config: Optional[Dict[str, Any]] = None) -> None:
        self.sql_path = Path(sql_path)
        self.config = {**DEFAULT_WEIGHTS, **(config or {})}
        self.rows_by_table: Dict[str, List[Dict[str, Any]]] = {}
        self.documents: List[Dict[str, Any]] = []
        self.token_to_doc_ids: Dict[str, Set[int]] = {}
        self.vocabulary: Set[str] = set()
        self.table_index: Dict[str, List[int]] = {}
        self._embed_model: Optional[Any] = None
        self._faiss_index: Optional[Any] = None

    def load(self) -> None:
        sql_text = self.sql_path.read_text(encoding="utf-8", errors="ignore")
        self.rows_by_table = self._parse_insert_statements(sql_text)
        self.documents = self._build_documents(self.rows_by_table)
        self.token_to_doc_ids = self._build_inverted_index(self.documents)
        self.vocabulary = set(self.token_to_doc_ids.keys())
        self.table_index = self._build_table_index(self.documents)
        self.build_semantic_index()
        print(f"Loaded {len(self.documents)} documents across "
              f"{len(self.rows_by_table)} tables.")

    def get_faculty_timetable(self, faculty_id: Any) -> List[Dict[str, Any]]:
        if faculty_id is None:
            return []
        return [
            r for r in self.rows_by_table.get("timetable", [])
            if str(r.get("faculty_id", "")) == str(faculty_id)
        ]

    def build_semantic_index(self) -> None:
        if not SEMANTIC_AVAILABLE:
            print("Semantic search unavailable — install faiss + sentence-transformers.")
            return

        if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_DOCS_PATH):
            print("Loading semantic index from disk ...", end=" ", flush=True)
            self._faiss_index = faiss.read_index(FAISS_INDEX_PATH)
            with open(FAISS_DOCS_PATH, "rb") as f:
                doc_count = pickle.load(f)
            if doc_count == len(self.documents):
                self._embed_model = SentenceTransformer(EMBED_MODEL_NAME)
                print("done.")
                return
            print("cache mismatch — rebuilding.")

        print("Building semantic index ...", end=" ", flush=True)
        self._embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        texts = [self._format_doc_text(d["table"], d["row"]) for d in self.documents]
        emb = self._embed_model.encode(
            texts, batch_size=64, show_progress_bar=False, convert_to_numpy=True
        ).astype(np.float32)
        faiss.normalize_L2(emb)
        idx = faiss.IndexFlatIP(emb.shape[1])
        idx.add(emb)
        self._faiss_index = idx
        faiss.write_index(idx, FAISS_INDEX_PATH)
        with open(FAISS_DOCS_PATH, "wb") as f:
            pickle.dump(len(self.documents), f)
        print("done.")

    @trace_function("SQLDumpRAG.retrieve")
    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K,
        table_filter: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q_tokens = _tokenize(query)
        cand_ids: Set[int] = set()
        for tok in q_tokens:
            cand_ids |= self.token_to_doc_ids.get(tok, set())
            for vocab_tok in self.vocabulary:
                if len(tok) >= 4 and vocab_tok.startswith(tok[:4]):
                    cand_ids |= self.token_to_doc_ids.get(vocab_tok, set())

        if table_filter:
            cand_ids &= set(self.table_index.get(table_filter, []))

        if not cand_ids:
            cand_ids = set(range(len(self.documents)))

        scored: List[Tuple[float, int]] = []
        q_field_vals = {_normalize_key(t) for t in q_tokens}
        w = self.config
        for i in cand_ids:
            d = self.documents[i]
            tok_score = len(q_tokens & d["tokens"]) * w["token_overlap"]
            fv_score  = sum(
                1.0 for fv in d["field_values"]
                if any(qv in fv or fv in qv for qv in q_field_vals)
            ) * w["field_exact"]
            scored.append((tok_score + fv_score, i))

        if SEMANTIC_AVAILABLE and self._faiss_index and self._embed_model:
            q_emb = self._embed_model.encode([query], convert_to_numpy=True).astype(np.float32)
            faiss.normalize_L2(q_emb)
            k = min(top_k * 3, self._faiss_index.ntotal)
            sim_scores, idxs = self._faiss_index.search(q_emb, k)
            sem_map = {int(idxs[0][j]): float(sim_scores[0][j]) for j in range(k)}
            scored = [
                (s + sem_map.get(i, 0.0) * w["semantic_blend"], i)
                for s, i in scored
            ]

        scored.sort(key=lambda item: -item[0])
        seen_rows: Set[int] = set()
        results: List[Dict[str, Any]] = []
        for _, i in scored:
            if i in seen_rows:
                continue
            seen_rows.add(i)
            results.append(self.documents[i])
            if len(results) >= top_k:
                break

        return results

    def _build_documents(self, rows_by_table: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        docs = []
        for table, rows in rows_by_table.items():
            for row in rows:
                text = self._format_doc_text(table, row)
                docs.append({
                    "table": table,
                    "row": row,
                    "text": text,
                    "tokens": _tokenize(text),
                    "field_values": [
                        str(v).lower()
                        for v in row.values()
                        if v is not None and str(v).strip()
                    ],
                })
        return docs

    @staticmethod
    def _format_doc_text(table: str, row: Dict[str, Any]) -> str:
        parts = [f"Type: {table}"]
        for k, v in row.items():
            if v is None or str(v).strip() == "":
                continue
            parts.append(f"{k.replace('_', ' ').title()}: {v}")
        return ". ".join(parts)

    def _build_inverted_index(self, docs: List[Dict[str, Any]]) -> Dict[str, Set[int]]:
        idx: Dict[str, Set[int]] = {}
        for i, d in enumerate(docs):
            for t in d["tokens"]:
                idx.setdefault(t, set()).add(i)
        return idx

    def _build_table_index(self, docs: List[Dict[str, Any]]) -> Dict[str, List[int]]:
        idx: Dict[str, List[int]] = {}
        for i, d in enumerate(docs):
            idx.setdefault(d["table"], []).append(i)
        return idx

    def _parse_insert_statements(self, sql_text: str) -> Dict[str, List[Dict[str, Any]]]:
        pattern = re.compile(
            r"INSERT INTO\s+`(?P<table>[^`]+)`\s*\((?P<cols>.*?)\)\s*VALUES\s*(?P<vals>.*?);",
            re.IGNORECASE | re.DOTALL,
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for m in pattern.finditer(sql_text):
            table = m.group("table").strip().lower()
            cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
            for tup in self._split_tuples(m.group("vals")):
                items = self._split_items(tup)
                if len(items) != len(cols):
                    continue
                out.setdefault(table, []).append(
                    dict(zip(cols, [self._parse_sql_value(v) for v in items]))
                )
        return out

    def _split_tuples(self, blob: str) -> List[str]:
        tuples, in_str, escaped, depth, cur = [], False, False, 0, []
        for ch in blob:
            if escaped:
                cur.append(ch); escaped = False; continue
            if ch == "\\":
                cur.append(ch); escaped = True; continue
            if ch == "'":
                in_str = not in_str; cur.append(ch); continue
            if not in_str:
                if ch == "(":
                    if depth == 0:
                        cur = []
                    else:
                        cur.append(ch)
                    depth += 1; continue
                if ch == ")":
                    depth -= 1
                    if depth == 0:
                        tuples.append("".join(cur).strip()); cur = []
                    else:
                        cur.append(ch)
                    continue
            if depth > 0:
                cur.append(ch)
        return tuples

    def _split_items(self, tup: str) -> List[str]:
        items, in_str, escaped, cur = [], False, False, []
        for ch in tup:
            if escaped:
                cur.append(ch); escaped = False; continue
            if ch == "\\":
                cur.append(ch); escaped = True; continue
            if ch == "'":
                in_str = not in_str; cur.append(ch); continue
            if ch == "," and not in_str:
                items.append("".join(cur).strip()); cur = []; continue
            cur.append(ch)
        if cur:
            items.append("".join(cur).strip())
        return items

    def _parse_sql_value(self, v: str) -> Any:
        v = v.strip()
        if v.upper() == "NULL":
            return None
        if v.startswith("'") and v.endswith("'"):
            return v[1:-1].replace("\\'", "'").replace("\\\\", "\\")
        if re.fullmatch(r"-?\d+", v):
            try:
                return int(v)
            except ValueError:
                return v
        if re.fullmatch(r"-?\d+\.\d+", v):
            try:
                return float(v)
            except ValueError:
                return v
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            return v
        return v


#  MAPPING HANDLER
class MappingHandler:
    def __init__(self, rag: SQLDumpRAG) -> None:
        self.rag = rag

    @trace_function("MappingHandler.handle")
    def handle(self, question: str, state: ConversationState, history: List[Dict[str, str]],
               trace_id: Optional[str] = None) -> str:
        result: str = ""
        ans = self._try_follow_up(question, state, history)
        if ans:
            result = ans
        else:
            ans = self._try_reverse_lookup(question)
            if ans:
                result = ans
            else:
                ans = self._try_structured_answer(question, state)
                if ans:
                    result = ans
                else:
                    if not is_llama_query(question):
                        has_roll = bool(ROLL_RE.search(question.lower()))
                        has_name = bool(_name_tokens(question))
                        if has_roll or has_name:
                            ans = self._resolve_person(question, state)
                            result = ans if ans else "No matching student or faculty found."
        return result

    @trace_function("MappingHandler._try_reverse_lookup")
    def _try_reverse_lookup(self, question: str) -> str:
        q = question.lower()
        phone_match = re.search(r"\b(\d{10})\b", q)
        if phone_match:
            phone = phone_match.group(1)
            for tbl in ["faculty", "student"]:
                for row in self.rag.rows_by_table.get(tbl, []):
                    if str(row.get("phone", "")).replace(" ", "") == phone:
                        return self._build_response_from_fields(dict(row), tbl, set())
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", q)
        if email_match:
            email = email_match.group(0).lower()
            for tbl in ["faculty", "student"]:
                for row in self.rag.rows_by_table.get(tbl, []):
                    if str(row.get("email", "")).lower() == email:
                        return self._build_response_from_fields(dict(row), tbl, set())
        return ""

    def _attach_faculty_timetable(self, row: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        if "_timetable_text" in row and not question:
            return row
        if question and "_timetable_text" in row:
            del row["_timetable_text"]
        days  = _extract_day_filters(question) if question else set()
        times = _extract_time_filters(question) if question else []
        all_entries = self.rag.get_faculty_timetable(row.get("id"))
        if days or times:
            all_entries = [
                r for r in all_entries
                if (not days or str(r.get("day_of_week", "")).lower() in days)
                and _row_matches_time(r, times)
            ]
        row["_timetable_text"] = _format_timetable_entries(all_entries) if all_entries else "Not available"
        return row

    def _attach_student_timetable(self, row: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        if "_timetable_text" in row and not question:
            return row
        if question and "_timetable_text" in row:
            del row["_timetable_text"]
        div   = _normalize_key(row.get("division"))
        grp   = _normalize_key(row.get("group_name"))
        days  = _extract_day_filters(question) if question else set()
        times = _extract_time_filters(question) if question else []
        matched = []
        for r in self.rag.rows_by_table.get("timetable", []):
            if _normalize_key(r.get("division")) != div:
                continue
            if grp not in _split_group_components(r.get("group_name")):
                continue
            if days and str(r.get("day_of_week", "")).lower() not in days:
                continue
            if not _row_matches_time(r, times):
                continue
            matched.append(r)
        row["_timetable_text"] = _format_timetable_entries(matched) if matched else "Not available"
        return row

    def _extract_requested_fields(self, query: str) -> Set[str]:
        q = query.lower()
        req: Set[str] = set()
        if re.search(r"\b(full|complete|all|everything|detail|details|info|information)\b", q):
            if re.search(r"\b(detail|details|info|information|about|full|complete|everything)\b", q):
                return set()
        if re.search(r"\b(roll|roll_no|roll no|rollno)\b", q):          req.add("roll_no")
        if re.search(r"\b(division|div)\b", q) and not re.search(r"\b(list|students|student)\b", q):
            req.add("division")
        if re.search(r"\b(group|grp)\b", q) and not re.search(r"\b(list|students|student)\b", q):
            req.add("group_name")
        if re.search(r"\b(name|who)\b", q):                              req.add("name")
        if re.search(r"\b(email|mail)\b", q):                            req.add("email")
        if re.search(r"\b(phone|contact|mobile)\b", q):                  req.add("phone")
        if re.search(r"\b(cabin|office|location)\b", q):                 req.add("cabin")
        if re.search(r"\b(designation|post|title)\b", q):                req.add("designation")
        if re.search(r"\b(department|dept)\b", q):                       req.add("department")
        if re.search(r"\b(qualification|qualified)\b", q):               req.add("qualification")
        if re.search(r"\b(phd|ph\.?d|phd subject)\b", q):               req.add("phd_subject")
        if re.search(r"\b(college|university|institute)\b", q):          req.add("college")
        if re.search(r"\b(research interest|interest area|research area|research)\b", q):
            req.add("research_interest")
        if re.search(r"\b(timetable|schedule|time table|lecture timing|tt)\b", q):
            req.add("timetable")
        return req

    def _build_response_from_fields(self, row: Dict[str, Any], table: str, requested: Set[str]) -> str:
        field_map = {
            "roll_no":           lambda r: f"Roll No: {_safe_text(r.get('roll_no'))}",
            "group_name":        lambda r: f"Group: {_safe_text(r.get('group_name'))}",
            "name":              lambda r: f"Name: {_safe_text(r.get('name'))}",
            "email":             lambda r: f"Email: {_safe_text(r.get('email'))}",
            "phone":             lambda r: f"Phone: {_safe_text(r.get('phone'))}",
            "cabin":             lambda r: f"Cabin: {_safe_text(r.get('cabin'))}",
            "designation":       lambda r: f"Designation: {_safe_text(r.get('designation'))}",
            "division":          lambda r: f"Division: {_safe_text(r.get('division'))}",
            "department":        lambda r: f"Department: {_safe_text(r.get('department'))}",
            "qualification":     lambda r: f"Qualification: {_safe_text(r.get('qualification'))}",
            "phd_subject":       lambda r: f"PhD Subject: {_safe_text(r.get('phd_subject'))}",
            "college":           lambda r: f"College: {_safe_text(r.get('college'))}",
            "research_interest": lambda r: (
                "Research Interest: Not available for students"
                if table == "student"
                else f"Research Interest: {_safe_text(r.get('research_interest'))}"
            ),
            "timetable": lambda r: f"Timetable:\n{_safe_text(r.get('_timetable_text'))}",
        }
        if not requested:
            if table == "student":
                return (
                    f"Name: {_safe_text(row.get('name'))}\n"
                    f"Roll No: {_safe_text(row.get('roll_no'))}\n"
                    f"Division: {_safe_text(row.get('division'))}\n"
                    f"Group: {_safe_text(row.get('group_name'))}"
                )
            return (
                f"Name: {_safe_text(row.get('name'))}\n"
                f"Department: {_safe_text(row.get('department'))}\n"
                f"Designation: {_safe_text(row.get('designation'))}\n"
                f"Phone: {_safe_text(row.get('phone'))}\n"
                f"Email: {_safe_text(row.get('email'))}\n"
                f"Cabin: {_safe_text(row.get('cabin'))}\n"
                f"Qualification: {_safe_text(row.get('qualification'))}\n"
                f"PhD Subject: {_safe_text(row.get('phd_subject'))}\n"
                f"College: {_safe_text(row.get('college'))}\n"
                f"Research Interest: {_safe_text(row.get('research_interest'))}"
            )
        order = [
            "name", "roll_no", "division", "group_name", "email", "phone", "cabin",
            "designation", "department", "qualification", "phd_subject", "college",
            "research_interest", "timetable",
        ]
        parts = [field_map[f](row) for f in order if f in requested and f in field_map]
        return "\n".join(parts) if parts else "Not found"

    @trace_function("MappingHandler._resolve_person")
    def _resolve_person(
        self,
        question: str,
        state: Optional[ConversationState] = None,
        direct_row: Optional[Dict[str, Any]] = None,
        direct_table: Optional[str] = None,
    ) -> str:
        if direct_row is not None and direct_table is not None:
            row = dict(direct_row)
            requested = self._extract_requested_fields(question)
            if direct_table == "faculty" and "timetable" in requested:
                self._attach_faculty_timetable(row, question)
            elif direct_table == "student" and "timetable" in requested:
                self._attach_student_timetable(row, question)
            return self._build_response_from_fields(row, direct_table, requested or {"name"})

        roll_match = ROLL_RE.search(question.lower())
        if roll_match:
            roll = roll_match.group(1).upper()
            for row in self.rag.rows_by_table.get("student", []):
                if str(row.get("roll_no", "")).upper() == roll:
                    requested = self._extract_requested_fields(question)
                    if "timetable" in requested:
                        self._attach_student_timetable(row, question)
                    if state:
                        state.set_person("student", row)
                    return self._build_response_from_fields(
                        row, "student", requested or {"name", "roll_no", "division", "group_name"}
                    )

        tokens = _name_tokens(question)
        if not tokens:
            return ""

        multi_name_parts = re.split(r"\band\b|&", question, flags=re.IGNORECASE)
        if len(multi_name_parts) >= 2:
            name_toks_per_part = [_name_tokens(p) for p in multi_name_parts]
            valid_parts = all(
                len(toks) >= 1 and any(len(t) >= 3 for t in toks)
                for toks in name_toks_per_part
            )
            if valid_parts and all(name_toks_per_part):
                requested = self._extract_requested_fields(question)
                all_results: List[str] = []
                for part_toks in name_toks_per_part:
                    found = False
                    for tbl in ["student", "faculty"]:
                        for row in self.rag.rows_by_table.get(tbl, []):
                            name = str(row.get("name", "")).lower()
                            if all(re.search(rf"\b{re.escape(t)}\b", name) for t in part_toks):
                                r = dict(row)
                                all_results.append(
                                    self._build_response_from_fields(r, tbl, requested or {"name", "roll_no", "cabin"})
                                )
                                found = True
                                break
                        if found:
                            break
                    if not found:
                        first_tok = part_toks[0]
                        if len(first_tok) >= 3:
                            matches_part = []
                            for tbl in ["student", "faculty"]:
                                for row in self.rag.rows_by_table.get(tbl, []):
                                    name = str(row.get("name", "")).lower()
                                    if re.search(rf"\b{re.escape(first_tok)}\b", name):
                                        matches_part.append((tbl, row))
                            if len(matches_part) == 1:
                                tbl, row = matches_part[0]
                                all_results.append(
                                    self._build_response_from_fields(dict(row), tbl, requested or {"name", "roll_no", "cabin"})
                                )
                            elif len(matches_part) > 1:
                                names = ', '.join(r.get('name','') for _, r in matches_part[:4])
                                all_results.append(f"Multiple matches for '{first_tok}': {names} — please use full name")
                if all_results:
                    return "\n".join(f"{i}. {res}" for i, res in enumerate(all_results, 1))

        matches: List[Dict[str, Any]] = []
        for tbl in ["student", "faculty"]:
            for row in self.rag.rows_by_table.get(tbl, []):
                name = str(row.get("name", "")).lower()
                if any(re.search(rf"\b{re.escape(tok)}\b", name) for tok in tokens):
                    matches.append({"table": tbl, "row": row})

        if not matches:
            return ""

        requested = self._extract_requested_fields(question)

        if len(matches) == 1:
            m = matches[0]
            row = dict(m["row"])
            tbl = m["table"]
            if tbl == "faculty":
                self._attach_faculty_timetable(row, question)
            elif tbl == "student" and "timetable" in requested:
                self._attach_student_timetable(row, question)
            if state:
                state.set_person(tbl, row)
            return self._build_response_from_fields(row, tbl, requested or {"name"})

        if state:
            state.set_pending_matches(
                [{"table": m["table"], "name": m["row"].get("name"),
                  "roll_no": m["row"].get("roll_no", ""),
                  "designation": m["row"].get("designation", ""),
                  "row": m["row"]} for m in matches],
                intent=question,
            )

        if requested:
            lines = ["I found multiple people with that name. Here are the details:"]
            for i, m in enumerate(matches, 1):
                row = dict(m["row"])
                tbl = m["table"]
                if "timetable" in requested:
                    if tbl == "faculty":
                        self._attach_faculty_timetable(row, question)
                    elif tbl == "student":
                        self._attach_student_timetable(row, question)
                fields = set(requested) | {"name"}
                lines.append(f"{i}. {self._build_response_from_fields(row, tbl, fields)}")
            return "\n".join(lines)

        lines = ["I found multiple people with that name. Who are you asking about?"]
        for i, m in enumerate(matches, 1):
            name = _safe_text(m["row"].get("name"))
            if m["table"] == "student":
                roll = _safe_text(m["row"].get("roll_no"))
                div  = _safe_text(m["row"].get("division"))
                grp  = _safe_text(m["row"].get("group_name"))
                lines.append(f"  {i}. {name} — Student | Roll No: {roll} | {div} | {grp}")
            else:
                desig = _safe_text(m["row"].get("designation"))
                cabin = _safe_text(m["row"].get("cabin"))
                lines.append(f"  {i}. {name} — {desig} | Cabin: {cabin}")
        lines.append("\nPlease reply with the number, full name, or roll number.")
        return "\n".join(lines)

    @trace_function("MappingHandler._try_structured_answer")
    def _try_structured_answer(self, question: str, state=None) -> str:
        requested = self._extract_requested_fields(question)

        subj_match = re.search(r"\b(?:faculty|teacher|professor)\s+(?:of|for)\s+(.+)", question.lower())
        if subj_match:
            subj_query = subj_match.group(1).strip()
            out = self._build_faculty_by_subject_answer(subj_query)
            if out:
                return out

        divs = _extract_division_keys(question)
        q = question.lower()
        if divs and re.search(r"\b(faculty|teacher|professor|staff)\b", q):
            out = self._build_faculty_by_division_answer(question, divs)
            if out:
                return out

        if self._is_generic_list_query(question, requested, FACULTY_KEYWORDS):
            return self._build_entity_list_answer("faculty", question)
        if self._is_generic_list_query(question, requested, STUDENT_KEYWORDS):
            return self._build_entity_list_answer("student", question)

        out = self._build_count_answer(question)
        if out:
            return out

        out = self._build_timetable_answer(question)
        if out:
            return out

        divs = _extract_division_keys(question)
        if divs:
            out = self._build_filtered_students_answer(
                question,
                filter_fn=lambda row: _normalize_key(row.get("division")) in divs,
                label=f"division {', '.join(sorted(divs))}",
                requested=requested,
            )
            if out:
                return out

        grps = _extract_group_keys(question)
        if grps:
            out = self._build_filtered_students_answer(
                question,
                filter_fn=lambda row: _row_matches_groups(row.get("group_name"), grps),
                label=f"group {', '.join(sorted(grps))}",
                requested=requested,
            )
            if out:
                return out

        return ""

    def _build_faculty_by_subject_answer(self, subj_query: str) -> str:
        SUBJECT_ALIASES: Dict[str, str] = {
            "awt": "advanced web", "web": "advanced web",
            "ai": "artificial intelligence", "ml": "machine learning",
            "cn": "computer network", "os": "operating system",
            "dbms": "database", "toc": "theory of computation",
            "ds": "data structure", "se": "software engineering",
            "cc": "cloud computing", "cloud": "cloud computing",
            "cns": "cryptography", "crypto": "cryptography",
            "cybersecurity": "cyber security", "cyber security": "cyber security",
            "cyber": "cyber security", "bda": "big data", "big data": "big data",
            "daa": "design and analysis",
        }
        q = subj_query.lower().strip()
        subj_filter = SUBJECT_ALIASES.get(q, q)

        faculty_rows = self.rag.rows_by_table.get("faculty", [])
        fac_map = {str(f.get("id")): f for f in faculty_rows}
        seen_ids: Set[str] = set()
        results: List[str] = []
        for row in self.rag.rows_by_table.get("timetable", []):
            subj_val = str(row.get("subject", "")).lower()
            if subj_filter not in subj_val:
                continue
            fid = str(row.get("faculty_id", ""))
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            fac = fac_map.get(fid)
            if fac:
                results.append(
                    f"{len(results)+1}. {_safe_text(fac.get('name'))} — "
                    f"{_safe_text(fac.get('designation'))}"
                )
        if not results:
            return ""
        return f"Faculty teaching {subj_query}:\n" + "\n".join(results)

    def _build_faculty_by_division_answer(self, question: str, divs: Set[str]) -> str:
        faculty_rows = self.rag.rows_by_table.get("faculty", [])
        fac_map = {str(f.get("id")): f for f in faculty_rows}
        seen_ids: Set[str] = set()
        results: List[str] = []
        for row in self.rag.rows_by_table.get("timetable", []):
            if _normalize_key(row.get("division")) not in divs:
                continue
            fid = str(row.get("faculty_id", ""))
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            fac = fac_map.get(fid)
            if fac:
                results.append(f"{len(results)+1}. {_safe_text(fac.get('name'))} — {_safe_text(fac.get('designation'))}")

        if not results:
            return ""
        div_label = ", ".join("Division " + d.replace("div", "") for d in sorted(divs))
        return "Faculty teaching in " + div_label + ":\n" + "\n".join(results)

    def _build_timetable_answer(self, question: str) -> str:
        q = question.lower()
        if not re.search(r"\b(timetable|timebale|schedule|time table|lecture|lec)\b", q):
            return ""
        divs = _extract_division_keys(question)
        grps = _extract_group_keys(question)
        days = _extract_day_filters(question)
        times = _extract_time_filters(question)
        if not divs and not grps:
            return ""
        rows = self.rag.rows_by_table.get("timetable", [])
        matched = []
        for row in rows:
            if divs and _normalize_key(row.get("division")) not in divs:
                continue
            if grps and not _row_matches_groups(row.get("group_name"), grps):
                continue
            if days and str(row.get("day_of_week", "")).lower() not in days:
                continue
            if not _row_matches_time(row, times):
                continue
            matched.append(row)
        if not matched:
            parts = []
            if divs: parts.append(f"division: {', '.join(sorted(divs))}")
            if grps: parts.append(f"group: {', '.join(sorted(grps))}")
            if days: parts.append(f"day: {', '.join(sorted(days))}")
            return f"No timetable found for {' | '.join(parts) or 'given filters'}."
        hp = []
        if divs: hp.append(f"division {', '.join(sorted(divs))}")
        if grps: hp.append(f"group {', '.join(sorted(grps))}")
        if days: hp.append(f"day {', '.join(sorted(days))}")
        heading = "Timetable" + (f" for {' | '.join(hp)}" if hp else "")
        return f"{heading}:\n{_format_timetable_entries(matched)}"

    def _build_filtered_students_answer(
        self,
        question: str,
        filter_fn: Callable,
        label: str,
        requested: Optional[Set[str]] = None,
    ) -> str:
        if not re.search(r"\b(student|students)\b", question.lower()):
            return ""
        rows = self.rag.rows_by_table.get("student", [])
        matched = [r for r in rows if filter_fn(r)]
        if not matched:
            return f"No students found for {label}."
        if requested is None:
            requested = self._extract_requested_fields(question)
        fields = (requested | {"name", "roll_no"}) if requested else {"name", "roll_no", "division", "group_name"}
        lines = [f"Found {len(matched)} students in {label}:"]
        for i, row in enumerate(matched, 1):
            lines.append(f"{i}. {self._build_response_from_fields(row, 'student', fields)}")
        return "\n".join(lines)

    def _build_count_answer(self, question: str) -> str:
        q = question.lower()
        if not re.search(r"\b(how many|count|total|number of)\b", q):
            return ""
        divs = _extract_division_keys(question)
        grps = _extract_group_keys(question)
        is_student = bool(re.search(r"\b(student|students)\b", q))
        is_faculty = bool(re.search(r"\b(faculty|faculties|teacher|teachers|professor|professors)\b", q))
        is_division = bool(re.search(r"\b(division|divisions|div|divs|group|groups|batch|batches)\b", q))

        if is_division and not is_student and not is_faculty:
            student_rows = self.rag.rows_by_table.get("student", [])
            unique_divs = {_normalize_key(r.get("division")) for r in student_rows if r.get("division")}
            unique_grps = {_normalize_key(r.get("group_name")) for r in student_rows if r.get("group_name")}
            if re.search(r"\b(group|groups|batch|batches)\b", q):
                return f"There are {len(unique_grps)} groups in total: {', '.join(sorted(unique_grps))}."
            return f"There are {len(unique_divs)} divisions in total: {', '.join(sorted(unique_divs))}."

        if divs or grps:
            table = "student" if is_student else ("faculty" if is_faculty else "student")
            rows = self.rag.rows_by_table.get(table, [])
            if divs:
                matched = [r for r in rows if _normalize_key(r.get("division")) in divs]
                return f"There are {len(matched)} {table}s in division {', '.join(sorted(divs))}."
            if grps:
                matched = [r for r in rows if _row_matches_groups(r.get("group_name"), grps)]
                return f"There are {len(matched)} {table}s in group {', '.join(sorted(grps))}."
        if is_student:
            return f"There are {len(self.rag.rows_by_table.get('student', []))} students in total."
        if is_faculty:
            return f"There are {len(self.rag.rows_by_table.get('faculty', []))} faculty members in total."
        return ""

    def _build_entity_list_answer(self, table: str, question: str = "") -> str:
        rows = self.rag.rows_by_table.get(table, [])
        if not rows:
            return f"No {table} records found."
        if table == "faculty" and question:
            q = question.lower()
            title_filter: Optional[str] = None
            if re.search(r"\bdr\.?\b", q):  title_filter = "dr"
            elif re.search(r"\bms\.?\b", q): title_filter = "ms"
            elif re.search(r"\bmr\.?\b", q): title_filter = "mr"
            if title_filter:
                rows = [
                    r for r in rows
                    if str(r.get("name", "")).lower().startswith(title_filter)
                ]
        label = "faculty" if table == "faculty" else "students"
        lines = [f"Found {len(rows)} {label}:"]
        for i, row in enumerate(rows, 1):
            name = _safe_text(row.get("name"))
            if table == "faculty":
                lines.append(f"{i}. {name} — {_safe_text(row.get('designation'))}")
            else:
                lines.append(f"{i}. {name}")
        return "\n".join(lines)

    def _is_generic_list_query(self, question: str, requested: Set[str], keywords: List[str]) -> bool:
        if requested:
            return False
        q = question.lower().strip()
        kw = "|".join(keywords)
        patterns = [
            rf"^(all\s+)?({kw})(\s+list)?(\s+(dr|ms|mr)\.?)?$",
            rf"^(show|give|display)\s+(all\s+)?({kw})(\s+(dr|ms|mr)\.?)?$",
            rf"^list(\s+of)?\s+(all\s+)?({kw})(\s+(dr|ms|mr)\.?)?$",
        ]
        return any(re.fullmatch(p, q) for p in patterns)

    @trace_function("MappingHandler._try_follow_up")
    def _try_follow_up(
        self,
        question: str,
        state: ConversationState,
        history: List[Dict[str, str]],
    ) -> str:
        q = question.lower().strip()
        requested = self._extract_requested_fields(question)

        if state.pending_matches:
            choice_match = re.fullmatch(r"\s*(\d+)\s*", q)
            if choice_match:
                idx = int(choice_match.group(1)) - 1
                if 0 <= idx < len(state.pending_matches):
                    chosen = state.pending_matches[idx]
                    row = dict(chosen["row"])
                    tbl = chosen["table"]
                    original_q = state.pending_intent or ""
                    if tbl == "faculty":
                        self._attach_faculty_timetable(row, question)
                    elif tbl == "student":
                        self._attach_student_timetable(row, question)
                    state.set_person(tbl, row)
                    orig_requested = self._extract_requested_fields(original_q) if original_q else set()
                    result = self._build_response_from_fields(row, tbl, orig_requested or set())
                    name = _safe_text(row.get('name'))
                    return f"Here is the information for {name}:\n{result}" if result != "Not found" else result
                else:
                    return f"Please pick a number between 1 and {len(state.pending_matches)}."

            for pm in state.pending_matches:
                pm_name = str(pm.get("name", "")).lower()
                if any(tok in pm_name for tok in _name_tokens(question)):
                    row = dict(pm["row"])
                    tbl = pm["table"]
                    original_q = state.pending_intent or ""
                    if tbl == "faculty":
                        self._attach_faculty_timetable(row, question)
                    elif tbl == "student":
                        self._attach_student_timetable(row, question)
                    state.set_person(tbl, row)
                    orig_requested = self._extract_requested_fields(original_q) if original_q else set()
                    result = self._build_response_from_fields(row, tbl, orig_requested or set())
                    name = _safe_text(row.get('name'))
                    return f"Here is the information for {name}:\n{result}" if result != "Not found" else result

            if requested:
                has_roll = bool(re.search(r"\b\d{2}bcp\d+[a-z]?\b", q))
                has_name = bool(_name_tokens(question))
                if not has_roll and not has_name:
                    if state.last_row and state.last_table in {"student", "faculty"}:
                        row = dict(state.last_row)
                        if state.last_table == "faculty":
                            self._attach_faculty_timetable(row, question)
                        elif state.last_table == "student":
                            self._attach_student_timetable(row, question)
                        return self._build_response_from_fields(row, state.last_table, requested)
                    field_label = ", ".join(sorted(requested)).replace("_", " ")
                    lines = [f"Whose {field_label}? Please specify from the list above:"]
                    for i, m in enumerate(state.pending_matches, 1):
                        name = _safe_text(m.get("name"))
                        roll = m.get("roll_no", "").strip()
                        if roll:
                            lines.append(f"  {i}. {name} (Roll No: {roll})")
                        else:
                            desig = m.get("designation", "").strip() or m.get("table", "").title()
                            lines.append(f"  {i}. {name} ({desig})")
                    lines.append("Reply with a name or roll number.")
                    return "\n".join(lines)

        is_detail_query = bool(re.search(
            r"\b(full|complete|all|everything|detail|details|info|information|timetable|schedule|tt)\b",
            q
        ))
        if (not requested and not is_detail_query) or state.last_table not in {"student", "faculty"} or not state.last_row:
            return ""

        has_roll = bool(re.search(r"\b\d{2}bcp\d+[a-z]?\b", q))
        if has_roll:
            return ""

        DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        name_toks = [t for t in _name_tokens(question) if t not in DAYS]
        if name_toks:
            state_name = str(state.last_row.get("name", "")).lower()
            if not all(tok in state_name for tok in name_toks):
                return ""

        last_bot = _last_bot_message(history).lower()
        cues = ["what about", "and", "also", "its", "his", "her", "their", "him", "them", "same"]
        is_follow_up = (
            "what info do you need" in last_bot
            or any(c in q for c in cues)
            or (len(q.split()) <= 6 and not re.search(r"\b(all|list|count|how many|total|division|group)\b", q))
            or bool(name_toks)
            or (not name_toks and bool(requested))
        )
        if not is_follow_up:
            return ""

        return self._resolve_person(
            question,
            state=state,
            direct_row=state.last_row,
            direct_table=state.last_table,
        )


#  LLAMA HANDLER  (OpenRouter only)
class LlamaHandler:
    def __init__(self, rag: SQLDumpRAG) -> None:
        self.rag = rag

    @trace_function("LlamaHandler.handle")
    def handle(
        self,
        question: str,
        history: List[Dict[str, str]],
        state: Optional[Any] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        context = self._build_context(question, history, trace_id=trace_id)
        answer = self._call_openrouter(question, context, history, trace_id=trace_id)
        return answer

    @trace_function("LlamaHandler._build_context")
    def _build_context(
        self,
        question: str,
        history: List[Dict[str, str]],
        trace_id: Optional[str] = None,
    ) -> str:
        q = question.lower()
        sections: List[str] = []

        faculty_rows = self.rag.rows_by_table.get("faculty", [])
        student_rows = self.rag.rows_by_table.get("student", [])
        tt_rows      = self.rag.rows_by_table.get("timetable", [])
        fac_map      = {str(f.get("id")): f.get("name", "Unknown") for f in faculty_rows}

        divs   = _extract_division_keys(question)
        groups = _extract_group_keys(question)
        days   = _extract_day_filters(question)
        times  = _extract_time_filters(question)
        rooms  = {
            re.sub(r"[^A-Z0-9]", "", m.group(0).upper())
            for m in re.finditer(r"\b[A-Za-z]-?\d{3,4}\b", question, re.IGNORECASE)
        }
        roll_matches = ROLL_RE.findall(q)
        name_tokens  = _name_tokens(question)
        TEACHING_WORDS = {
            "teaches", "teach", "teaching", "taught", "takes", "take",
            "faculty", "professor", "teacher", "staff", "lecturer",
            "which", "all", "who", "what", "where", "when", "how",
            "division", "subject", "lab", "lec", "lecture",
        }
        name_tokens = [t for t in name_tokens if t not in TEACHING_WORDS]

        SUBJECT_ALIASES: Dict[str, str] = {
            "ai": "artificial intelligence", "ml": "machine learning",
            "cn": "computer network", "os": "operating system",
            "dbms": "database", "toc": "theory of computation",
            "ds": "data structure", "awt": "advanced web",
            "se": "software engineering", "cc": "cloud computing",
            "cns": "cryptography", "crypto": "cryptography",
            "cybersecurity": "cyber security", "cyber security": "cyber security",
            "network security": "network security", "daa": "design and analysis",
            "flat": "automata", "oop": "object", "java": "java",
            "python": "python", "web": "web", "iot": "iot",
            "cloud": "cloud", "compiler": "compiler",
        }
        subj_filter: str = ""
        for alias, full in SUBJECT_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", q):
                subj_filter = full
                break
        if not subj_filter:
            for kw in ["artificial intelligence", "machine learning", "cryptography",
                       "network security", "cyber security", "data structure",
                       "operating system", "compiler", "software engineering",
                       "web technology", "cloud computing", "advanced web",
                       "object oriented", "design and analysis"]:
                if kw in q:
                    subj_filter = kw
                    break
        if not subj_filter:
            teach_match = re.search(r"\b(?:teach|teaches|teaching|taught)\s+([a-z][a-z\s]{2,30})\b", q)
            if teach_match:
                candidate = teach_match.group(1).strip()
                if len(candidate) > 2 and candidate not in {"in", "at", "all", "the", "a"}:
                    subj_filter = candidate

        cabin_rooms: Set[str] = set()
        for fac in faculty_rows:
            cabin_norm = re.sub(r"[^A-Z0-9]", "", str(fac.get("cabin", "")).upper())
            for room in rooms:
                room_norm = re.sub(r"[^A-Z0-9]", "", room.upper())
                if room_norm and (room_norm in cabin_norm or cabin_norm.startswith(room_norm)):
                    cabin_rooms.add(str(fac.get("id", "")))

        is_free_slot_query = bool(re.search(r"free.slot|free.period|free.time|not.teaching|available", q))
        matched_students: List[Dict[str, Any]] = []

        if is_free_slot_query and name_tokens and not divs:
            for s in student_rows:
                s_name = s.get("name", "").lower()
                if any(tok in s_name for tok in name_tokens):
                    div_key = _normalize_key(s.get("division"))
                    if div_key:
                        divs.add(div_key)
                        matched_students.append(s)
                    break

        wants_timetable = bool(re.search(
            r"(timetable|schedule|time table|lecture|lec|class|subject|teaches|teaching|room"
            r"|day|monday|tuesday|wednesday|thursday|friday|saturday|sunday|when|where"
            r"|free slot|free period|free time|available|not teaching|sitting in|who is in|who are in"
            r"|lab|which subject|what subject|which div|first roll|last roll|who teach|teach in)",
            q
        ))
        if divs and re.search(r"\b(faculty|teacher|professor|staff)\b", q):
            wants_timetable = True
        wants_faculty = bool(re.search(
            r"(faculty|professor|teacher|staff|lecturer|cabin|email|phone|contact|"
            r"designation|research|qualification|phd|department)", q
        ))
        wants_student = bool(re.search(
            r"(student|roll|roll.no|roll_no|division|group|batch|learner|list|how many|count"
            r"|same division|same div|same class|first roll|last roll)", q
        )) or bool(roll_matches) or (bool(name_tokens) and not wants_faculty and not wants_timetable)
        wants_count = bool(re.search(r"\b(how many|count|total|number of)\b", q))

        fac_lines = ["=== FACULTY RECORDS ==="]
        if cabin_rooms:
            display_faculty = [f for f in faculty_rows if str(f.get("id", "")) in cabin_rooms]
        elif wants_timetable or subj_filter:
            display_faculty = faculty_rows
        elif name_tokens:
            display_faculty = [
                f for f in faculty_rows
                if any(tok in f.get("name", "").lower() for tok in name_tokens)
            ] or ([] if (wants_student and not wants_faculty) else faculty_rows)
        elif wants_student and not wants_faculty:
            display_faculty = []
        else:
            display_faculty = faculty_rows

        for f in display_faculty:
            if wants_timetable or subj_filter:
                fac_lines.append(f"  ID:{f.get('id')} | Name: {_safe_text(f.get('name'))}")
            else:
                fac_lines.append(
                    f"  ID:{f.get('id')} | Name: {_safe_text(f.get('name'))} | "
                    f"Email: {_safe_text(f.get('email'))} | "
                    f"Phone: {_safe_text(f.get('phone'))} | "
                    f"Cabin: {_safe_text(f.get('cabin'))} | "
                    f"Designation: {_safe_text(f.get('designation'))} | "
                    f"Department: {_safe_text(f.get('department'))}"
                )
        sections.append("\n".join(fac_lines))

        is_same_div_query = bool(re.search(r"same.*(div|class|group)", q))
        student_div_filter: Set[str] = set()
        if name_tokens and re.search(r"\b(teach|teaches|teaching|taught|faculty|who teach)\b", q):
            for s in student_rows:
                s_name = s.get("name", "").lower()
                if any(tok in s_name for tok in name_tokens):
                    div_key = _normalize_key(s.get("division"))
                    if div_key:
                        student_div_filter.add(div_key)
                        if not matched_students:
                            matched_students.append(s)
            if student_div_filter and not divs:
                divs = student_div_filter

        needs_students = (wants_student or roll_matches or is_same_div_query or
                          bool(re.search(r"first.roll|last.roll", q)) or bool(student_div_filter)
                          or bool(matched_students))
        if needs_students:
            if is_same_div_query:
                for s in student_rows:
                    s_name = s.get("name", "").lower()
                    if any(tok in s_name for tok in name_tokens):
                        matched_students.append(s)
            elif student_div_filter:
                pass
            else:
                for s in student_rows:
                    if roll_matches:
                        if any(
                            _normalize_key(s.get("roll_no")) == _normalize_key(r)
                            for r in roll_matches
                        ):
                            matched_students.append(s)
                            continue
                    if divs and _normalize_key(s.get("division")) not in divs:
                        continue
                    if groups:
                        grp_norm = _normalize_key(s.get("group_name"))
                        grp_comps = _split_group_components(s.get("group_name"))
                        if not any(g == grp_norm or g in grp_comps for g in groups):
                            continue
                    if name_tokens and not divs and not roll_matches:
                        s_name = s.get("name", "").lower()
                        s_name_parts = s_name.split()
                        tok_match = any(tok in s_name for tok in name_tokens)
                        part_match = any(
                            part.startswith(tok) or tok.startswith(part)
                            for tok in name_tokens
                            for part in s_name_parts
                            if len(part) >= 3 and len(tok) >= 3
                        )
                        if not tok_match and not part_match:
                            continue
                    matched_students.append(s)

            if not matched_students and (divs or groups):
                matched_students = [
                    s for s in student_rows
                    if (not divs or _normalize_key(s.get("division")) in divs)
                ]

            stu_lines = [f"=== STUDENT RECORDS (total in result: {len(matched_students)}) ==="]
            for s in matched_students:
                stu_lines.append(
                    f"  Name: {_safe_text(s.get('name'))} | "
                    f"Roll No: {_safe_text(s.get('roll_no'))} | "
                    f"Division: {_safe_text(s.get('division'))} | "
                    f"Group: {_safe_text(s.get('group_name'))}"
                )
            if wants_count:
                stu_lines.insert(1, f"  [COUNT NOTE: {len(matched_students)} students match the filter above]")
            sections.append("\n".join(stu_lines))

        if wants_timetable or rooms or days or times:
            filtered_tt: List[Dict[str, Any]] = []
            for row in tt_rows:
                if divs and _normalize_key(row.get("division")) not in divs:
                    continue
                if days and str(row.get("day_of_week", "")).lower() not in days:
                    continue
                if times and not _row_matches_time(row, times):
                    continue
                if rooms and not cabin_rooms:
                    classroom = re.sub(r"[^A-Z0-9]", "", str(row.get("classroom", "")).upper())
                    if not any(r in classroom for r in rooms):
                        continue
                if subj_filter:
                    subj_val = str(row.get("subject", "")).lower()
                    if subj_filter not in subj_val:
                        continue
                filtered_tt.append(row)

            if name_tokens and not subj_filter:
                if not student_div_filter:
                    faculty_ids_for_name: Set[str] = set()
                    for f in faculty_rows:
                        fname = f.get("name", "").lower()
                        if any(tok in fname for tok in name_tokens):
                            faculty_ids_for_name.add(str(f.get("id")))

                    if faculty_ids_for_name:
                        name_filtered = [
                            row for row in filtered_tt
                            if str(row.get("faculty_id", "")) in faculty_ids_for_name
                        ]
                        if name_filtered:
                            filtered_tt = name_filtered
                        else:
                            for fid in faculty_ids_for_name:
                                filtered_tt.extend(self.rag.get_faculty_timetable(fid))

            if not filtered_tt:
                filtered_tt = tt_rows

            MAX_TT_ROWS = 279 if (not subj_filter and (is_free_slot_query or divs)) else (40 if not subj_filter else 279)
            if len(filtered_tt) > MAX_TT_ROWS:
                if DEBUG: print(f"[Info] Timetable rows capped from {len(filtered_tt)} to {MAX_TT_ROWS}")
                filtered_tt = filtered_tt[:MAX_TT_ROWS]

            tt_lines = ["=== TIMETABLE RECORDS ==="]
            for row in filtered_tt:
                fid   = str(row.get("faculty_id", ""))
                fname = fac_map.get(fid, f"Faculty ID {fid}")
                subj  = _clean_subject_name(_safe_text(row.get("subject")))
                tt_lines.append(
                    f"  Faculty: {fname} (ID:{fid}) | "
                    f"Division: {_safe_text(row.get('division'))} | "
                    f"Subject: {subj} | "
                    f"Day: {_safe_text(row.get('day_of_week'))} | "
                    f"Time: {_safe_text(row.get('start_time'))}-{_safe_text(row.get('end_time'))} | "
                    f"Room: {_safe_text(row.get('classroom'))}"
                )
            sections.append("\n".join(tt_lines))

        if cabin_rooms:
            cabin_lines = ["=== CABIN/OFFICE LOOKUP ==="]
            for fac in faculty_rows:
                if str(fac.get("id", "")) in cabin_rooms:
                    cabin_lines.append(
                        f"  Faculty: {_safe_text(fac.get('name'))} | "
                        f"Cabin: {_safe_text(fac.get('cabin'))} | "
                        f"Designation: {_safe_text(fac.get('designation'))}"
                    )
            sections.insert(0, "\n".join(cabin_lines))

        if history:
            last_turns = history[-4:]
            conv_lines = ["=== RECENT CONVERSATION (for context) ==="]
            for turn in last_turns:
                role = "User" if turn["role"] == "user" else "Assistant"
                conv_lines.append(f"  {role}: {turn['content'][:200]}")
            sections.append("\n".join(conv_lines))

        full = "\n\n".join(sections)
        if len(full) > MAX_CONTEXT_CHARS:
            full = full[:MAX_CONTEXT_CHARS] + "\n...[truncated]"

        return full

    def _call_openrouter(
        self,
        user_question: str,
        context_block: str,
        history: List[Dict[str, str]],
        max_history_turns: int = 2,
        trace_id: Optional[str] = None,
    ) -> Optional[str]:
        _span = tracker.span_llm(trace_id, user_question, len(context_block), OPENROUTER_MODEL)

        messages = []
        for turn in history[-(max_history_turns * 2):]:
            role = "user" if turn["role"] == "user" else "assistant"
            content = turn["content"]
            if role == "assistant" and len(content) > 150:
                content = content[:150] + "..."
            messages.append({"role": role, "content": content})

        messages.append({
            "role": "user",
            "content": (
                f"DATABASE RECORDS (answer ONLY from these):\n{context_block}\n\n"
                f"User question: {user_question}"
            ),
        })

        if DEBUG:
            print(f"[Debug] Sending {len(context_block)} characters of context to LLM.")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = OpenAI(
                    api_key=OPENROUTER_API_KEY,
                    base_url="https://openrouter.ai/api/v1",
                )
                print("Bot: ", end="", flush=True)
                completion = client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                    temperature=0.3,
                    max_tokens=2000,
                    stream=True,
                )
                collected = []
                for chunk in completion:
                    token = chunk.choices[0].delta.content or ""
                    if token:
                        print(token, end="", flush=True)
                        collected.append(token)
                print()
                result = "".join(collected).strip()
                tracker.end_span(_span, output={"response_length": len(result), "model": OPENROUTER_MODEL})
                return result if result else "I wasn't able to find an answer for that. Could you rephrase your question?"

            except Exception as e:
                err_str = str(e)
                if "429" in err_str and attempt < max_retries - 1:
                    wait = 30
                    m = re.search(r"retry_after_seconds.*?(\d+\.?\d*)", err_str)
                    if m:
                        wait = int(float(m.group(1))) + 2
                    print(f"\n[OpenRouter] Rate limited. Retrying in {wait}s... (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                print(f"\n[OpenRouter] Error: {e}")
                tracker.end_span(_span, error=str(e))
                return f"An error occurred with OpenRouter API: {e}"

    @staticmethod
    def is_available() -> bool:
        try:
            client = OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
            )
            client.models.list()
            return True
        except Exception:
            return False


# Main chatbot function
def main() -> None:
    print("=" * 60)
    print("  ACADEMIC CHATBOT  —  (FAISS + MiniLM + OpenRouter)")
    print("  With LangFuse Observability")
    print("=" * 60)

    print("\nLoading SQL dump...", end=" ", flush=True)
    rag = SQLDumpRAG(SQL_DUMP_PATH)
    rag.load()
    print(f"done.  Tables: {', '.join(sorted(rag.rows_by_table.keys()))}")
    print(f"       Records: {len(rag.documents)}")

    mapping_handler = MappingHandler(rag)
    llama_handler   = LlamaHandler(rag)

    use_llm = LlamaHandler.is_available()
    if use_llm:
        print(f"[OK] OpenRouter API ({OPENROUTER_MODEL}) reachable — LLM handler ON.")
    else:
        print("[!] OpenRouter not reachable — Mapping handler only.")

    tracker.start_session(use_llm=use_llm, use_openrouter=True)

    print("\nChatbot ready. Type 'exit' to quit.")
    print("Hello! How can I help you today?\n")

    history: List[Dict[str, str]] = []
    state      = ConversationState()
    turn_count = 0

    while True:
        try:
            user_q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBot: Goodbye!")
            tracker.end_session(turn_count, status="ended_by_user")
            break

        if not user_q:
            continue

        turn_count += 1
        _append_history(history, "user", user_q)
        tid = tracker.start_turn(user_q, turn_count)

        # Exit
        if user_q.lower() in {"exit", "quit", "bye"}:
            bot_response = "Bye! Have a great day!"
            _append_history(history, "bot", bot_response)
            tracker.end_turn(tid, bot_response, "exit")
            print(f"Bot: {bot_response}")
            break

        # Greeting
        if is_greeting(user_q):
            bot_response = "Hi! How can I help you with student and faculty info?"
            _append_history(history, "bot", bot_response)
            tracker.end_turn(tid, bot_response, "greeting")
            print(f"Bot: {bot_response}\n")
            continue

        # Out-of-scope check
        if not is_academic_query(user_q) and not _name_tokens(user_q):
            bot_response = "I'm designed only for academic queries about PDEU students and faculty."
            _append_history(history, "bot", bot_response)
            tracker.end_turn(tid, bot_response, "out_of_scope")
            print(f"Bot: {bot_response}\n")
            continue

        handler_used = "no_handler"

        # Route: LLM for complex/cross-table queries
        if use_llm and is_llama_query(user_q):
            print("[Answered by: OPENROUTER]")
            bot_response = llama_handler.handle(user_q, history[:-1], trace_id=tid)
            if not bot_response:
                bot_response = "I couldn't generate an answer. Please try rephrasing."
            handler_used = "openrouter_complex"
            _append_history(history, "bot", bot_response)
            tracker.end_turn(tid, bot_response, handler_used)
            tracker.ask_and_record_feedback(tid)
            print(f"\n")
            continue

        # Route: Mapping for direct/structural queries
        mapping_ans = mapping_handler.handle(user_q, state, history[:-1], trace_id=tid)
        if mapping_ans:
            print("[Answered by: MAPPING]")
            bot_response = mapping_ans
            handler_used = "mapping"
            _append_history(history, "bot", bot_response)
            tracker.end_turn(tid, bot_response, handler_used)
            tracker.ask_and_record_feedback(tid)
            print(f"Bot: {bot_response}\n")
            continue

        # Fallback: OpenRouter on anything not caught by mapping
        if use_llm:
            print("[Answered by: OPENROUTER (fallback)]")
            retrieved = rag.retrieve(user_q, top_k=TOP_K, trace_id=tid)
            if retrieved:
                context      = _build_fallback_context(user_q, retrieved, rag)
                bot_response = llama_handler._call_openrouter(user_q, context, history[:-1], trace_id=tid)
            else:
                bot_response = None
            if not bot_response:
                bot_response = "I could not find that information in the database."
            handler_used = "openrouter_fallback"
        else:
            bot_response = "I could not find that information in the database."

        _append_history(history, "bot", bot_response)
        tracker.end_turn(tid, bot_response, handler_used)
        tracker.ask_and_record_feedback(tid)
        print(f"\n")

    tracker.end_session(turn_count)


# Build fallback context for OpenRouter when query is not complex
def _build_fallback_context(
    question: str,
    retrieved_docs: List[Dict[str, Any]],
    rag: SQLDumpRAG,
) -> str:
    if not retrieved_docs:
        return "No relevant records found in the database."
    timetable_asked = bool(re.search(
        r"(timetable|schedule|time table|lecture timing|lecture|lec)",
        question.lower()
    ))
    skip = {"id", "faculty_id", "tokens"}
    lines = []
    for i, doc in enumerate(retrieved_docs, 1):
        table = doc.get("table", "")
        row = dict(doc.get("row", {}))
        if timetable_asked:
            if table == "faculty":
                fac_tt = rag.get_faculty_timetable(row.get("id"))
                row["timetable"] = _format_timetable_entries(fac_tt)
            elif table == "student":
                div = _normalize_key(row.get("division"))
                grp = _normalize_key(row.get("group_name"))
                matched = [
                    r for r in rag.rows_by_table.get("timetable", [])
                    if _normalize_key(r.get("division")) == div
                    and grp in _split_group_components(r.get("group_name"))
                ]
                row["timetable"] = _format_timetable_entries(matched)
        parts = [f"[{table.upper()} RECORD {i}]"]
        for k, v in row.items():
            if k in skip or v is None or str(v).strip() == "":
                continue
            val_str = str(v)
            if len(val_str) > 400:
                val_str = val_str[:400] + "..."
            parts.append(f"  {k.replace('_', ' ').title()}: {val_str}")
        lines.append("\n".join(parts))
    full_context = "\n\n".join(lines)
    if len(full_context) > MAX_CONTEXT_CHARS:
        full_context = full_context[:MAX_CONTEXT_CHARS] + "\n...[truncated]"
    return full_context


if __name__ == "__main__":
    main()