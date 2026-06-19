import os
import threading
import uuid
import json
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Thread-local storage to track the current active span/trace per request/thread
_local = threading.local()

def _get_stack() -> List[Any]:
    if not hasattr(_local, "stack"):
        _local.stack = []
    return _local.stack

class LangfuseTracker:
    def __init__(self) -> None:
        self.enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        self.host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        
        self.langfuse = None
        if self.enabled and self.public_key and self.secret_key:
            try:
                from langfuse import Langfuse
                self.langfuse = Langfuse(
                    public_key=self.public_key,
                    secret_key=self.secret_key,
                    host=self.host,
                    flush_at=1,
                    flush_interval=0.1
                )
                print(f"[Langfuse] Initialized tracing to {self.host}")
            except ImportError:
                print("[Langfuse Warning] langfuse python package not installed. Tracing disabled.")
                self.enabled = False
            except Exception as e:
                print(f"[Langfuse Error] Failed to initialize: {e}")
                self.enabled = False
        else:
            print("[Langfuse] Tracing is disabled (or keys are missing in .env)")
            self.enabled = False

        # Session and trace tracking
        self._current_session_id = str(uuid.uuid4())
        self._active_traces: Dict[str, Any] = {}

    @contextmanager
    def trace(self, name: str, input_str: Optional[str] = None, session_id: Optional[str] = None, user_id: Optional[str] = None, tags: Optional[List[str]] = None):
        """Context manager to start a top-level Trace."""
        if not self.enabled or not self.langfuse:
            yield None
            return

        sid = session_id or self._current_session_id
        trace_obj = self.langfuse.trace(
            name=name,
            input=input_str,
            session_id=sid,
            user_id=user_id,
            tags=tags
        )
        stack = _get_stack()
        stack.append(trace_obj)
        try:
            yield trace_obj
        finally:
            if stack and stack[-1] is trace_obj:
                stack.pop()
            try:
                self.langfuse.flush()
            except Exception:
                pass

    @contextmanager
    def span(self, name: str, input_data: Optional[Any] = None):
        """Context manager to start a Span under the active Trace or Span."""
        if not self.enabled or not self.langfuse:
            yield None
            return

        stack = _get_stack()
        parent = stack[-1] if stack else None

        if parent:
            span_obj = parent.span(name=name, input=input_data)
        else:
            span_obj = self.langfuse.span(name=name, input=input_data)

        stack.append(span_obj)
        try:
            yield span_obj
        finally:
            if stack and stack[-1] is span_obj:
                stack.pop()
            try:
                span_obj.end()
            except Exception:
                pass

    # Compatibility methods for existing app.py code
    def start_session(self, use_llm: bool = False, use_openrouter: bool = False) -> None:
        self._current_session_id = f"cli_session_{uuid.uuid4().hex[:8]}"

    def end_session(self, turn_count: int, status: str = "completed") -> None:
        pass

    def start_turn(self, user_q: str, turn_count: int) -> str:
        """Starts a new trace for a CLI conversation turn."""
        if not self.enabled or not self.langfuse:
            return f"dummy_{uuid.uuid4()}"

        trace_obj = self.langfuse.trace(
            name="handle-chatbot-message",
            input=user_q,
            session_id=self._current_session_id,
            tags=["qa-chatbot", "cli"]
        )
        
        # Store in map and thread local context
        self._active_traces[trace_obj.id] = trace_obj
        _get_stack().append(trace_obj)
        return trace_obj.id

    def end_turn(self, trace_id: str, bot_response: str, handler_used: str) -> None:
        """Completes a trace turn."""
        trace_obj = self._active_traces.pop(trace_id, None)
        if trace_obj:
            try:
                trace_obj.update(
                    output=bot_response,
                    tags=["qa-chatbot", handler_used]
                )
            except Exception:
                pass
            
            # Clean up stack
            stack = _get_stack()
            if stack and stack[-1] is trace_obj:
                stack.pop()
            
            try:
                self.langfuse.flush()
            except Exception:
                pass

    def record_event(self, trace_id: str, name: str, input_data: Optional[Any] = None, output_data: Optional[Any] = None, level: str = "DEFAULT") -> None:
        """NO-OP function because events are strictly not wanted in the Langfuse dashboard."""
        pass

    def span_retrieval(self, trace_id: str, query: str, top_k: int) -> Any:
        trace_obj = self._active_traces.get(trace_id) or (list(self._active_traces.values())[-1] if self._active_traces else None)
        if trace_obj:
            span = trace_obj.span(name="retrieval", input={"query": query, "top_k": top_k})
            return span
        return None

    def span_mapping(self, trace_id: str, question: str) -> Any:
        trace_obj = self._active_traces.get(trace_id) or (list(self._active_traces.values())[-1] if self._active_traces else None)
        if trace_obj:
            span = trace_obj.span(name="mapping-handler", input=question)
            return span
        return None

    def span_llm(self, trace_id: str, user_question: str, context_chars: int, model: str) -> Any:
        trace_obj = self._active_traces.get(trace_id) or (list(self._active_traces.values())[-1] if self._active_traces else None)
        if trace_obj:
            # Create a generation instead of a basic span
            gen = trace_obj.generation(
                name="llm-generation",
                model=model,
                input=user_question,
                metadata={"context_chars": context_chars}
            )
            return gen
        return None

    def end_span(self, span_obj: Any, output: Optional[Any] = None, error: Optional[str] = None) -> None:
        if span_obj:
            try:
                # If output is a dictionary, try to convert it or extract details
                out_val = output
                if isinstance(output, dict):
                    # For LLM call output dictionary: {"response_length": ..., "model": ...}
                    # If it's a generation object, we can log the model or custom metadata
                    if hasattr(span_obj, "update") and "model" in output:
                        span_obj.update(model=output["model"])
                    out_val = json.dumps(output)
                
                if error:
                    span_obj.end(output=out_val, level="ERROR", status_message=error)
                else:
                    span_obj.end(output=out_val)
            except Exception:
                pass

    def ask_and_record_feedback(self, trace_id: str) -> None:
        """Dummy to avoid blocking the CLI when run."""
        pass

# Instantiate the singleton tracker
tracker = LangfuseTracker()

def trace_function(name: Optional[str] = None):
    """Decorator to automatically log function calls as spans inside the active trace."""
    def decorator(func):
        func_name = name or func.__name__
        def wrapper(*args, **kwargs):
            if not tracker.enabled or not tracker.langfuse:
                return func(*args, **kwargs)

            stack = _get_stack()
            parent = stack[-1] if stack else None

            # Fallback to active traces if stack is empty (e.g. from app.py CLI mapping path)
            if not parent and tracker._active_traces:
                parent = list(tracker._active_traces.values())[-1]

            if not parent:
                return func(*args, **kwargs)

            # Determine input info
            input_val = None
            if args:
                # Skip class instances for cleaner inputs
                first_arg = args[0]
                if len(args) > 1 and hasattr(first_arg, "__class__") and first_arg.__class__.__name__ in ("MappingHandler", "LlamaHandler", "SQLDumpRAG"):
                    input_val = args[1]
                else:
                    input_val = first_arg
            else:
                input_val = kwargs

            # Format input nicely
            if input_val is not None and not isinstance(input_val, (str, int, float, bool)):
                try:
                    input_val = json.dumps(input_val, default=str)
                except Exception:
                    input_val = str(input_val)

            # Start child span
            span_obj = parent.span(name=func_name, input=input_val)
            stack.append(span_obj)
            try:
                result = func(*args, **kwargs)
                
                # Format output nicely
                output_val = result
                if output_val is not None and not isinstance(output_val, (str, int, float, bool)):
                    try:
                        output_val = json.dumps(output_val, default=str)
                    except Exception:
                        output_val = str(output_val)
                
                span_obj.end(output=output_val)
                return result
            except Exception as e:
                span_obj.end(level="ERROR", status_message=str(e))
                raise
            finally:
                if stack and stack[-1] is span_obj:
                    stack.pop()
        return wrapper
    return decorator
