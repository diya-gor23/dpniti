from flask import Flask, request, jsonify
from flask_cors import CORS
from app import (
    SQLDumpRAG, MappingHandler, LlamaHandler, ConversationState,
    is_greeting, is_academic_query, is_llama_query, _name_tokens,
    _append_history, _build_fallback_context, TOP_K, LOCAL_ONLY_MODE
)

app = Flask(__name__)
CORS(app)

# Load once at startup
rag = SQLDumpRAG("dpniti.sql")
rag.load()
mapping_handler = MappingHandler(rag)
llama_handler   = LlamaHandler(rag)
use_llm = (not LOCAL_ONLY_MODE) and LlamaHandler.is_available()

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

    if not user_q:
        return jsonify({"reply": "Please type a message."})

    sess    = get_session(session_id)
    history = sess["history"]
    state   = sess["state"]

    _append_history(history, "user", user_q)

    if user_q.lower() in {"exit", "quit", "bye"}:
        reply = "Bye! Have a great day!"
    elif is_greeting(user_q):
        reply = "Hi! How can I help you with student and faculty info?"
    elif not is_academic_query(user_q) and not _name_tokens(user_q):
        reply = "I'm designed only for academic queries about PDEU students and faculty."
    elif use_llm and is_llama_query(user_q):
        reply = llama_handler.handle(user_q, history[:-1]) or "I couldn't generate an answer. Please try rephrasing."
    else:
        mapping_ans = mapping_handler.handle(user_q, state, history[:-1])
        if mapping_ans:
            reply = mapping_ans
        elif use_llm:
            retrieved = rag.retrieve(user_q, top_k=TOP_K)
            if retrieved:
                context = _build_fallback_context(user_q, retrieved, rag)
                reply = llama_handler._call_ollama(user_q, context, history[:-1]) or "I could not find that information."
            else:
                reply = "I could not find that information in the database."
        else:
            reply = "I could not find that information in the database."

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
