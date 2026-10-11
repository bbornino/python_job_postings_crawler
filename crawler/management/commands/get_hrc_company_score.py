"""
crawler/management/commands/get_hrc_company_score.py

Look up companies on the HRC Corporate Equality Index from the command line.

    python manage.py get_hrc_company_score "Abbott Laboratories" "HP" "AMD"

For each name it prints the HRC score, whether it's verified, and how the name
was matched, then a summary with the elapsed time. Lookups run one at a time,
since hrc_lookup paces its own requests to hrc.org.

Lookup only for now: nothing is written to the Company table yet.

USAGE NOTE: most rated companies score 100. Only a low score is a red flag;
treat high scores and "not rated" as no signal.
"""

import logging
import time

from django.core.management.base import BaseCommand

from crawler.hrc_lookup import get_hrc_score

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run hrc_lookup.get_hrc_score for each company name given on the command line."""

    help = "Look up one or more companies' HRC Corporate Equality Index scores."

    def add_arguments(self, parser):
        """One or more company names. Quote names with spaces: "Procter & Gamble"."""
        parser.add_argument("companies", nargs="+", help="company names to look up on hrc.org")

    def handle(self, *args, **options):
        """Look up each company, print its result, then a summary of all of them.

        One company failing (an HTTP error, a page HRC changed) is logged with
        its traceback and the rest still run.
        """
        companies = options["companies"]
        logger.info("HRC lookup for %d companies: %s", len(companies), ", ".join(companies))
        run_start = time.perf_counter()
        rated, not_rated, failed = [], [], []

        for name in companies:
            # Broad on purpose: one company failing must not kill the batch.
            try:
                result = get_hrc_score(name)
            except Exception:  # pylint: disable=broad-exception-caught
                failed.append(name)
                logger.exception("FAILED HRC lookup for %s", name)
                continue

            if result is None:
                not_rated.append(name)
                self.stdout.write(f"{name}: not rated by HRC")
                continue

            rated.append(name)
            # get_hrc_score already logs the details; this line is the on-screen answer.
            self.stdout.write(
                f"{name}: {result['name']}, score {result['score']} "
                f"({'verified' if result['verified'] else 'unverified'}, via {result['matched_via']})"
            )

        elapsed = time.perf_counter() - run_start
        logger.info("HRC lookup done in %.1fs: %d rated, %d not rated, %d failed",
                    elapsed, len(rated), len(not_rated), len(failed))
        if not_rated:
            logger.info("Not rated by HRC: %s", ", ".join(not_rated))
        if failed:
            logger.warning("Failed HRC lookups: %s", ", ".join(failed))