"""Crawler data models: companies being vetted and the job postings crawled from their boards."""
from django.db import models


class Company(models.Model):
    """A company in the pipeline. vetted_on is NULL until vetted, which is what marks it "to vet."

    Identity, in match order: id (known rows, round-tripped through the Cowork CSV),
    then (ats, board_token), then name. name is unique and, under the utf8mb4_unicode_ci
    collation, case-insensitive, so "AirBnB" and "Airbnb" collide. Strip whitespace before saving.

    Top-level fields mirror the submit_company_vetting tool schema. The per-criterion
    scoring stays in JSON because the rubric evolves; fit_score is computed in code
    from it and stored as a real column so it can be sorted and filtered on.
    """

    name = models.CharField(max_length=255, unique=True)

    # NULL, not "", when unknown: MariaDB unique constraints allow multiple NULLs
    # but treat every "" as a duplicate.
    ats = models.CharField(max_length=32, null=True, blank=True)
    board_token = models.CharField(max_length=255, null=True, blank=True)
    vetted_on = models.DateField(null=True, blank=True)

    synopsis = models.TextField(blank=True, default="")
    tech_stack = models.JSONField(default=list, blank=True)
    company_url = models.URLField(max_length=500, blank=True, default="")
    glassdoor_url = models.URLField(max_length=500, blank=True, default="")
    linkedin_url = models.URLField(max_length=500, blank=True, default="")

    legal_flags = models.JSONField(default=dict, blank=True)
    prior_rejections = models.PositiveIntegerField(default=0)
    application_limit = models.CharField(max_length=255, null=True, blank=True)

    scoring = models.JSONField(default=dict, blank=True)
    fit_score = models.FloatField(null=True, blank=True)

    # Full tool output, untouched. Anything not promoted to a column above still lives here.
    vetting_record = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "companies"
        constraints = [
            models.UniqueConstraint(fields=["ats", "board_token"], name="unique_board"),
        ]
        indexes = [
            models.Index(fields=["vetted_on"]),
            models.Index(fields=["fit_score"]),
        ]

    def __str__(self):
        return self.name


class CrawledPosting(models.Model):
    """A job posting pulled from a company's ATS board. A lead, not an application.

    Kept separate from Job Tracker's JobPosting (an application record); a posting
    gets "promoted" into a JobPosting when the user decides to apply.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="postings")
    # The ATS's own job ID. CharField, not int, so non-Greenhouse boards fit too.
    external_id = models.CharField(max_length=64)

    title = models.CharField(max_length=255)
    url = models.URLField(max_length=2048)
    location = models.CharField(max_length=255, blank=True, default="")
    departments = models.JSONField(default=list, blank=True)
    content = models.TextField(blank=True, default="")  # Description HTML as the ATS returns it

    posted_at = models.DateTimeField(null=True, blank=True)       # Greenhouse: first_published
    ats_updated_at = models.DateTimeField(null=True, blank=True)  # Greenhouse: updated_at

    # last_seen_at is bumped on every crawl; a posting not seen recently has closed.
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()

    fit_score = models.FloatField(null=True, blank=True)
    emailed_on = models.DateField(null=True, blank=True)

    raw = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "external_id"], name="unique_posting_per_company"),
        ]
        indexes = [
            models.Index(fields=["fit_score"]),
            models.Index(fields=["emailed_on"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.company})"