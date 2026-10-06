# vet_companies.py
"""Vet a list of company names with Claude and save each result to the Company table.

Scope: given names -> vet -> save. Deciding WHICH names to vet (input, merge,
throttle) is vet_new_companies' job. Must be called through manage.py, since
importing crawler.models requires Django to be set up.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from django.conf import settings
from django.db import connections
from crawler.analyze_company import analyze_company
from crawler.models.companies import Company

logger = logging.getLogger(__name__)


def vet(name: str) -> dict:
    """Vet one company. Runs in a worker thread.

    Logs on actual start (not on submit), so only running jobs show.
    No Company writes here; those stay on the main thread in vet_companies.
    The one DB write that does happen in this thread is the audit row saved
    inside run_with_pause. Django gives each thread its own connection for
    that, so it's closed on the way out rather than left open.
    """
    # DEBUG, not INFO: run_with_pause already logs "Vetting <name>: starting" at INFO.
    logger.debug("Worker picked up %s", name)
    try:
        return analyze_company(name)
    finally:
        connections.close_all()

def vetting_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Map an analyze_company result to Company column values.
    
    Missing optional keys fall back to empty defaults; checked_on is required
    and raises KeyError if absent.
    """
    links = result.get("links", {})
    return {
        # "" -> None: MariaDB's unique_board constraint allows many NULLs but only one "".
        "ats": result.get("ats") or None,
        "board_token": result.get("board_token") or None,
        "vetted_on": result["checked_on"], # "YYYY-MM-DD" string; DateField parses it on save
        "synopsis": result.get("synopsis", ""),
        "tech_stack": result.get("tech_stack", []),
        "company_url": links.get("company_url", ""),
        "glassdoor_url": links.get("glassdoor_url", ""),
        "linkedin_url": links.get("linkedin_url", ""),
        "legal_flags": result.get("legal_flags", {}),
        "prior_rejections": result.get("prior_rejections", 0),
        "application_limit": result.get("application_limit"),
        "scoring": result.get("scoring", {}),
        "vetting_record": result,   # full raw output, so nothing unpromoted is lost
    }

def vet_companies(
    companies: list[dict[str, Any]], max_workers: int | None = None,
) -> tuple[list[str], list[str]]:
    """Vet companies concurrently (see VETTING_MAX_WORKERS) and save each result as it finishes.

    Each company must include ats and board_token; one missing either fails
    immediately, without an API call. Each result is written the moment it
    completes, so a crash partway through keeps all finished work. A failed
    company writes nothing and will show up as new again on the next run.

    Args:
        companies: [{name, ats, board_token}] to vet. ats/board_token are stored
            as given; Claude's values for them are ignored.

    Returns:
        (saved, failed): company names in each outcome.
    """
    if not companies:
        logger.info("No companies submitted; nothing to vet.")
        return [], []

    saved, failed = [], []

    # Reject incomplete input up front, before spending an API call on it.
    to_vet = []
    for company in companies:
        if company.get("ats") and company.get("board_token"):
            to_vet.append(company)
        else:
            failed.append(company["name"])
            logger.info("Skipping %s: missing ats or board_token", company['name'])

    if not to_vet:
        logger.info("All %d submitted companies were incomplete; nothing to vet.",
                    len(companies))
        return saved, failed

    workers = max_workers or settings.VETTING_MAX_WORKERS
    logger.info("Vetting %d companies with %d workers: %s",
                len(to_vet), workers, ", ".join(c["name"] for c in to_vet))
    batch_start = time.perf_counter()


    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = { pool.submit(vet, company["name"]): company for company in to_vet}
        # as_completed yields on the main thread, so every DB write below happens there.
        for done, future in enumerate(as_completed(futures), start=1):
            company = futures[future]
            try:
                fields = vetting_fields(future.result())
                fields["ats"] = company["ats"]
                fields["board_token"] = company["board_token"]

                # INSERT if no row has this name, else UPDATE it (a re-vet).
                # Name match is case-insensitive via collation.
                _, created = Company.objects.update_or_create(name=company["name"], defaults=fields)
                saved.append(company["name"])
                logger.info("Saved %s (%s) [%d/%d]", company["name"],
                            "new" if created else "re-vet", done, len(to_vet))


            # Broad on purpose: one company failing for any reason must not kill the batch.
            except Exception:  # pylint: disable=broad-exception-caught
                failed.append(company["name"])
                # logger.exception includes the traceback, so the cause is in the log file.
                logger.exception("FAILED %s [%d/%d]", company["name"], done, len(to_vet))

                continue

    logger.info("Vetting batch done in %.1fs: %d saved, %d failed",
                time.perf_counter() - batch_start, len(saved), len(failed))
    if failed:
        logger.warning("Failed Companies: %s", ", ".join(failed))

    return saved, failed
