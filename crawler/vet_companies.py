"""Vet a list of company names with Claude and save each result to the Company table.

Scope: given names -> vet -> save. Deciding WHICH names to vet (input, merge,
throttle) is vet_new_companies' job. Must be called through manage.py, since
importing crawler.models requires Django to be set up.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from django.conf import settings
from crawler.analyze_company import analyze_company
from crawler.models import Company


def vet(name: str) -> dict:
    """Vet one company. Runs in a worker thread.

    Prints on actual start (not on submit), so only running jobs show.
    No DB access here: Django gives each thread its own connection, so all
    writes stay on the main thread in vet_companies.
    """
    print(f"Started {name}...")
    return analyze_company(name)

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
        print("No Companies submitted")
        return [], []

    saved, failed = [], []
    
    # Reject incomplete input up front, before spending an API call on it.
    to_vet = []
    for company in companies:
        if company.get("ats") and company.get("board_token"):
            to_vet.append(company)
        else:
            failed.append(company["name"])
            print(f"FAILED {company['name']}: missing ats or board_token")

    print("Companies to vet: " + ", ".join(c["name"] for c in to_vet))
    
    with ThreadPoolExecutor(max_workers=max_workers or settings.VETTING_MAX_WORKERS) as pool:
        futures = { pool.submit(vet, company["name"]): company for company in to_vet}
        # as_completed yields on the main thread, so every DB write below happens there.
        for future in as_completed(futures):
            company = futures[future]
            try:
                fields = vetting_fields(future.result())
                fields["ats"] = company["ats"]
                fields["board_token"] = company["board_token"]

                # INSERT if no row has this name, else UPDATE it (a re-vet).
                # Name match is case-insensitive via collation.
                Company.objects.update_or_create(name=company["name"], defaults=fields)
                saved.append(company["name"])
                print(f"Saved {company['name']}")

            # Broad on purpose: one company failing for any reason must not kill the batch.
            except Exception as e:  # pylint: disable=broad-exception-caught
                failed.append(company["name"])
                print(f"FAILED {company['name']}: {e}")
                continue

    return saved, failed
