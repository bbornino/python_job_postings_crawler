"""
crawler/eeoc.py

Everything EEOC that touches the website or the database: walk the newsroom
list pages, save each press release as an EeocAction, and re-derive saved rows.
Deciding what a release says (action type, employer, tags) is done by
crawler.eeoc_classify.

scrape() and reprocess() are the entry points. The scrape_eeoc management
command is a thin wrapper around them, and a Lambda handler can call them
directly later.

scrape()    reads the site and saves releases it has not seen.
reprocess() re-derives action type, employer, tags, amount and duplicates
            for the saved rows from their title and teaser. No network.
"""

import logging
import re
import time
from collections import Counter
from datetime import date, datetime
from html import unescape

import requests
from bs4 import BeautifulSoup
from django.db.models import Count

from crawler.eeoc_classify import ACTION_PATTERNS, CASE_TYPES, TAG_PATTERNS, NO_EMPLOYER_TYPES, classify
from crawler.models.eeoc_actions import ActionType, EeocAction, SetBy, Tag
from crawler.net import fetch

logger = logging.getLogger(__name__)

BASE_URL = "https://www.eeoc.gov"
LIST_URL = f"{BASE_URL}/newsroom/search"
DIVIDER_LINE = "=" * 100    # divider line that sets a summary block apart in the log
# Seconds between list pages. At 1s (about 22 pages a minute) the site answered
# 403 after 113 requests in 5 minutes; 4s keeps a run near 10 pages a minute.
PAGE_DELAY = 4
MAX_PAGES = 400     # hard stop; the archive is ~300 pages, so this only trips on a bug
DERIVED_FIELDS = ["tags", "action_type", "amount", "employer_raw", "employer_key"]

PUBLISHED_FORMAT = "%B %d, %Y"      # the list page's date field: "October 7, 2026"
OLD_DATE = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{2})\b")     # 1990s/2000s style: 12-8-97

# Fail at import if a pattern uses a tag or action type the model does not allow.
assert set(TAG_PATTERNS) <= set(Tag.values), "TAG_PATTERNS has a tag missing from Tag"
assert {name for name, _ in ACTION_PATTERNS} <= set(ActionType.values)


def parse_date(published: str, teaser: str) -> date | None:
    """Release date from the page's date field, else an old-style 12-8-97 in the teaser."""
    try:
        return datetime.strptime(published, PUBLISHED_FORMAT).date()
    except ValueError:      # field missing or in another format: try the teaser
        pass
    try:
        if match := OLD_DATE.search(teaser):
            month, day, year = map(int, match.groups())
            return date(1900 + year if year >= 90 else 2000 + year, month, day)
    except ValueError:      # e.g. month 13: store nothing rather than crash
        pass
    logger.debug("No date parsed: field=%r teaser=%r", published, teaser[:80])
    return None


def parse_list_page(html: str) -> list[dict]:
    """One dict per press release on a newsroom list page, ready for EeocAction(**entry).

    Each entry on the page looks like this (trimmed):

        <div class="views-row">
          <article class="press_release">
            <h2><a href="/newsroom/slug">Title</a></h2>
            <div class="field--name-body">First sentences...</div>
            <div class="field--name-field-published-date">October 7, 2026</div>
    """
    entries = []
    for article in BeautifulSoup(html, "html.parser").select("div.views-row article"):
        link = article.select_one("h2 a[href]")
        if not link:
            continue
        body = article.select_one(".field--name-body")
        published = article.select_one(".field--name-field-published-date")
        title = link.get_text(" ", strip=True)
        teaser = body.get_text(" ", strip=True)[:1000] if body else ""
        href = link["href"]
        derived = classify(title, teaser)
        # A case with no employer means a headline shape EMPLOYER_PATTERNS misses.
        # Grep the log for these to see which patterns to add.
        if derived["action_type"] in CASE_TYPES and not derived["employer_raw"]:
            logger.debug("No employer parsed from: %s", title)
        entries.append({
            "url": href if href.startswith("http") else BASE_URL + href,
            "title": title[:500],
            "teaser": teaser,
            "released_on": parse_date(published.get_text(strip=True) if published else "", teaser),
            **derived,
        })
    return entries


def describe(row: EeocAction) -> str:
    """One-line summary of a release, for on-screen progress."""
    # Agency news has no employer, so say so rather than show a "?" that looks like a miss.
    no_employer = {"announcement": "EEOC announcement", "translation": "Spanish translation"}
    employer = row.employer_raw or no_employer.get(row.action_type, "?")
    copy = "    [copy]" if row.duplicate_of_id else ""
    return (f"  {row.released_on} | {row.action_type or '-':12} | "
            f"{employer} | {', '.join(row.tags)} | {row.title[:150]}{copy}")


def scrape(pages: int = MAX_PAGES, full: bool = False, dry_run: bool = False,
           limit: int | None = None, start_page: int = 0) -> int:
    """Walk the list pages newest-first and save unseen releases. Returns how many were saved.

    pages:      most list pages to read.
    full:       keep going past pages already saved (the backfill, or resuming one).
    dry_run:    show what was parsed, save nothing.
    limit:      stop after saving this many releases (None = no limit).
    start_page: first list page to read, for resuming a backfill that was cut off.

    All progress goes through the logger, so it lands in the log file as well
    as on screen.
    """
    known = set(EeocAction.objects.values_list("url", flat=True))
    saved = 0
    needs_a_look = []       # new releases the rules could not fully work out
    logger.info("EEOC scrape start: pages=%s start_page=%s full=%s dry_run=%s known=%s",
                pages, start_page, full, dry_run, len(known))

    for page in range(start_page, min(start_page + pages, MAX_PAGES)):
        try:
            response = fetch(f"{LIST_URL}?page={page}")
        except requests.HTTPError as err:
            # Usually a 403 from the site's rate limiting. Everything up to the
            # previous page is already saved, so stop cleanly and say where to resume.
            logger.error("EEOC page %s refused (HTTP %s). Resume later with: --full --start-page %s",
                         page, err.response.status_code, page)
            break
        entries = parse_list_page(response.text)
        if not entries:
            if page == 0:
                logger.error("EEOC page 0 parsed 0 entries: parse_list_page doesn't match the HTML")
            break       # past the last page

        fresh = [e for e in entries if e["url"] not in known]
        logger.info("EEOC page %s: %s found, %s new", page, len(entries), len(fresh))
        if limit is not None:
            fresh = fresh[:limit - saved]   # keep only what's left of the limit

        if dry_run:
            for e in entries:
                logger.info(describe(EeocAction(**e)))
        else:
            # Saved page by page, so a crash or Ctrl-C keeps everything so far.
            # ignore_conflicts covers the same URL showing up on two pages.
            EeocAction.objects.bulk_create([EeocAction(**e) for e in fresh], ignore_conflicts=True)
            known.update(e["url"] for e in fresh)
            saved += len(fresh)
            # Same test as the admin's "No employer name" and "Unclear action type" filters.
            needs_a_look += [e for e in fresh if not e["action_type"]
                             or (e["action_type"] not in NO_EMPLOYER_TYPES and not e["employer_raw"])]
            for e in fresh:     # what was just saved: progress on screen, a record in the log
                logger.info(describe(EeocAction(**e)))

        if limit is not None and saved >= limit:
            logger.info("EEOC limit of %s reached, stopping", limit)
            break
        # Routine runs: a page with nothing new means we've caught up.
        # Assumes page 0 is newest-first; full=True skips this check.
        if not fresh and not full:
            logger.info("EEOC page %s had nothing new, stopping", page)
            break
        time.sleep(PAGE_DELAY)

    if needs_a_look:
        logger.warning(DIVIDER_LINE)
        logger.warning("EEOC scrape: %s NEW RELEASES NEED A LOOK (no employer name, or unclear action type)",
                       len(needs_a_look))
        for e in needs_a_look:
            logger.warning(describe(EeocAction(**e)))
            logger.warning("      %s", e["url"])
        logger.warning(DIVIDER_LINE)
    logger.info("EEOC scrape done: %s new releases saved", saved)
    return saved


def reprocess() -> int:
    """Re-derive every saved row from its title and teaser. Returns how many rows changed.

    No network. Run it after changing any pattern in this file. It redoes the
    action type, employer, tags and amount, then the duplicate marks.

    Only rows still marked set_by="rules" are rewritten. A row fixed by hand
    (or by Claude) keeps its values, whatever the patterns now say.
    """
    rows = list(EeocAction.objects.filter(set_by=SetBy.RULES))
    kept = EeocAction.objects.exclude(set_by=SetBy.RULES).count()
    logger.info("EEOC reprocess start: %s rows set by rules, %s set by hand or Claude left alone",
                len(rows), kept)

    changed_rows = []
    changed_lines = []      # the same lines again, shown together at the end
    changed_fields = Counter()      # field name -> how many rows it changed on
    for row in rows:
        derived = classify(row.title, row.teaser)
        differs = [field for field, value in derived.items() if getattr(row, field) != value]
        # Changed rows get a second line: each field as old -> new. Built
        # before the row is updated, while it still holds the old values.
        detail = "      changed: " + "; ".join(
            f"{field}: {getattr(row, field)!r} -> {derived[field]!r}" for field in differs)
        for field in differs:
            setattr(row, field, derived[field])
            changed_fields[field] += 1
        # The same one-line summary scrape() prints, showing the row as it now stands.
        summary = describe(row)
        logger.info(summary)
        if not differs:
            continue
        logger.info(detail)
        changed_lines += [summary, detail]
        changed_rows.append(row)
    EeocAction.objects.bulk_update(changed_rows, DERIVED_FIELDS, batch_size=500)

    if changed_lines:
        logger.info(DIVIDER_LINE)
        logger.info("EEOC reprocess: the rows that changed:")
        for line in changed_lines:
            logger.info(line)
        logger.info(DIVIDER_LINE)
    logger.info("EEOC reprocess: %s of %s rows changed", len(changed_rows), len(rows))
    for field in DERIVED_FIELDS:
        logger.info("  %-12s changed on %s rows", field, changed_fields[field])

    mark_duplicates()

    # What is left to check by hand, counted the way the review will filter it.
    unique = EeocAction.objects.filter(duplicate_of__isnull=True)
    for action, total in unique.values_list("action_type").annotate(n=Count("id")).order_by("-n"):
        logger.info("  %-12s %s releases", action or "(unclear)", total)
    logger.info("EEOC reprocess done: %s releases are about an employer but have no name",
                unique.exclude(action_type__in=NO_EMPLOYER_TYPES).filter(employer_raw="").count())
    return len(changed_rows)


def title_key(title: str) -> str:
    """Title cut down to lowercase letters and digits.

    Copies of one release differ in spacing, capitals and HTML entities
    ("DENNY&#39;S" vs "DENNY'S"), and this makes them compare equal.
    """
    return re.sub(r"[^a-z0-9]+", " ", unescape(title).lower()).strip()


def mark_duplicates() -> int:
    """Point every repeated release at the first copy saved. Returns how many are marked.

    The EEOC archive holds two copies of many older releases under different
    URLs, so the URL check in scrape() can't catch them. Two rows are the same
    release when they share a date and a title_key. The same title on different
    dates is left alone: those are separate cases, such as one employer sued
    again years later.

    Nothing is deleted, because a deleted copy would just be saved again by
    the next backfill. Count with .filter(duplicate_of__isnull=True) instead.
    Safe to re-run: it recomputes every row from scratch.
    """
    originals = {}      # (date, title_key) -> first row saved with that pair
    rows = list(EeocAction.objects.order_by("id"))
    for row in rows:
        original = originals.setdefault((row.released_on, title_key(row.title)), row)
        row.duplicate_of = None if original is row else original
    EeocAction.objects.bulk_update(rows, ["duplicate_of"], batch_size=500)
    marked = sum(1 for row in rows if row.duplicate_of)
    logger.info("EEOC duplicates: %s of %s releases marked as copies", marked, len(rows))
    return marked
