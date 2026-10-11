"""
crawler/management/commands/scrape_eeoc.py

Command-line wrapper around crawler.eeoc. All the logic lives there.

    python manage.py scrape_eeoc --pages 1 --dry-run   # first test: print, save nothing
    python manage.py scrape_eeoc --full                # one-time backfill, ~300 pages
    python manage.py scrape_eeoc                       # routine run: stops at known releases
    python manage.py scrape_eeoc --full --start-page 112   # resume a backfill that was cut off
    python manage.py scrape_eeoc --reprocess           # re-derive saved rows after a pattern change, no network
"""

import time

from django.core.management.base import BaseCommand

from crawler import eeoc


class Command(BaseCommand):
    help = "Scrape EEOC newsroom press releases into EeocAction."

    def add_arguments(self, parser):
        parser.add_argument("--pages", type=int, default=eeoc.MAX_PAGES, help="Most list pages to read.")
        parser.add_argument("--full", action="store_true",
                            help="Keep going past pages already saved (backfill, or resuming one).")
        parser.add_argument("--dry-run", action="store_true", help="Print what was parsed, save nothing.")
        parser.add_argument("--limit", type=int, default=None, help="Stop after saving this many releases.")
        parser.add_argument("--start-page", type=int, default=0,
                            help="First list page to read (resume a backfill that was cut off).")
        parser.add_argument("--reprocess", action="store_true",
                            help="Re-derive action type, employer, tags and duplicates for saved rows. No fetching.")

    def handle(self, *args, **options):
        started = time.monotonic()      # monotonic: unaffected by clock changes mid-run
        if options["reprocess"]:
            changed = eeoc.reprocess()
            summary = f"Reprocessed: {changed} releases changed"
        else:
            saved = eeoc.scrape(pages=options["pages"], full=options["full"], dry_run=options["dry_run"],
                                limit=options["limit"], start_page=options["start_page"])
            summary = f"Done: {saved} new releases saved"
        minutes, seconds = divmod(int(time.monotonic() - started), 60)
        self.stdout.write(self.style.SUCCESS(f"{summary} in {minutes}m {seconds:02d}s."))
