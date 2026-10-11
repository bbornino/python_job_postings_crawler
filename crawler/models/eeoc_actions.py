"""
crawler/models/eeoc_actions.py
EEOC press releases saved by the newsroom scraper (crawler.eeoc).
"""
from django.core.exceptions import ValidationError
from django.db import models


class ActionType(models.TextChoices):
    """What kind of release this is. Each entry is: stored value, dropdown label."""
    SUED = "sued", "Sued"
    SETTLED = "settled", "Settled"
    VERDICT = "verdict", "Verdict"
    ANNOUNCEMENT = "announcement", "EEOC announcement"
    TRANSLATION = "translation", "Spanish translation (repeat of an English release)"


# How to read a tag: every tag describes the EMPLOYER in that release.
#
#   Plain tags (age, trans, sex, race, equal_pay, ...) = the employer was
#   accused of that kind of discrimination. These count AGAINST the employer.
#   So "trans" means accused of anti-trans discrimination, and "equal_pay"
#   means accused of underpaying someone.
#
#   pro_ tags (pro_trans, pro_dei) = the EEOC went after the employer BECAUSE
#   it supported trans employees or ran a DEI program. These count FOR the
#   employer. They are rare (16 releases as of Oct 2026, mostly 2025 onward).
#
#   dropped_dei = the employer publicly gave up its DEI program, usually to
#   settle with the EEOC. Counts AGAINST the employer. Set by hand only; there
#   is no pattern for it.
#
# There are no anti_ tags: a plain tag already is the "anti".
class Tag(models.TextChoices):
    """The fixed list of tags a release can carry. See the comment above for how to read them."""
    AGE = "age", "Age"
    TRANS = "trans", "Trans"
    LGBTQ = "lgbtq", "LGBTQ"
    SEX = "sex", "Sex"
    RELIGION = "religion", "Religion"
    NATIONAL_ORIGIN = "national_origin", "National origin"
    VISA_PREFERENCE = "visa_preference", "Visa preference"
    RACE = "race", "Race"
    PREGNANCY = "pregnancy", "Pregnancy"
    RETALIATION = "retaliation", "Retaliation"
    HARASSMENT = "harassment", "Harassment"
    HOSTILE_ENV = "hostile_env", "Hostile environment"
    DISABILITY = "disability", "Disability"
    EQUAL_PAY = "equal_pay", "Equal pay"
    PRO_TRANS = "pro_trans", "Pro-trans (targeted for supporting trans employees)"
    PRO_DEI = "pro_dei", "Pro-DEI (targeted for a DEI program)"
    DROPPED_DEI = "dropped_dei", "Dropped DEI (publicly abandoned its DEI program)"
    GENETIC_INFO = "genetic_info", "Genetic information (asked for family medical history)"


class SetBy(models.TextChoices):
    """Who last set a row's derived fields: the regex rules, by hand, or Claude."""
    RULES = "rules", "Rules"
    HAND = "hand", "By hand"
    CLAUDE = "claude", "Claude"


def validate_tags(value):
    """Reject any tag that is not in Tag (runs on form saves, not on .save())."""
    unknown = set(value) - set(Tag.values)
    if unknown:
        raise ValidationError(f"Unknown tags: {sorted(unknown)}")


class EeocAction(models.Model):
    """One EEOC press release (lawsuit filed, settlement, verdict, announcement)."""

    url = models.URLField(max_length=500, unique=True)     # dedupe key: never save a release twice
    title = models.CharField(max_length=500)
    teaser = models.TextField(blank=True)                   # first lines shown on the list page
    released_on = models.DateField(null=True, blank=True)   # some 1990s entries have odd dates

    # Everything below is derived from title + teaser by crawler.eeoc, so it
    # can be rebuilt any time without re-scraping.
    employer_raw = models.CharField("employer name", max_length=300, blank=True)     # a real name, or blank
    employer_key = models.CharField(max_length=300, blank=True, db_index=True)  # normalized, for grouping/joins
    # A JSON list, e.g. ["age", "retaliation"]; empty list when nothing matched.
    # Query one tag with: EeocAction.objects.filter(tags__contains=["age"])
    tags = models.JSONField(default=list, blank=True, validators=[validate_tags])
    action_type = models.CharField(max_length=20, blank=True, choices=ActionType.choices)
    amount = models.PositiveBigIntegerField(null=True, blank=True)  # whole dollars, when the title says

    # Who last set the derived fields. Reprocessing only overwrites "rules" rows.
    set_by = models.CharField(max_length=10, choices=SetBy.choices, default=SetBy.RULES)

    # Set when this row is a second copy of another release (same date and
    # title under a different URL). Filled by crawler.eeoc.mark_duplicates().
    # Per-company counts should use .filter(duplicate_of__isnull=True).
    duplicate_of = models.ForeignKey("self", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="copies")

    class Meta:
        """Newest releases first."""
        ordering = ["-released_on"]

    def __str__(self):
        return str(self.title)
