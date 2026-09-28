"""Admin views for crawler data; the interim GUI until Job Tracker's frontend exists."""
from django.contrib import admin

from crawler.models import Company, CrawledPosting


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "ats", "board_token", "vetted_on", "fit_score", "prior_rejections"]
    list_filter = ["ats", "vetted_on"]
    search_fields = ["name", "board_token"]
    ordering = ["-fit_score"]


@admin.register(CrawledPosting)
class CrawledPostingAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "location", "posted_at", "fit_score", "emailed_on"]
    list_filter = ["company", "emailed_on"]
    search_fields = ["title", "company__name", "location"]
    ordering = ["-fit_score"]