from flask import Flask, request, jsonify
from flask_cors import CORS
from app import (
    SQLDumpRAG, MappingHandler, LlamaHandler, ConversationState,
    is_greeting, is_academic_query, is_llama_query, _name_tokens,
    _append_history, _build_fallback_context, TOP_K,
    OPENROUTER_API_KEY, SYSTEM_PROMPT,
)
from langfuse_integration import tracker
import time, re
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# Load once at startup
rag = SQLDumpRAG("dpniti.sql")
rag.load()
mapping_handler = MappingHandler(rag)
llama_handler   = LlamaHandler(rag)
use_llm = LlamaHandler.is_available()

# Fallback model chain: try free first, then lighter free models
OPENROUTER_MODELS = [
    "openrouter/free",
]

def _call_openrouter_with_fallback(
    user_question: str,
    context_block: str,
    history: list,
    system_prompt: str,
    max_history_turns: int = 2,
) -> str:
    """Call OpenRouter with automatic model fallback on 429 rate limit."""
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

    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )

    last_error = None
    for model in OPENROUTER_MODELS:
        for attempt in range(2):  # 2 retries per model
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    temperature=0.3,
                    max_tokens=2000,
                    stream=True,
                    extra_headers={
                        "HTTP-Referer": "https://dpniti.local",
                        "X-Title": "DPNITI Campus Assist",
                    },
                )
                collected = []
                for chunk in completion:
                    token = chunk.choices[0].delta.content or ""
                    if token:
                        collected.append(token)
                result = "".join(collected).strip()
                return result if result else "I wasn't able to find an answer. Could you rephrase?"

            except Exception as e:
                err_str = str(e)
                last_error = err_str
                if "429" in err_str:
                    wait = 5
                    m = re.search(r"retry_after_seconds.*?(\d+\.?\d*)", err_str)
                    if m:
                        wait = max(5, int(float(m.group(1))) + 2)
                    if attempt == 0 and wait <= 35:
                        print(f"[OpenRouter] 429 on {model}. Waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"[OpenRouter] 429 on {model}. Switching model...")
                        break
                else:
                    print(f"[OpenRouter] Error on {model}: {e}")
                    break  # Non-rate-limit error → try next model

    return f"The AI service is temporarily overloaded. Please try again in a moment. (Last error: {last_error})"


# Per-session state (keyed by session_id)
sessions: dict = {}

def get_session(session_id: str):
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "state": ConversationState()}
    return sessions[session_id]

@app.route("/chat", methods=["POST"])
def chat():
    data       = request.get_json(force=True)
    user_q     = (data.get("message") or "").strip()
    session_id = data.get("session_id", "default")
    user_id    = data.get("user_id")

    if not user_q:
        return jsonify({"reply": "Please type a message."})

    sess    = get_session(session_id)
    history = sess["history"]
    state   = sess["state"]

    _append_history(history, "user", user_q)

    with tracker.trace(
        name="handle-chatbot-message",
        input_str=user_q,
        session_id=session_id,
        user_id=user_id,
        tags=["qa-chatbot"]
    ) as trace:
        if user_q.lower() in {"exit", "quit", "bye"}:
            reply = "Bye! Have a great day!"

        elif is_greeting(user_q):
            reply = "Hi! How can I help you with student and faculty info?"

        elif not is_academic_query(user_q) and not _name_tokens(user_q):
            reply = "I'm designed only for academic queries about PDEU students and faculty."

        elif use_llm and is_llama_query(user_q):
            # Complex / cross-table → use LlamaHandler (which calls OpenRouter internally)
            context = llama_handler._build_context(question=user_q, history=history[:-1])
            reply = _call_openrouter_with_fallback(
                user_q, context, history[:-1], system_prompt=SYSTEM_PROMPT
            ) or "I couldn't generate an answer. Please try rephrasing."

        else:
            mapping_ans = mapping_handler.handle(user_q, state, history[:-1])
            if mapping_ans:
                reply = mapping_ans
            elif use_llm:
                # Fallback: retrieve relevant docs → LLM
                retrieved = rag.retrieve(user_q, top_k=TOP_K)
                if retrieved:
                    context = _build_fallback_context(user_q, retrieved, rag)
                    reply = _call_openrouter_with_fallback(
                        user_q, context, history[:-1], system_prompt=SYSTEM_PROMPT
                    ) or "I could not find that information."
                else:
                    reply = "I could not find that information in the database."
            else:
                reply = "I could not find that information in the database."

        if trace:
            trace.update(output=reply)

    _append_history(history, "bot", reply)
    return jsonify({"reply": reply})

@app.route("/reset", methods=["POST"])
def reset():
    session_id = (request.get_json(force=True) or {}).get("session_id", "default")
    if session_id in sessions:
        del sessions[session_id]
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    print(f"[OK] LLM {'ON' if use_llm else 'OFF - mapping only'}")
    print("[OK] Chatbot API running on http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)