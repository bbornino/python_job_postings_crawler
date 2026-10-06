"""
Claude API setup and the shared request loop. Import `client`, the model
settings, and run_with_pause from here instead of creating clients per command.
"""
import logging
import os
import time
import anthropic
from dotenv import load_dotenv
from crawler.audit import record_usage
from crawler.utils import status_timer

logger = logging.getLogger(__name__)

load_dotenv()
_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    raise ValueError("ANTHROPIC_API_KEY is not set")

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
THINKING_MODEL = os.getenv("THINKING_MODEL", "claude-opus-4-7")
THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))

# Output caps per request type. Raise one if its runs log a max_tokens warning.
VETTING_MAX_TOKENS = int(os.getenv("VETTING_MAX_TOKENS", "4096"))
INCLUSION_REFS_MAX_TOKENS = int(os.getenv("INCLUSION_REFS_MAX_TOKENS", "8000"))
EEOC_AGE_ACTIONS_MAX_TOKENS = int(os.getenv("EEOC_AGE_ACTIONS_MAX_TOKENS", "32000"))
# Retries per API call when the connection drops mid-response. See .env.example.
CLAUDE_CONNECTION_RETRIES = int(os.getenv("CLAUDE_CONNECTION_RETRIES", "1"))

client = anthropic.Anthropic(api_key=_api_key)

def _stream_message(label: str, messages: list, create_kwargs: dict) -> anthropic.types.Message:
    """Make one streaming API call, retrying if the connection drops mid-response.

    Only dropped connections are retried (up to CLAUDE_CONNECTION_RETRIES).
    An error the API itself returned (4xx/5xx) is raised straight away: the
    SDK has already retried the ones worth retrying.
    """
    for attempt in range(CLAUDE_CONNECTION_RETRIES + 1):
        try:
            with status_timer(label), client.messages.stream(messages=messages,
                                                             **create_kwargs) as stream:
                return stream.get_final_message()
        except anthropic.APIStatusError:
            raise
        # Broad on purpose: a mid-stream drop arrives as a raw httpx error,
        # not an anthropic one, so there's no narrower class to catch.
        except Exception:  # pylint: disable=broad-exception-caught
            if attempt == CLAUDE_CONNECTION_RETRIES:
                raise
            logger.warning("%s: connection dropped (attempt %d of %d); retrying",
                           label, attempt + 1, CLAUDE_CONNECTION_RETRIES + 1, exc_info=True)

def run_with_pause(label: str = "Waiting on Claude", max_resumes: int = 10,
                   purpose: str | None = None,
                   **create_kwargs) -> anthropic.types.Message:
    """Stream one request, resuming on pause_turn until the model actually stops.
 
    Takes the same keyword args as client.messages.create(), plus `label` for the
    status timer line, log messages, and the audit row's `purpose`. `messages` is
    copied, so the caller's list isn't modified.

    Each API call is logged and saved as one audit row (via record_usage), then a
    total across all resumes is logged. The total is the number that matches the
    bill, since every resume re-sends the full context.
    """
    messages = list(create_kwargs.pop("messages"))
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write":0, "searches": 0}
    response = None
    logger.info("%s: starting (model=%s)", label, create_kwargs.get("model"))
    run_start = time.perf_counter()

    for call in range(max_resumes):
        call_start = time.perf_counter()
        try:
            response = _stream_message(label, messages, create_kwargs)
        # Exception, not anthropic.APIError: a dropped connection isn't an APIError.
        except Exception:
            # Tokens from earlier calls in this run are already billed; log them before bailing.
            logger.exception("%s: API call %d failed; tokens so far: %s", label, call, totals)
            raise

        duration_ms = int((time.perf_counter() - call_start) * 1000)

        usage = response.usage
        stu = usage.server_tool_use
        totals["input"] += usage.input_tokens
        totals["output"] += usage.output_tokens
        totals["cache_read"] += usage.cache_read_input_tokens or 0
        totals["cache_write"] += usage.cache_creation_input_tokens or 0
        totals["searches"] += stu.web_search_requests if stu else 0

        # Logs this call's tokens and duration, and writes the audit row.
        record_usage(response, label, purpose or label, duration_ms)

        if response.stop_reason != "pause_turn":
            elapsed = time.perf_counter() - run_start
            if call == 0:
                # One call: the usage line above already has these numbers.
                logger.info("%s: finished in %.1fs", label, elapsed)
            else:
                logger.info("%s: finished after %d calls in %.1fs; totals: %s",
                            label, call + 1, elapsed, totals)
            return response
        # Server-side tool loop hit its per-turn limit; send everything back to resume.
        logger.info("%s: pause_turn, resuming", label)
        messages.append({"role": "assistant", "content": response.content})

    logger.warning("%s: still paused after %d resumes in %.1fs; giving up. Totals: %s",
                   label, max_resumes, time.perf_counter() - run_start, totals)
    return response # still paused after max_resumes; caller sees stop_reason == "pause_turn"
