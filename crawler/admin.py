"""Admin views for crawler data; the interim GUI until Job Tracker's frontend exists."""
from django.contrib import admin
from django.utils.html import format_html
from django import forms

from crawler.eeoc_classify import employer_key
from crawler.models.eeoc_actions import SetBy, Tag
from crawler.models import (Company, CrawledPosting, EeocAction, ReferenceCompanyEntry,
                            ReferenceSource, ReferenceStateEntry)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Companies being tracked, best fit score first."""
    list_display = ["name", "ats", "board_token", "vetted_on", "fit_score", "prior_rejections"]
    list_filter = ["ats", "vetted_on"]
    search_fields = ["name", "board_token"]
    ordering = ["-fit_score"]


@admin.register(CrawledPosting)
class CrawledPostingAdmin(admin.ModelAdmin):
    """Job postings found by the crawler, best fit score first."""
    list_display = ["title", "company", "location", "posted_at", "fit_score", "emailed_on"]
    list_filter = ["company", "emailed_on"]
    search_fields = ["title", "company__name", "location"]
    ordering = ["-fit_score"]


class TagFilter(admin.SimpleListFilter):
    """Sidebar filter: releases carrying one tag (tags is a JSON list, so no built-in filter)."""
    title = "tag"
    parameter_name = "tag"

    def lookups(self, request, model_admin):
        """One sidebar choice per tag in the model's Tag list."""
        return Tag.choices

    def queryset(self, request, queryset):
        """Rows whose tags list contains the chosen tag."""
        return queryset.filter(tags__contains=[self.value()]) if self.value() else queryset


class NeedsALookFilter(admin.SimpleListFilter):
    """Sidebar filter for the rows the rules most often get wrong."""
    title = "needs a look"
    parameter_name = "look"

    def lookups(self, request, model_admin):
        """The sidebar choices."""
        return [
            ("no_employer", "No employer name"),
            ("unclear", "Unclear action type"),
            ("no_tags", "Employer but no tags"),
            ("copies", "Duplicate copies"),
        ]

    def queryset(self, request, queryset):
        """Rows matching the chosen sidebar option."""
        if self.value() == "no_employer":
            # About an employer (not an EEOC announcement) but no name was found.
            # Copies are left out so the same release isn't fixed twice.
            return (queryset.exclude(action_type__in=["announcement", "translation"])
                    .filter(employer_raw="", duplicate_of__isnull=True))
        if self.value() == "unclear":
            return queryset.filter(action_type="", duplicate_of__isnull=True)
        if self.value() == "no_tags":
            return queryset.exclude(employer_raw="").filter(tags=[])
        if self.value() == "copies":
            return queryset.filter(duplicate_of__isnull=False)
        return queryset


class EeocActionForm(forms.ModelForm):
    """Edit form that shows tags as checkboxes instead of a raw JSON text box."""
    tags = forms.MultipleChoiceField(choices=Tag.choices, required=False,
                                     widget=forms.CheckboxSelectMultiple)

    class Meta:
        """Every model field; the admin's own `fields` list picks which to show."""
        model = EeocAction
        fields = "__all__"


@admin.register(EeocAction)
class EeocActionAdmin(admin.ModelAdmin):
    """EEOC press releases: review list with inline fixes for employer name and action type."""
    # List page: the headline opens the edit form; employer and action can be
    # fixed right in the list for a whole screen of rows, then saved once.
    list_display = ["headline", "released_on", "employer_raw", "action_type", "tag_list",
                    "amount", "release_link"]
    list_display_links = ["headline"]
    list_editable = ["employer_raw", "action_type"]
    list_filter = [NeedsALookFilter, "action_type", TagFilter]
    search_fields = ["title", "employer_raw", "teaser"]
    date_hierarchy = "released_on"      # year > month > day drill-down above the list
    ordering = ["-released_on"]
    list_per_page = 50

    # Edit form: what the EEOC wrote is read-only, shown above the fields we derive.
    # duplicate_of is read-only on purpose: as a dropdown it would list every release.
    fields = [("released_on", "release_link", "duplicate_of"), "teaser",
              ("action_type", "amount", "set_by"),
              ("employer_raw", "employer_key"),
              "tags"]
    readonly_fields = ["release_link", "title", "teaser", "released_on",
                       "employer_key", "duplicate_of"]

    form = EeocActionForm

    def get_changelist_form(self, request, **kwargs):
        """The list page's inline editing keeps the plain form; checkboxes are for the edit page."""
        kwargs.setdefault("form", forms.ModelForm)
        return super().get_changelist_form(request, **kwargs)

    @admin.display(description="Headline", ordering="title")
    def headline(self, obj):
        """Headline cut to 90 characters so the list stays readable."""
        return obj.title[:90]

    @admin.display(description="Tags")
    def tag_list(self, obj):
        """Tags as plain comma-separated text."""
        return ", ".join(obj.tags)

    @admin.display(description="Release")
    def release_link(self, obj):
        """Link that opens the release on eeoc.gov in a new tab."""
        return format_html('<a href="{}" target="_blank" rel="noopener">open on eeoc.gov</a>',
                           obj.url)

    def save_model(self, request, obj, form, change):
        """Rebuild the matching key and mark the row as set by hand."""
        obj.employer_key = employer_key(obj.employer_raw)
        obj.set_by = SetBy.HAND
        super().save_model(request, obj, form, change)


@admin.register(ReferenceSource)
class ReferenceSourceAdmin(admin.ModelAdmin):
    """Where each reference list came from and when it was refreshed."""
    list_display = ["key", "edition", "published_on", "last_refreshed"]
    search_fields = ["key", "edition"]


@admin.register(ReferenceCompanyEntry)
class ReferenceCompanyEntryAdmin(admin.ModelAdmin):
    """Companies named in a reference list."""
    list_display = ["name", "source", "details"]
    list_filter = ["source"]
    search_fields = ["name"]


@admin.register(ReferenceStateEntry)
class ReferenceStateEntryAdmin(admin.ModelAdmin):
    """State ratings from a reference list."""
    list_display = ["state", "rating", "scoring_bucket", "tally", "source"]
    list_filter = ["source", "scoring_bucket"]
