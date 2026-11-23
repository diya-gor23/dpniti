
from academic_helpers import (
    ConversationState, is_greeting, is_academic_query, _name_tokens,
    _append_history, SYSTEM_PROMPT, DEBUG, OPENROUTER_API_KEY,
    OPENROUTER_MODEL, OPENROUTER_MODELS, LOCAL_LLM_BASE_URL,
)
from llama_handler import LlamaHandler


async def main() -> None:
    raise RuntimeError(
        "The interactive SQL-dump CLI has been removed. Start the API with "
        "`uvicorn chatbot_api:app --host 0.0.0.0 --port 5001`."
    )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
