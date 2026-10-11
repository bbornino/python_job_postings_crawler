"""
crawler/tests/test_hrc_lookup.py

Tests for crawler/hrc_lookup.py. No network: net.fetch is mocked, and time.sleep
is patched out so the polite delays don't slow the suite down.

    python manage.py test crawler.tests.test_hrc_lookup

Fixtures in crawler/tests/fixtures/ are real hrc.org pages saved on 2026-10-11:
    hrc_abbott_laboratories.html   unverified 100
    hrc_apple_inc.html             verified 100
    hrc_tesla_inc.html             unverified 55, partial criteria points
    hrc_search_hp.html             search for "HP": GlassBridge, HPE, HP Inc. + hospitals
    hrc_search_meta_p1.html        search for "Meta", page 1 of 2 (has the real "Next" link)

If HRC redesigns its pages, the parser tests fail here first. Re-save the
fixtures from the live site and fix parse_detail_page to match.

The matching-logic tests use small hand-built search pages (search_page below)
instead, so each test shows exactly which results the matcher was choosing from.
"""

from pathlib import Path
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from crawler import hrc_lookup
from crawler.hrc_lookup import _name_tokens, get_hrc_score, parse_detail_page, slugify

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CORP = hrc_lookup.BASE_URL + hrc_lookup.DETAIL_PATH   # https://www.hrc.org/resources/corporations/
SEARCH = hrc_lookup.SEARCH_URL


def fixture(name):
    """Text of a saved hrc.org page."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:  # pylint: disable=too-few-public-methods
    """Stands in for requests.Response; hrc_lookup only ever reads .text."""

    def __init__(self, text):
        self.text = text


def http_error(status):
    """The requests.HTTPError net.fetch raises for a non-2xx status."""
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def search_page(*slugs, next_url=None):
    """Minimal HRC search results page linking to each corporation slug.

    Includes a hospital link on every page, so the tests also prove that
    non-corporation results are ignored.
    """
    links = "".join(f'<a href="{CORP}{slug}">View detail</a>' for slug in slugs)
    links += '<a href="https://www.hrc.org/resources/healthcare-facilities/some-hospital">x</a>'
    pager = f'<a href="{next_url}">Next</a>' if next_url else ""
    return f"<html><body><main>{links}{pager}</main></body></html>"


def fake_site(pages):
    """A side_effect for the mocked fetch: URL -> page text, or a status code to raise.

    Any URL not in `pages` is a 404, which is what hrc.org does for a bad slug.
    Every requested URL is recorded in .calls, in order.
    """
    def fetch(url):
        fetch.calls.append(url)
        page = pages.get(url, 404)
        if isinstance(page, int):
            raise http_error(page)
        return FakeResponse(page)

    fetch.calls = []
    return fetch


def search_url(query):
    """The first-page search URL hrc_lookup builds for `query`."""
    return f"{SEARCH}?{requests.compat.urlencode({'q': query})}"


class SlugifyTests(SimpleTestCase):
    """slugify: our guess at HRC's URL slug for a company name."""

    def test_lowercases_and_hyphenates(self):
        self.assertEqual(slugify("Abbott Laboratories"), "abbott-laboratories")

    def test_punctuation_runs_collapse_to_one_hyphen(self):
        self.assertEqual(slugify("1-800-FLOWERS.COM, Inc."), "1-800-flowers-com-inc")

    def test_no_leading_or_trailing_hyphens(self):
        self.assertEqual(slugify("  (Acme) "), "acme")


class NameTokensTests(SimpleTestCase):
    """_name_tokens: the normalized form names and slugs are compared in."""

    def test_drops_legal_form_words(self):
        self.assertEqual(_name_tokens("Procter & Gamble Co."), ["procter", "gamble"])

    def test_slug_and_name_normalize_the_same(self):
        self.assertEqual(_name_tokens("amazon-com-inc."), _name_tokens("Amazon"))

    def test_all_noise_gives_empty_list(self):
        self.assertEqual(_name_tokens("The Company, Inc."), [])


class ParseDetailPageTests(SimpleTestCase):
    """parse_detail_page against real saved HRC pages."""

    def test_unverified_page(self):
        result = parse_detail_page(fixture("hrc_abbott_laboratories.html"))
        self.assertEqual(result["name"], "Abbott Laboratories")
        self.assertEqual(result["headquarters"], "Abbott Park, IL")
        self.assertEqual(result["industry"], "Healthcare")
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["score_year"], 2026)
        self.assertIs(result["verified"], False)

    def test_verified_page(self):
        result = parse_detail_page(fixture("hrc_apple_inc.html"))
        self.assertEqual(result["name"], "Apple Inc.")
        self.assertEqual(result["score"], 100)
        self.assertIs(result["verified"], True)

    def test_low_score_and_partial_criteria(self):
        # The case that matters most: a low score is the only real red flag.
        result = parse_detail_page(fixture("hrc_tesla_inc.html"))
        self.assertEqual(result["score"], 55)
        benefits = next(c for c in result["criteria"] if c["name"] == "Inclusive Benefits")
        self.assertEqual((benefits["earned"], benefits["possible"]), (35, 50))

    def test_criteria_list(self):
        criteria = parse_detail_page(fixture("hrc_abbott_laboratories.html"))["criteria"]
        self.assertEqual([c["name"] for c in criteria], [
            "Workforce Protections", "Inclusive Benefits", "Inclusive Culture",
            "Outreach and Engagement", "Responsible Citizenship",
        ])
        self.assertEqual(criteria[0]["points"], "5/5")
        self.assertEqual((criteria[0]["earned"], criteria[0]["possible"]), (5, 5))

    def test_penalty_criterion_has_no_fraction(self):
        # Criteria 5 is a deduction shown as "No Penalty", not "x/y".
        last = parse_detail_page(fixture("hrc_abbott_laboratories.html"))["criteria"][-1]
        self.assertEqual(last["label"], "Points Deducted")
        self.assertEqual(last["points"], "No Penalty")
        self.assertIsNone(last["earned"])
        self.assertIsNone(last["possible"])

    def test_page_without_rating_returns_empty_fields(self):
        # Layout change or wrong page: empty fields, not an exception.
        result = parse_detail_page("<html><body><main><h1>Someone</h1></main></body></html>")
        self.assertEqual(result["name"], "Someone")
        self.assertIsNone(result["score"])
        self.assertIsNone(result["verified"])
        self.assertEqual(result["criteria"], [])


@patch("crawler.hrc_lookup.time.sleep")
class GetHrcScoreTests(SimpleTestCase):
    """get_hrc_score end to end, with fetch mocked. Class-level patch passes
    the sleep mock into every test as `_sleep`."""

    def run_lookup(self, name, pages):
        """Look up `name` against a fake site; returns (result, urls fetched)."""
        site = fake_site(pages)
        with patch("crawler.hrc_lookup.fetch", side_effect=site):
            result = get_hrc_score(name)
        return result, site.calls

    def test_slug_hit_takes_one_request(self, _sleep):
        url = CORP + "abbott-laboratories"
        result, calls = self.run_lookup("Abbott Laboratories",
                                        {url: fixture("hrc_abbott_laboratories.html")})
        self.assertEqual(calls, [url])
        self.assertEqual(result["matched_via"], "slug")
        self.assertEqual(result["url"], url)
        self.assertEqual(result["score"], 100)

    def test_slug_miss_falls_back_to_search(self, _sleep):
        # Real HP search page: the first hit is GlassBridge, which must NOT win.
        result, calls = self.run_lookup("HP", {
            search_url("HP"): fixture("hrc_search_hp.html"),
            CORP + "hp-inc.": fixture("hrc_apple_inc.html"),  # any detail page will do
        })
        self.assertEqual(calls, [CORP + "hp", search_url("HP"), CORP + "hp-inc."])
        self.assertEqual(result["matched_via"], "search")
        self.assertEqual(result["url"], CORP + "hp-inc.")

    def test_search_with_no_real_match_returns_none(self, _sleep):
        # "Stripe" really returns Diageo (brand match); that must not be used.
        result, calls = self.run_lookup("Stripe", {
            search_url("Stripe"): search_page("diageo-north-america"),
        })
        self.assertIsNone(result)
        self.assertEqual(len(calls), 2)   # slug guess + one search page, no detail fetch

    def test_prefix_match(self, _sleep):
        result, _ = self.run_lookup("Cisco", {
            search_url("Cisco"): search_page("cisco-systems-inc.", "sysco-corp."),
            CORP + "cisco-systems-inc.": fixture("hrc_apple_inc.html"),
        })
        self.assertEqual(result["matched_via"], "search_prefix")

    def test_ambiguous_prefix_returns_none(self, _sleep):
        result, _ = self.run_lookup("American", {
            search_url("American"): search_page("american-airlines-group", "american-express-co."),
        })
        self.assertIsNone(result)

    def test_exact_match_beats_prefix(self, _sleep):
        result, _ = self.run_lookup("Target", {
            search_url("Target"): search_page("target-hospitality", "target-corp."),
            CORP + "target-corp.": fixture("hrc_apple_inc.html"),
        })
        self.assertEqual(result["url"], CORP + "target-corp.")
        self.assertEqual(result["matched_via"], "search")

    def test_acronym_match(self, _sleep):
        result, _ = self.run_lookup("AMD", {
            search_url("AMD"): search_page("advanced-micro-devices-inc.", "amdocs-ltd."),
            CORP + "advanced-micro-devices-inc.": fixture("hrc_apple_inc.html"),
        })
        self.assertEqual(result["matched_via"], "search_acronym")

    def test_ambiguous_acronym_returns_none(self, _sleep):
        result, _ = self.run_lookup("AMD", {
            search_url("AMD"): search_page("advanced-micro-devices-inc.", "applied-medical-devices"),
        })
        self.assertIsNone(result)

    def test_follows_next_link_to_page_two(self, _sleep):
        # Real page 1, so the real "Next" link markup is what gets followed.
        # Meta Platforms is on that page today, so it's renamed out of it to
        # force the search on to page 2 (hand-built), where it is.
        page_one = fixture("hrc_search_meta_p1.html").replace("meta-platforms-inc.", "renamed-out")
        page_two = hrc_lookup.SEARCH_URL + "/p2?q=Meta"
        result, calls = self.run_lookup("Meta", {
            search_url("Meta"): page_one,
            page_two: search_page("meta-platforms-inc."),
            CORP + "meta-platforms-inc.": fixture("hrc_apple_inc.html"),
        })
        self.assertIn(page_two, calls)
        self.assertEqual(result["url"], CORP + "meta-platforms-inc.")

    def test_stops_at_page_cap(self, _sleep):
        # Every page says "Next"; the loop must stop at MAX_SEARCH_PAGES.
        pages = {}
        for n in range(1, 10):
            url = search_url("Loop") if n == 1 else f"{SEARCH}/p{n}?q=Loop"
            pages[url] = search_page(f"other-{n}", next_url=f"{SEARCH}/p{n + 1}?q=Loop")
        with self.assertLogs("crawler.hrc_lookup", level="WARNING"):
            result, calls = self.run_lookup("Loop", pages)
        self.assertIsNone(result)
        self.assertEqual(len(calls), 1 + hrc_lookup.MAX_SEARCH_PAGES)   # slug guess + capped pages

    def test_non_404_error_is_raised(self, _sleep):
        # A 500 (or a 429 net.fetch gave up on) is not "not rated": let it raise.
        with self.assertRaises(requests.HTTPError):
            self.run_lookup("Abbott Laboratories", {CORP + "abbott-laboratories": 500})

    def test_name_that_is_only_noise_returns_none(self, _sleep):
        result, calls = self.run_lookup("Inc.", {})
        self.assertIsNone(result)
        self.assertEqual(calls, [CORP + "inc"])   # slug guess only, no search

    def test_waits_between_requests(self, sleep):
        self.run_lookup("Stripe", {search_url("Stripe"): search_page()})
        sleep.assert_called_with(hrc_lookup.POLITE_DELAY)
