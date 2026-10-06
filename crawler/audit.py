# crawler/audit.py
"""Logs Claude token usage and writes it to the LLMCallAudit table."""
import logging
import anthropic
from crawler.models.audit import LLMCallAudit

logger = logging.getLogger(__name__)


def _log_usage(response: anthropic.types.Message, label: str, duration_ms: int) -> None:
    """Log one response's duration, tokens, and server-side tool counts."""
    usage = response.usage
    # server_tool_use is None when Claude didn't search or fetch at all.
    # web_fetch_requests only exists on newer SDK versions, hence getattr.
    stu = usage.server_tool_use
    logger.info(
        "%s: usage %.1fs stop_reason=%s input=%d output=%d cache_read=%d cache_write=%d "
        "searches=%d fetches=%d",
        label,
        duration_ms / 1000,
        response.stop_reason,
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_input_tokens or 0,
        usage.cache_creation_input_tokens or 0,
        stu.web_search_requests if stu else 0,
        getattr(stu, "web_fetch_requests", 0) if stu else 0,
    )


def record_usage(response: anthropic.types.Message, label: str, purpose: str,
                 duration_ms: int) -> None:
    """Log one Claude API response's usage and save it as an audit row.

    The only function callers need. Never raises: the response is already paid
    for, so a bug in logging or a failed DB write must not throw it away.

    Args:
        label: Specific to this call, e.g. "Vetting Abridge". Goes in the log
            line so concurrent workers' lines can be told apart.
        purpose: The category, e.g. "vet_company". Goes in the audit row so
            usage can be totalled across all calls of one kind.
    """
    # Separate try blocks so a logging failure doesn't also skip the audit row.
    try:
        _log_usage(response, label, duration_ms)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Usage logging failed for %s", label)

    try:
        usage = response.usage
        stu = usage.server_tool_use
        LLMCallAudit.objects.create(
            purpose=purpose,
            model=response.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            web_search_requests=stu.web_search_requests if stu else 0,
            duration_ms=duration_ms,
            stop_reason=response.stop_reason or "",
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Audit write failed for %s", label)