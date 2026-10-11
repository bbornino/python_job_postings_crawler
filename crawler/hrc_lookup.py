"""
crawler/hrc_lookup.py
HRC Corporate Equality Index lookup: one company at a time, on demand.

    from crawler.hrc_lookup import get_hrc_score
    result = get_hrc_score("Abbott Laboratories")   # dict, or None if HRC doesn't rate them

Command-line check while developing (run from the project root, so the
crawler package imports resolve):

    python -m crawler.hrc_lookup "Abbott Laboratories"

No caching in here on purpose: this module only fetches and parses. The caller
(vet_companies) should store the result and not ask again until the next CEI
release, since the index only changes once a year.

All HTTP goes through crawler.net.fetch, which supplies the User-Agent, the
live ticker, per-request logging and 429 retries. Pacing stays here, because
net.fetch leaves the polite rate to each scraper.

USAGE NOTE: most rated companies score 100, so the score is only useful as a
red flag when it is low. Treat None and high scores as "no signal".

Needs: requests, beautifulsoup4
"""

import json
import logging
import re
import sys
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from crawler.net import fetch

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hrc.org"
DETAIL_PATH = "/resources/corporations/"
SEARCH_URL = BASE_URL + "/resources/employers/search"
POLITE_DELAY = 1.5  # seconds between our requests to hrc.org

# Legal-form words HRC tacks onto names ("Intel Corp.", "Amazon.com Inc.").
# Dropped before comparing, so "Intel" == "Intel Corp." and "Amazon" == "Amazon.com Inc."
NAME_NOISE = {"inc", "corp", "corporation", "co", "company", "llc", "lp", 
              "llp", "ltd", "plc", "the", "com"}
MAX_SEARCH_PAGES = 5  # 10 results per page


def slugify(company_name):
    """'1-800-FLOWERS.COM, Inc.' -> '1-800-flowers-com-inc' (matches HRC's URL style)."""
    return re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-")


def get_hrc_score(company_name):
    """
    Look up one company's CEI rating. Returns a dict (see parse_detail_page),
    or None if HRC has no corporation page for it.

    Tries the guessed slug URL first (one request). Only if that 404s does it
    fall back to HRC's employer search (two or more requests). Returns None
    rather than a different company when the search has no real name match.

    Raises requests.HTTPError for anything other than a 404 on the slug guess
    (5xx, or a 429 that net.fetch gave up on), so the caller can retry later.
    """
    url = BASE_URL + DETAIL_PATH + slugify(company_name)
    matched_via = "slug"
    try:
        response = fetch(url)
    except requests.HTTPError as error:
        # net.fetch raises on every non-2xx. A 404 here only means our slug
        # guess was wrong, so fall back to search; anything else is real.
        if error.response is None or error.response.status_code != 404:
            raise
        logger.debug("HRC slug guess missed for %s, searching", company_name)
        time.sleep(POLITE_DELAY)
        url, matched_via = _search_for_detail_url(company_name)
        if url is None:
            logger.debug("HRC: no match for %s", company_name)
            return None
        time.sleep(POLITE_DELAY)
        response = fetch(url)

    result = parse_detail_page(response.text)
    result["url"] = url
    # How sure the match is: "slug" / "search" = same name. "search_prefix" /
    # "search_acronym" = weaker, see _search_for_detail_url.
    result["matched_via"] = matched_via
    logger.debug("HRC: %s -> %s, score %s (%s, via %s)", company_name, result["name"],
                result["score"], "verified" if result["verified"] else "unverified", matched_via)
    return result


def _name_tokens(text):
    """'Procter & Gamble Co.' or 'procter-gamble-co.' -> ['procter', 'gamble']."""
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in NAME_NOISE]


def _search_for_detail_url(company_name):
    """
    Search HRC and return (url, how) for the corporation that IS this company,
    or (None, None).

    HRC's search is a loose substring match that also searches brand names, so
    its first hit is often a different company ("Meta" -> A-Mark Precious
    Metals, "Stripe" -> Diageo, "HP" -> GlassBridge). So never take the first
    hit: compare each result's URL slug to the name we asked for.

        how == "search"          names are equal once Inc./Corp./etc. are dropped
        how == "search_prefix"   exactly one result STARTS with our name
                                 ("Cisco" -> "Cisco Systems Inc.")
        how == "search_acronym"  exactly one result's initials spell our name
                                 ("AMD" -> "Advanced Micro Devices Inc.")

    The last two are weaker; the caller may want to eyeball result["name"].

    Municipalities and hospitals live under other URL paths, so only
    /resources/corporations/ links are considered.
    """
    wanted = _name_tokens(company_name)
    if not wanted:
        return None, None

    slugs = {}  # slug -> absolute URL, in result order
    # net.fetch takes a bare URL, so the query string is built here.
    url = f"{SEARCH_URL}?{urlencode({'q': company_name})}"
    for page in range(1, MAX_SEARCH_PAGES + 1):
        if page > 1:
            time.sleep(POLITE_DELAY)
        soup = BeautifulSoup(fetch(url).text, "html.parser")
        for link in soup.find_all("a", href=re.compile(re.escape(DETAIL_PATH))):
            href = link["href"] if link["href"].startswith("http") else BASE_URL + link["href"]
            slugs.setdefault(href.rstrip("/").rsplit("/", 1)[1], href)
        # Pager is a "Next" link to .../search/p2?q=... (query string already in the href).
        # Matched on get_text, not find(string=...): the real link wraps "Next"
        # in a <span> with an arrow <svg>, which find(string=...) never matches.
        next_link = next((a for a in soup.find_all("a", href=True)
                          if a.get_text(strip=True) == "Next"), None)
        if next_link is None:
            break
        url = next_link["href"]
    else:
        logger.warning("HRC search for %s hit the %d-page cap; later results not checked",
                       company_name, MAX_SEARCH_PAGES)

    logger.debug("HRC search for %s: %d corporation results", company_name, len(slugs))
    tokens = {slug: _name_tokens(slug) for slug in slugs}

    for slug, found in tokens.items():
        if found == wanted:
            return slugs[slug], "search"

    prefix_hits = [slug for slug, found in tokens.items() if found[:len(wanted)] == wanted]
    if len(prefix_hits) == 1:
        return slugs[prefix_hits[0]], "search_prefix"

    # Acronyms only: one short word, matched against the initials of a multi-word name.
    if len(wanted) == 1 and 2 <= len(wanted[0]) <= 5:
        acronym_hits = [slug for slug, found in tokens.items()
                        if len(found) > 1 and "".join(t[0] for t in found) == wanted[0]]
        if len(acronym_hits) == 1:
            return slugs[acronym_hits[0]], "search_acronym"

    return None, None


def parse_detail_page(html):
    """
    Pull the rating out of a /resources/corporations/<slug> page.

    Returns:
        name, headquarters, industry   strings (None if missing)
        score                          int 0-100, or None if no score shown
        score_year                     int, e.g. 2026
        verified                       False when HRC labels the score "Unverified"
                                       (company did not submit that year's survey)
        criteria                       list of {name, label, points, earned, possible}

    Checked live against verified and unverified pages, scores from 55 to 100.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    h1 = main.find("h1")
    result = {
        "name": h1.get_text(strip=True) if h1 else None,
        "headquarters": _definition(main, "Headquarters"),
        "industry": _definition(main, "Industry"),
        "score": None,
        "score_year": None,
        "verified": None,
        "criteria": [],
    }

    # The score box has no id or stable class (its colour class likely changes
    # with the score), so anchor on the "2026 Score" label and read its parent:
    #   <div> 100 <p>Unverified</p> <p>2026 Score</p> </div>
    year_label = main.find("p", string=re.compile(r"\d{4}\s+Score"))
    if year_label is not None:
        box = year_label.parent
        result["score_year"] = int(re.search(r"\d{4}", year_label.get_text()).group())
        first_text = next(box.stripped_strings, "")
        if first_text.isdigit():
            result["score"] = int(first_text)
        result["verified"] = box.find("p", string=re.compile(r"Unverified", re.I)) is None

    # One <section> per criterion; name and points both use the heading-32 class.
    ratings = main.find("section", attrs={"data-label": "partial-criteria-sections"})
    for block in ratings.find_all("section") if ratings else []:
        name = block.find("h2")
        points = block.find("p", class_="heading-32")
        if name is None or points is None:
            continue
        points_text = points.get_text(strip=True)
        label = points.find_previous_sibling("p")
        # Criteria 1-4 read "5/5". Criteria 5 is a deduction and reads
        # "No Penalty", so earned/possible stay None for it.
        fraction = re.fullmatch(r"(-?\d+)\s*/\s*(\d+)", points_text)
        result["criteria"].append({
            "name": name.get_text(strip=True),
            "label": label.get_text(strip=True) if label else None,
            "points": points_text,
            "earned": int(fraction.group(1)) if fraction else None,
            "possible": int(fraction.group(2)) if fraction else None,
        })

    return result


def _definition(main, term):
    """Text of the <dd> following the <dt> labelled `term`, or None."""
    dt = main.find("dt", string=re.compile(rf"^\s*{term}\s*$", re.I))
    dd = dt.find_next_sibling("dd") if dt else None
    return dd.get_text(" ", strip=True) if dd else None


if __name__ == "__main__":
    # Standalone runs have no Django LOGGING config, so wire up the same console
    # handler settings.LOGGING uses: it keeps log lines off the live status line.
    from crawler.utils import TickerConsoleHandler
    logging.basicConfig(level=logging.INFO, handlers=[TickerConsoleHandler()],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if len(sys.argv) != 2:
        sys.exit('usage: python -m crawler.hrc_lookup "Company Name"')
    run_start = time.perf_counter()
    lookup  = get_hrc_score(sys.argv[1])
    print(json.dumps(lookup , indent=2) if lookup
          else f"No HRC corporation page found for {sys.argv[1]!r}")
    print(f"Done in {time.perf_counter() - run_start:.1f}s")
