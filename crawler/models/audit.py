"""
Audit models for the crawler app.

Tracks every successful Claude API call the crawler makes so token usage
can be counted per purpose and per day.
"""

from django.db import models


class LLMCallAudit(models.Model):
    """
    One row per successful Claude API call.

    Rows are written by record_usage() in crawler/audit.py, never by hand, so
    every call is counted. A request that pauses and resumes makes several API
    calls, so it produces several rows with the same purpose.

    Failed API calls are not recorded: they raise before record_usage runs,
    and there's no usage to count. They show up in the log file instead.

    Stores raw token counts rather than dollar cost because pricing changes;
    compute cost at query time.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    purpose = models.CharField(max_length=50)         # "grade_posting", etc.
    model = models.CharField(max_length=100)

    # Token counts come straight from response.usage. Cache tokens are billed
    # at different rates than regular input, so they stay in separate columns.
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_creation_input_tokens = models.PositiveIntegerField(default=0)
    cache_read_input_tokens = models.PositiveIntegerField(default=0)
    web_search_requests = models.PositiveIntegerField(default=0)

    duration_ms = models.PositiveIntegerField(default=0)
    stop_reason = models.CharField(max_length=50, blank=True)

    # Not written yet: record_usage only runs after a successful call, so
    # success is always True and error is always blank. Kept for when failed
    # calls get recorded too.
    success = models.BooleanField(default=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "LLM call audit"
        verbose_name_plural = "LLM call audits"
        indexes = [
            # Covers the "tokens by purpose over a date range" report.
            models.Index(fields=["purpose", "created_at"]),
        ]

    def __str__(self):
        status = "ok" if self.success else "FAILED"
        return f"{self.purpose} [{status}] {self.total_tokens} tokens ({self.created_at:%Y-%m-%d %H:%M})"

    @property
    def total_input_tokens(self):
        """All input tokens: uncached + cache writes + cache reads."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    @property
    def total_tokens(self):
        """Everything sent plus everything received for this call."""
        return self.total_input_tokens + self.output_tokens

