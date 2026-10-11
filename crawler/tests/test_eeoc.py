"""
crawler/tests/test_eeoc.py

Tests for crawler.eeoc: reading a newsroom list page, saving releases,
re-deriving saved rows and marking duplicates.

These use Django's test database, which is created empty for the run and
dropped afterwards, so the real crawler_eeocaction table is never touched.
Nothing here reaches the EEOC website: scrape() is given canned pages in place
of fetch(), and the pause between pages is switched off. Run with

    python manage.py test crawler.tests.test_eeoc

What a release's text means (action type, employer, tags) is tested in the
other test_eeoc_*.py files. Here the text is only a way to get rows into the
table.
"""
import logging
from datetime import date
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase

from crawler import eeoc
from crawler.eeoc_classify import classify
from crawler.models.eeoc_actions import EeocAction, SetBy

LOGGER = "crawler.eeoc"     # the logger scrape() and reprocess() write to
QUIET = logging.NullHandler()


def setUpModule():      # pylint: disable=invalid-name
    """Keep the per-release progress lines off the screen and out of the log file while testing.

    assertLogs still sees them: it listens on the logger itself.
    """
    logger = logging.getLogger(LOGGER)
    logger.addHandler(QUIET)
    logger.propagate = False


def tearDownModule():   # pylint: disable=invalid-name
    """Put the logger back the way the settings had it."""
    logger = logging.getLogger(LOGGER)
    logger.removeHandler(QUIET)
    logger.propagate = True


def article(slug, title, teaser="", published="October 7, 2026"):
    """HTML for one press release, as it appears on a newsroom list page."""
    body = f'<div class="field--name-body">{teaser}</div>' if teaser is not None else ""
    when = f'<div class="field--name-field-published-date">{published}</div>' if published is not None else ""
    return (f'<div class="views-row"><article class="press_release">'
            f'<h2><a href="/newsroom/{slug}">{title}</a></h2>{body}{when}</article></div>')


def list_page(*articles):
    """HTML for a whole list page holding these articles."""
    return "<html><body><div class='view-content'>" + "".join(articles) + "</div></body></html>"


def fake_fetch(pages):
    """Stand-in for crawler.net.fetch: serves pages[n] for ?page=n, an empty page past the end.

    An entry that is an exception is raised instead of served.
    """
    def fetch(url):
        number = int(url.rsplit("page=", 1)[1])
        page = pages[number] if number < len(pages) else list_page()
        if isinstance(page, Exception):
            raise page
        return mock.Mock(text=page)
    return mock.Mock(side_effect=fetch)


def refused(status=403):
    """The error fetch() raises when the site turns a request down."""
    return requests.HTTPError(response=mock.Mock(status_code=status))


def save(title, teaser="", released_on=date(2026, 10, 7), slug=None, **fields):
    """Save one release with its derived fields filled in by the rules, as scrape() would."""
    values = {**classify(title, teaser), **fields}
    slug = slug or f"release-{EeocAction.objects.count() + 1}"
    return EeocAction.objects.create(url=f"{eeoc.BASE_URL}/newsroom/{slug}", title=title, teaser=teaser,
                                     released_on=released_on, **values)


SUED = article("acme-sued", "EEOC Sues Acme Tools for Age Discrimination",
               "Acme Tools, Inc. violated federal law by firing older workers, the EEOC charged.")
SETTLED = article("zenith-settles", "Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit",
                  "Zenith Works will pay $50,000 and furnish other relief.")
NEWS = article("eeoc-launches", "EEOC Launches E-File for Attorneys", "The agency announced a new portal.")
NO_NAME = article("no-name", "EEOC Wins Disability Bias Ruling",
                  "The U.S. Equal Employment Opportunity Commission (EEOC) today announced a ruling in its lawsuit.")
UNCLEAR = article("unclear", "Supreme Court Decision is Step Forward for Victims of Discrimination",
                  "In a unanimous decision, the U.S. Supreme Court held today that courts may only conduct a "
                  "bare-bones review of the EEOC's conciliation efforts.")


class ParseDateTests(SimpleTestCase):
    """parse_date reads the page's date field, then falls back to an old-style date in the teaser."""

    def test_date_field(self):
        """The normal case: 'October 7, 2026'."""
        self.assertEqual(eeoc.parse_date("October 7, 2026", ""), date(2026, 10, 7))

    def test_date_field_wins_over_the_teaser(self):
        """A date in the teaser is only a fallback."""
        self.assertEqual(eeoc.parse_date("October 7, 2026", "FOR RELEASE 12-8-97"), date(2026, 10, 7))

    def test_old_style_date_in_the_teaser_1990s(self):
        """'12-8-97' is December 8, 1997."""
        self.assertEqual(eeoc.parse_date("", "FOR IMMEDIATE RELEASE 12-8-97 WASHINGTON"), date(1997, 12, 8))

    def test_old_style_date_in_the_teaser_2000s(self):
        """A two-digit year below 90 is 20xx."""
        self.assertEqual(eeoc.parse_date("", "FOR IMMEDIATE RELEASE 3-15-04"), date(2004, 3, 15))

    def test_year_90_is_the_cut_between_centuries(self):
        """90 is 1990; 89 would be 2089, which no release uses."""
        self.assertEqual(eeoc.parse_date("", "1-2-90"), date(1990, 1, 2))
        self.assertEqual(eeoc.parse_date("", "1-2-00"), date(2000, 1, 2))

    def test_date_field_in_another_format_falls_back_to_the_teaser(self):
        """An unreadable field is not an error."""
        self.assertEqual(eeoc.parse_date("10/07/2026", "issued 12-8-97"), date(1997, 12, 8))

    def test_impossible_date_gives_none(self):
        """Month 13 stores nothing rather than crashing."""
        self.assertIsNone(eeoc.parse_date("", "case number 13-40-97"))

    def test_no_date_anywhere_gives_none(self):
        """Nothing to read."""
        self.assertIsNone(eeoc.parse_date("", "Acme will pay $50,000."))
        self.assertIsNone(eeoc.parse_date("", ""))


class ParseListPageTests(SimpleTestCase):
    """parse_list_page turns the list page's HTML into one dict per release."""

    def test_one_release(self):
        """Every stored field comes out of one article."""
        entry, = eeoc.parse_list_page(list_page(SUED))
        self.assertEqual(entry["url"], "https://www.eeoc.gov/newsroom/acme-sued")
        self.assertEqual(entry["title"], "EEOC Sues Acme Tools for Age Discrimination")
        self.assertTrue(entry["teaser"].startswith("Acme Tools, Inc. violated federal law"))
        self.assertEqual(entry["released_on"], date(2026, 10, 7))
        self.assertEqual(entry["action_type"], "sued")
        self.assertEqual(entry["employer_raw"], "Acme Tools")
        self.assertEqual(entry["employer_key"], "acme tools")
        self.assertEqual(entry["tags"], ["age"])
        self.assertIsNone(entry["amount"])

    def test_entry_has_exactly_the_model_fields_scrape_saves(self):
        """EeocAction(**entry) must work, so the keys have to be real field names."""
        entry, = eeoc.parse_list_page(list_page(SETTLED))
        self.assertEqual(set(entry), {"url", "title", "teaser", "released_on", *eeoc.DERIVED_FIELDS})
        row = EeocAction(**entry)
        self.assertEqual(row.amount, 50000)
        self.assertEqual(row.set_by, SetBy.RULES)

    def test_releases_come_back_in_page_order(self):
        """Newest first, as the page lists them."""
        entries = eeoc.parse_list_page(list_page(SUED, SETTLED, NEWS))
        self.assertEqual([e["url"].rsplit("/", 1)[1] for e in entries], ["acme-sued", "zenith-settles", "eeoc-launches"])

    def test_absolute_link_is_kept(self):
        """Only a relative link gets the site's address put in front."""
        html = list_page('<div class="views-row"><article><h2><a href="https://www.eeoc.gov/newsroom/full">'
                         'EEOC Sues Acme</a></h2></article></div>')
        self.assertEqual(eeoc.parse_list_page(html)[0]["url"], "https://www.eeoc.gov/newsroom/full")

    def test_article_without_a_link_is_skipped(self):
        """No headline link, no release."""
        html = list_page('<div class="views-row"><article><h2>No link here</h2></article></div>', SUED)
        self.assertEqual(len(eeoc.parse_list_page(html)), 1)

    def test_missing_teaser_and_date(self):
        """Both are optional on the page."""
        entry, = eeoc.parse_list_page(list_page(article("bare", "EEOC Sues Acme Tools", teaser=None, published=None)))
        self.assertEqual(entry["teaser"], "")
        self.assertIsNone(entry["released_on"])
        self.assertEqual(entry["employer_raw"], "Acme Tools")

    def test_old_release_takes_its_date_from_the_teaser(self):
        """1990s entries have no date field."""
        entry, = eeoc.parse_list_page(list_page(
            article("old", "EEOC SUES ACME TOOLS", teaser="FOR IMMEDIATE RELEASE 12-8-97", published=None)))
        self.assertEqual(entry["released_on"], date(1997, 12, 8))

    def test_long_title_and_teaser_are_cut_to_fit(self):
        """Title to the column's 500 characters, teaser to 1000."""
        entry, = eeoc.parse_list_page(list_page(article("long", "EEOC Sues Acme " + "x" * 600, teaser="y" * 1500)))
        self.assertEqual(len(entry["title"]), 500)
        self.assertEqual(len(entry["teaser"]), 1000)

    def test_markup_inside_the_teaser_is_flattened_to_text(self):
        """Tags inside the body do not end up in the stored teaser."""
        entry, = eeoc.parse_list_page(list_page(
            article("markup", "EEOC Sues Acme Tools", teaser="<p>Acme Tools <strong>violated</strong> the law.</p>")))
        self.assertEqual(entry["teaser"], "Acme Tools violated the law.")

    def test_page_with_no_releases(self):
        """Past the last page, or a page whose layout changed."""
        self.assertEqual(eeoc.parse_list_page(list_page()), [])
        self.assertEqual(eeoc.parse_list_page(""), [])

    def test_rows_outside_views_row_are_ignored(self):
        """Only the list's own rows count, not an article elsewhere on the page."""
        self.assertEqual(eeoc.parse_list_page("<article><h2><a href='/x'>Sidebar</a></h2></article>"), [])


class DescribeTests(SimpleTestCase):
    """describe() builds the one-line summary shown for each release."""

    def row(self, **fields):
        """An unsaved release with sensible defaults."""
        values = {"released_on": date(2026, 10, 7), "action_type": "sued", "employer_raw": "Acme Tools",
                  "tags": ["age", "retaliation"], "title": "EEOC Sues Acme Tools for Age Discrimination", **fields}
        return EeocAction(**values)

    def test_ordinary_release(self):
        """Date, action, employer, tags, headline."""
        self.assertEqual(eeoc.describe(self.row()),
                         "  2026-10-07 | sued         | Acme Tools | age, retaliation | "
                         "EEOC Sues Acme Tools for Age Discrimination")

    def test_announcement_says_so_instead_of_a_question_mark(self):
        """Agency news has no employer and that is not a miss."""
        line = eeoc.describe(self.row(action_type="announcement", employer_raw="", tags=[]))
        self.assertIn("| EEOC announcement |", line)

    def test_translation_says_so(self):
        """Same for the Spanish repeats."""
        line = eeoc.describe(self.row(action_type="translation", employer_raw="", tags=[]))
        self.assertIn("| Spanish translation |", line)

    def test_case_without_an_employer_shows_a_question_mark(self):
        """A real miss stands out."""
        self.assertIn("| ? |", eeoc.describe(self.row(employer_raw="")))

    def test_unclear_action_shows_a_dash(self):
        """A blank action type still fills its column."""
        self.assertIn("| -            |", eeoc.describe(self.row(action_type="")))

    def test_no_tags(self):
        """An empty tag list leaves the column empty."""
        self.assertIn("| Acme Tools |  | EEOC Sues", eeoc.describe(self.row(tags=[])))

    def test_long_headline_is_cut_at_150(self):
        """The line stays readable."""
        line = eeoc.describe(self.row(title="T" * 400))
        self.assertTrue(line.endswith(" | " + "T" * 150))

    def test_copy_is_marked(self):
        """A duplicate gets [copy] on the end; an original does not."""
        self.assertTrue(eeoc.describe(self.row(duplicate_of_id=7)).endswith("[copy]"))
        self.assertNotIn("[copy]", eeoc.describe(self.row()))

    def test_missing_date(self):
        """A release with no date still prints."""
        self.assertTrue(eeoc.describe(self.row(released_on=None)).startswith("  None | "))


class TitleKeyTests(SimpleTestCase):
    """title_key makes two copies of one headline compare equal."""

    def test_capitals_spacing_and_punctuation_do_not_matter(self):
        """The usual differences between archive copies."""
        self.assertEqual(eeoc.title_key("EEOC  Sues  ACME, Inc."), "eeoc sues acme inc")
        self.assertEqual(eeoc.title_key("EEOC Sues Acme, Inc."), eeoc.title_key("  eeoc sues acme inc  "))

    def test_html_entities_are_decoded_first(self):
        """DENNY&#39;S and DENNY'S are the same headline."""
        self.assertEqual(eeoc.title_key("DENNY&#39;S SUED"), eeoc.title_key("DENNY'S SUED"))
        self.assertEqual(eeoc.title_key("Sidley &amp; Austin"), eeoc.title_key("Sidley & Austin"))

    def test_different_headlines_stay_different(self):
        """Digits count: two amounts are two headlines."""
        self.assertNotEqual(eeoc.title_key("Acme to Pay $50,000"), eeoc.title_key("Acme to Pay $60,000"))

    def test_empty_title(self):
        """Nothing in, nothing out."""
        self.assertEqual(eeoc.title_key(""), "")


class MarkDuplicatesTests(TestCase):
    """mark_duplicates points a repeated release at the first copy saved."""

    def test_same_date_and_headline_under_two_urls(self):
        """The second row saved becomes the copy."""
        first = save("EEOC Sues Acme Tools for Age Discrimination")
        second = save("EEOC Sues Acme Tools for Age Discrimination")
        self.assertEqual(eeoc.mark_duplicates(), 1)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.duplicate_of)
        self.assertEqual(second.duplicate_of, first)

    def test_copies_that_differ_in_capitals_spacing_and_entities(self):
        """The archive's second copy is rarely character-for-character the same."""
        first = save("DENNY'S SUED BY EEOC FOR DISABILITY BIAS")
        second = save("Denny&#39;s  Sued by EEOC  for Disability Bias")
        eeoc.mark_duplicates()
        second.refresh_from_db()
        self.assertEqual(second.duplicate_of, first)

    def test_same_headline_on_another_date_is_a_separate_case(self):
        """One employer sued again years later is not a copy."""
        save("EEOC Sues Acme Tools for Age Discrimination", released_on=date(2019, 5, 1))
        save("EEOC Sues Acme Tools for Age Discrimination", released_on=date(2026, 10, 7))
        self.assertEqual(eeoc.mark_duplicates(), 0)
        self.assertEqual(EeocAction.objects.filter(duplicate_of__isnull=False).count(), 0)

    def test_different_headline_on_the_same_date_is_a_separate_release(self):
        """Two releases a day is normal."""
        save("EEOC Sues Acme Tools for Age Discrimination")
        save("EEOC Sues Zenith Works for Age Discrimination")
        self.assertEqual(eeoc.mark_duplicates(), 0)

    def test_three_copies_all_point_at_the_first(self):
        """Never a chain: every copy points at the original."""
        first = save("EEOC Sues Acme Tools")
        save("EEOC Sues Acme Tools")
        save("EEOC SUES ACME TOOLS")
        self.assertEqual(eeoc.mark_duplicates(), 2)
        self.assertEqual(set(EeocAction.objects.exclude(pk=first.pk).values_list("duplicate_of", flat=True)), {first.pk})

    def test_nothing_is_deleted(self):
        """Copies stay in the table, or the next backfill would save them again."""
        save("EEOC Sues Acme Tools")
        save("EEOC Sues Acme Tools")
        eeoc.mark_duplicates()
        self.assertEqual(EeocAction.objects.count(), 2)
        self.assertEqual(EeocAction.objects.filter(duplicate_of__isnull=True).count(), 1)

    def test_running_it_twice_changes_nothing(self):
        """It recomputes from scratch each time."""
        save("EEOC Sues Acme Tools")
        save("EEOC Sues Acme Tools")
        self.assertEqual(eeoc.mark_duplicates(), 1)
        before = list(EeocAction.objects.order_by("id").values_list("id", "duplicate_of"))
        self.assertEqual(eeoc.mark_duplicates(), 1)
        self.assertEqual(list(EeocAction.objects.order_by("id").values_list("id", "duplicate_of")), before)

    def test_a_stale_mark_is_cleared(self):
        """A row that no longer matches anything stops being a copy."""
        first = save("EEOC Sues Acme Tools")
        second = save("EEOC Sues Zenith Works", duplicate_of=first)
        self.assertEqual(eeoc.mark_duplicates(), 0)
        second.refresh_from_db()
        self.assertIsNone(second.duplicate_of)

    def test_undated_releases_with_one_headline_count_as_copies(self):
        """No date on either is treated as the same date."""
        first = save("EEOC SUES ACME TOOLS", released_on=None)
        second = save("EEOC SUES ACME TOOLS", released_on=None)
        eeoc.mark_duplicates()
        second.refresh_from_db()
        self.assertEqual(second.duplicate_of, first)

    def test_empty_table(self):
        """Nothing saved yet."""
        self.assertEqual(eeoc.mark_duplicates(), 0)


class ReprocessTests(TestCase):
    """reprocess() re-derives rows set by the rules and leaves the rest alone."""

    def stale(self, title="EEOC Sues Acme Tools for Age Discrimination", **fields):
        """A saved row whose derived fields are out of date, as after a rule change."""
        values = {"employer_raw": "WRONG", "employer_key": "wrong", "tags": [], "action_type": "", "amount": 1,
                  **fields}
        return save(title, **values)

    def test_stale_row_is_rewritten(self):
        """Every derived field is brought back in line with the text."""
        row = self.stale()
        self.assertEqual(eeoc.reprocess(), 1)
        row.refresh_from_db()
        self.assertEqual(row.employer_raw, "Acme Tools")
        self.assertEqual(row.employer_key, "acme tools")
        self.assertEqual(row.tags, ["age"])
        self.assertEqual(row.action_type, "sued")
        self.assertIsNone(row.amount)
        self.assertEqual(row.set_by, SetBy.RULES)

    def test_row_already_right_is_not_counted(self):
        """The return value is rows changed, not rows read."""
        save("EEOC Sues Acme Tools for Age Discrimination")
        self.assertEqual(eeoc.reprocess(), 0)

    def test_second_run_changes_nothing(self):
        """Once rewritten, a row matches the rules."""
        self.stale()
        self.stale("Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit")
        self.assertEqual(eeoc.reprocess(), 2)
        self.assertEqual(eeoc.reprocess(), 0)

    def test_only_the_stale_rows_are_counted(self):
        """One wrong row among right ones."""
        save("EEOC Sues Acme Tools for Age Discrimination")
        self.stale("Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit")
        save("EEOC Launches E-File for Attorneys")
        self.assertEqual(eeoc.reprocess(), 1)

    def test_one_field_out_of_date_is_enough(self):
        """A single stale field is rewritten and the others are left as they were."""
        row = save("Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit", amount=5)
        self.assertEqual(eeoc.reprocess(), 1)
        row.refresh_from_db()
        self.assertEqual(row.amount, 50000)
        self.assertEqual(row.employer_raw, "Zenith Works")

    def test_hand_set_row_survives(self):
        """What a person typed in the admin wins over the rules."""
        row = self.stale(employer_raw="Intel Corporation", employer_key="intel", tags=["age"],
                         action_type="settled", amount=15000000, set_by=SetBy.HAND)
        self.assertEqual(eeoc.reprocess(), 0)
        row.refresh_from_db()
        self.assertEqual(row.employer_raw, "Intel Corporation")
        self.assertEqual(row.employer_key, "intel")
        self.assertEqual(row.tags, ["age"])
        self.assertEqual(row.action_type, "settled")
        self.assertEqual(row.amount, 15000000)
        self.assertEqual(row.set_by, SetBy.HAND)

    def test_claude_set_row_survives(self):
        """Same protection for a row Claude set."""
        row = self.stale(employer_raw="Set By Claude", set_by=SetBy.CLAUDE)
        self.assertEqual(eeoc.reprocess(), 0)
        row.refresh_from_db()
        self.assertEqual(row.employer_raw, "Set By Claude")
        self.assertEqual(row.set_by, SetBy.CLAUDE)

    def test_hand_row_next_to_a_rules_row(self):
        """Only the rules row moves."""
        hand = self.stale(employer_raw="By Hand", set_by=SetBy.HAND)
        rules = self.stale("Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit")
        self.assertEqual(eeoc.reprocess(), 1)
        hand.refresh_from_db()
        rules.refresh_from_db()
        self.assertEqual(hand.employer_raw, "By Hand")
        self.assertEqual(rules.employer_raw, "Zenith Works")

    def test_text_and_url_are_never_touched(self):
        """Only the derived fields are rewritten."""
        row = self.stale()
        before = (row.url, row.title, row.teaser, row.released_on)
        eeoc.reprocess()
        row.refresh_from_db()
        self.assertEqual((row.url, row.title, row.teaser, row.released_on), before)

    def test_duplicates_are_marked_afterwards(self):
        """reprocess() ends by running mark_duplicates()."""
        first = save("EEOC Sues Acme Tools for Age Discrimination")
        second = save("EEOC Sues Acme Tools for Age Discrimination")
        eeoc.reprocess()
        second.refresh_from_db()
        self.assertEqual(second.duplicate_of, first)

    def test_a_copy_is_still_reprocessed(self):
        """Being a duplicate does not freeze a row's derived fields."""
        first = save("EEOC Sues Acme Tools for Age Discrimination")
        copy = self.stale(duplicate_of=first)
        self.assertEqual(eeoc.reprocess(), 1)
        copy.refresh_from_db()
        self.assertEqual(copy.employer_raw, "Acme Tools")
        self.assertEqual(copy.duplicate_of, first)

    def test_hand_set_row_can_still_be_marked_a_copy(self):
        """set_by protects the derived fields, not the duplicate mark."""
        first = save("EEOC Sues Acme Tools for Age Discrimination")
        hand = save("EEOC Sues Acme Tools for Age Discrimination", set_by=SetBy.HAND)
        eeoc.reprocess()
        hand.refresh_from_db()
        self.assertEqual(hand.duplicate_of, first)

    def test_empty_table(self):
        """Nothing saved yet."""
        self.assertEqual(eeoc.reprocess(), 0)

    def test_more_rows_than_one_batch(self):
        """bulk_update goes in batches of 500; all of them have to land."""
        EeocAction.objects.bulk_create([
            EeocAction(url=f"{eeoc.BASE_URL}/newsroom/bulk-{n}", title=f"EEOC Sues Acme Tools {n} for Retaliation",
                       released_on=date(2026, 10, 7), employer_raw="WRONG") for n in range(520)])
        self.assertEqual(eeoc.reprocess(), 520)
        self.assertEqual(EeocAction.objects.filter(employer_raw="WRONG").count(), 0)
        self.assertEqual(EeocAction.objects.filter(action_type="sued").count(), 520)

    def test_log_recap_lists_the_changed_row_with_old_and_new_values(self):
        """The block between the divider lines is what gets read after a run."""
        self.stale(employer_raw="WRONG", tags=["age"], action_type="sued", amount=None, employer_key="acme tools")
        with self.assertLogs(LOGGER, level="INFO") as logs:
            eeoc.reprocess()
        lines = [record.getMessage() for record in logs.records]
        self.assertIn("EEOC reprocess: the rows that changed:", lines)
        self.assertIn("      changed: employer_raw: 'WRONG' -> 'Acme Tools'", lines)
        self.assertEqual(lines.count(eeoc.DIVIDER_LINE), 2)
        self.assertIn("EEOC reprocess: 1 of 1 rows changed", lines)
        self.assertIn("  employer_raw changed on 1 rows", lines)
        self.assertIn("  tags         changed on 0 rows", lines)

    def test_log_summary_line_shows_the_row_as_it_now_stands(self):
        """The one-line summary of a changed row carries the new employer, not the old one."""
        self.stale(employer_raw="WRONG", tags=["age"], action_type="sued", amount=None, employer_key="acme tools")
        with self.assertLogs(LOGGER, level="INFO") as logs:
            eeoc.reprocess()
        summaries = [record.getMessage() for record in logs.records if "EEOC Sues Acme Tools" in record.getMessage()]
        self.assertTrue(summaries)
        for line in summaries:
            self.assertIn("| Acme Tools |", line)
            self.assertNotIn("| WRONG |", line)

    def test_log_has_no_recap_when_nothing_changed(self):
        """No divider lines on a quiet run."""
        save("EEOC Sues Acme Tools for Age Discrimination")
        with self.assertLogs(LOGGER, level="INFO") as logs:
            eeoc.reprocess()
        lines = [record.getMessage() for record in logs.records]
        self.assertNotIn(eeoc.DIVIDER_LINE, lines)
        self.assertIn("EEOC reprocess: 0 of 1 rows changed", lines)

    def test_log_counts_rows_left_alone_and_rows_without_a_name(self):
        """The opening and closing lines of the run."""
        save("EEOC Sues Acme Tools for Age Discrimination")
        save("EEOC Sues Acme Tools for Age Discrimination", set_by=SetBy.HAND)      # a copy, set by hand
        save("EEOC Wins Disability Bias Ruling")            # a case with no employer name
        save("EEOC Launches E-File for Attorneys")          # no name, but none expected
        with self.assertLogs(LOGGER, level="INFO") as logs:
            eeoc.reprocess()
        lines = [record.getMessage() for record in logs.records]
        self.assertIn("EEOC reprocess start: 3 rows set by rules, 1 set by hand or Claude left alone", lines)
        self.assertIn("EEOC duplicates: 1 of 4 releases marked as copies", lines)
        self.assertIn("  sued         1 releases", lines)             # the copy is not counted twice
        self.assertIn("  verdict      1 releases", lines)
        self.assertIn("  announcement 1 releases", lines)
        self.assertIn("EEOC reprocess done: 1 releases are about an employer but have no name", lines)


@mock.patch("crawler.eeoc.time.sleep")
class ScrapeTests(TestCase):
    """scrape() walks the list pages and saves what it has not seen. No network, no waiting."""

    def run_scrape(self, site, **options):
        """Run scrape() against a canned site (a list of pages). Returns (count saved, the fake fetch)."""
        fetch = fake_fetch(site)
        with mock.patch("crawler.eeoc.fetch", fetch):
            return eeoc.scrape(**options), fetch

    def fetched(self, fetch):
        """The page numbers that were asked for, in order."""
        return [int(call.args[0].rsplit("page=", 1)[1]) for call in fetch.call_args_list]

    def test_new_releases_are_saved(self, _sleep):
        """Each release on the page becomes one row with its derived fields."""
        saved, _fetch = self.run_scrape([list_page(SUED, SETTLED, NEWS)])
        self.assertEqual(saved, 3)
        self.assertEqual(EeocAction.objects.count(), 3)
        row = EeocAction.objects.get(url="https://www.eeoc.gov/newsroom/zenith-settles")
        self.assertEqual(row.title, "Zenith Works to Pay $50,000 to Settle EEOC Retaliation Suit")
        self.assertEqual(row.released_on, date(2026, 10, 7))
        self.assertEqual(row.employer_raw, "Zenith Works")
        self.assertEqual(row.action_type, "settled")
        self.assertEqual(row.tags, ["retaliation"])
        self.assertEqual(row.amount, 50000)
        self.assertEqual(row.set_by, SetBy.RULES)
        self.assertIsNone(row.duplicate_of)

    def test_list_url_is_asked_for_by_page_number(self, _sleep):
        """Page 0 first, at the newsroom search address."""
        _saved, fetch = self.run_scrape([list_page(SUED)])
        self.assertEqual(fetch.call_args_list[0].args[0], "https://www.eeoc.gov/newsroom/search?page=0")

    def test_release_already_saved_is_skipped(self, _sleep):
        """The URL is the key: a known one is not saved again or changed."""
        self.run_scrape([list_page(SUED)])
        EeocAction.objects.update(employer_raw="Fixed By Hand", set_by=SetBy.HAND)
        saved, _fetch = self.run_scrape([list_page(SUED, SETTLED)])
        self.assertEqual(saved, 1)
        self.assertEqual(EeocAction.objects.count(), 2)
        self.assertEqual(EeocAction.objects.get(url__endswith="acme-sued").employer_raw, "Fixed By Hand")

    def test_routine_run_stops_at_the_first_page_with_nothing_new(self, _sleep):
        """Caught up: no reason to read the other 300 pages."""
        self.run_scrape([list_page(SUED)])
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED)])
        self.assertEqual(saved, 0)
        self.assertEqual(self.fetched(fetch), [0])
        self.assertEqual(EeocAction.objects.count(), 1)

    def test_routine_run_keeps_going_while_pages_have_something_new(self, _sleep):
        """Stops only after the page that had nothing."""
        self.run_scrape([list_page(NEWS)])
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED), list_page(NEWS), list_page(UNCLEAR)])
        self.assertEqual(saved, 2)
        self.assertEqual(self.fetched(fetch), [0, 1, 2])

    def test_full_run_goes_past_pages_already_saved(self, _sleep):
        """The backfill: known pages are read through, not a reason to stop."""
        self.run_scrape([list_page(SUED)])
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED)], full=True)
        self.assertEqual(saved, 1)
        self.assertEqual(self.fetched(fetch), [0, 1, 2])        # page 2 is the empty one that ends it

    def test_stops_at_the_first_empty_page(self, _sleep):
        """Past the end of the archive."""
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED)], full=True)
        self.assertEqual(saved, 2)
        self.assertEqual(self.fetched(fetch), [0, 1, 2])

    def test_empty_first_page_is_reported_as_a_parser_problem(self, _sleep):
        """Page 0 always has releases, so nothing there means the HTML changed."""
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            saved, fetch = self.run_scrape([list_page()])
        self.assertEqual(saved, 0)
        self.assertEqual(self.fetched(fetch), [0])
        self.assertIn("page 0 parsed 0 entries", logs.output[0])

    def test_pages_limits_how_many_are_read(self, _sleep):
        """pages=2 reads two pages."""
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED), list_page(NEWS)], pages=2)
        self.assertEqual(saved, 2)
        self.assertEqual(self.fetched(fetch), [0, 1])

    def test_start_page_resumes_part_way(self, _sleep):
        """A cut-off backfill picks up where it stopped."""
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED), list_page(NEWS)],
                                       start_page=1, full=True)
        self.assertEqual(saved, 2)
        self.assertEqual(self.fetched(fetch), [1, 2, 3])
        self.assertFalse(EeocAction.objects.filter(url__endswith="acme-sued").exists())

    def test_never_reads_past_max_pages(self, _sleep):
        """The hard stop holds even when asked for more."""
        with mock.patch("crawler.eeoc.MAX_PAGES", 2):
            _saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED), list_page(NEWS)], pages=50, full=True)
        self.assertEqual(self.fetched(fetch), [0, 1])

    def test_limit_stops_after_that_many_saved(self, _sleep):
        """limit=2 saves the first two and reads no further."""
        saved, fetch = self.run_scrape([list_page(SUED, SETTLED, NEWS), list_page(UNCLEAR)], limit=2)
        self.assertEqual(saved, 2)
        self.assertEqual(EeocAction.objects.count(), 2)
        self.assertFalse(EeocAction.objects.filter(url__endswith="eeoc-launches").exists())
        self.assertEqual(self.fetched(fetch), [0])

    def test_limit_carries_across_pages(self, _sleep):
        """One from page 0, then only one more from page 1."""
        saved, fetch = self.run_scrape([list_page(SUED), list_page(SETTLED, NEWS)], limit=2)
        self.assertEqual(saved, 2)
        self.assertEqual(self.fetched(fetch), [0, 1])
        self.assertFalse(EeocAction.objects.filter(url__endswith="eeoc-launches").exists())

    def test_dry_run_saves_nothing(self, _sleep):
        """It shows what it parsed and leaves the table alone."""
        with self.assertLogs(LOGGER, level="INFO") as logs:
            saved, _fetch = self.run_scrape([list_page(SUED, SETTLED)], dry_run=True)
        self.assertEqual(saved, 0)
        self.assertEqual(EeocAction.objects.count(), 0)
        shown = "\n".join(logs.output)
        self.assertIn("| Acme Tools |", shown)
        self.assertIn("| Zenith Works |", shown)

    def test_refused_page_stops_cleanly_and_keeps_what_was_saved(self, _sleep):
        """A 403 part-way through is not a crash, and the log says how to resume."""
        with self.assertLogs(LOGGER, level="ERROR") as logs:
            saved, fetch = self.run_scrape([list_page(SUED), refused(403), list_page(SETTLED)], full=True)
        self.assertEqual(saved, 1)
        self.assertEqual(EeocAction.objects.count(), 1)
        self.assertEqual(self.fetched(fetch), [0, 1])
        self.assertIn("page 1 refused (HTTP 403)", logs.output[0])
        self.assertIn("--full --start-page 1", logs.output[0])

    def test_refused_first_page_saves_nothing(self, _sleep):
        """Blocked from the start."""
        with self.assertLogs(LOGGER, level="ERROR"):
            saved, _fetch = self.run_scrape([refused(429)])
        self.assertEqual(saved, 0)

    def test_same_url_on_two_pages_is_saved_once(self, _sleep):
        """The list shifts while it is being read, so a release can show up twice."""
        saved, _fetch = self.run_scrape([list_page(SUED, SETTLED), list_page(SETTLED, NEWS)], full=True)
        self.assertEqual(saved, 3)
        self.assertEqual(EeocAction.objects.count(), 3)

    def test_same_url_twice_on_one_page_does_not_crash(self, _sleep):
        """The unique URL column would reject the second; it is skipped instead."""
        self.run_scrape([list_page(SUED, SUED)])
        self.assertEqual(EeocAction.objects.count(), 1)

    def test_waits_between_pages_and_not_after_the_last(self, sleep):
        """PAGE_DELAY seconds after each page that leads to another."""
        self.run_scrape([list_page(SUED), list_page(SETTLED)], full=True)
        self.assertEqual(sleep.call_args_list, [mock.call(eeoc.PAGE_DELAY), mock.call(eeoc.PAGE_DELAY)])

    def test_no_wait_when_the_run_stops_on_its_first_page(self, sleep):
        """Nothing new on page 0: stop without sleeping."""
        self.run_scrape([list_page(SUED)])
        sleep.reset_mock()
        self.run_scrape([list_page(SUED)])
        sleep.assert_not_called()

    def test_new_case_without_an_employer_is_flagged(self, _sleep):
        """Same test as the admin's 'No employer name' filter."""
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.run_scrape([list_page(SUED, NO_NAME)])
        shown = "\n".join(logs.output)
        self.assertIn("1 NEW RELEASES NEED A LOOK", shown)
        self.assertIn("EEOC Wins Disability Bias Ruling", shown)
        self.assertIn("https://www.eeoc.gov/newsroom/no-name", shown)
        self.assertNotIn("Acme Tools", shown)

    def test_new_release_with_an_unclear_action_is_flagged(self, _sleep):
        """Same test as the admin's 'Unclear action type' filter."""
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            self.run_scrape([list_page(UNCLEAR)])
        self.assertIn("1 NEW RELEASES NEED A LOOK", "\n".join(logs.output))

    def test_announcement_without_an_employer_is_not_flagged(self, _sleep):
        """Agency news has no employer and needs no look."""
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_scrape([list_page(SUED, SETTLED, NEWS)])

    def test_release_already_saved_is_not_flagged_again(self, _sleep):
        """Only new rows are flagged, or every run would repeat the list."""
        with self.assertLogs(LOGGER, level="WARNING"):
            self.run_scrape([list_page(NO_NAME)])
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_scrape([list_page(SUED, NO_NAME)])

    def test_dry_run_flags_nothing(self, _sleep):
        """Nothing was saved, so nothing needs a look yet."""
        with self.assertNoLogs(LOGGER, level="WARNING"):
            self.run_scrape([list_page(NO_NAME)], dry_run=True)

    def test_log_says_how_many_were_saved(self, _sleep):
        """The closing line of a run."""
        with self.assertLogs(LOGGER, level="INFO") as logs:
            self.run_scrape([list_page(SUED, SETTLED)])
        lines = [record.getMessage() for record in logs.records]
        self.assertIn("EEOC page 0: 2 found, 2 new", lines)
        self.assertEqual(lines[-1], "EEOC scrape done: 2 new releases saved")

    def test_saved_rows_can_be_reprocessed_without_change(self, _sleep):
        """What scrape() stores is exactly what reprocess() would derive."""
        self.run_scrape([list_page(SUED, SETTLED, NEWS, NO_NAME, UNCLEAR)])
        self.assertEqual(eeoc.reprocess(), 0)
