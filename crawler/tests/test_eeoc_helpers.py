"""
crawler/tests/test_eeoc_helpers.py

Tests for the two small helpers in crawler.eeoc_classify: parse_amount and
employer_key.
No database and no network. Run this file alone with

    python manage.py test crawler.tests.test_eeoc_helpers

or every EEOC test with

    python manage.py test crawler.tests

Every row of a table becomes its own test (see one_test_per_case in
eeoc_testing.py). A row that says "made up" or uses "Acme" / "Zenith Works"
is invented to pin down one wording. Everything else is a real EEOC headline.
"""
from django.test import SimpleTestCase

from crawler.eeoc_classify import classify, employer_key, parse_amount
from crawler.tests.eeoc_testing import one_test_per_case


# (headline, amount in whole dollars or None)
AMOUNT_CASES = [
    ("Acme to Pay $85,000 in Suit", 85000),
    ("Acme to Pay $1.55 Million", 1550000),
    ("ACME TO PAY $2 MILLION", 2000000),
    ("Acme to Pay $1.2 Billion", 1200000000),
    ("Acme to Pay $ 40,000", 40000),
    ("Acme to Pay $1,525,000", 1525000),
    ("Acme to Pay $130,691.50", 130691),
    ("Rizza Cadillac to Pay $100K to Three Arab Muslim Employees Under Federal Consent Decree", 100000),
    ("Wild Fork Foods to Pay $130k to Settle EEOC Suit", 130000),
    ("Acme to Pay $1.5K", 1500),
    ("Acme to Pay $50,000 Kroger Workers", 50000),      # a K that starts the next word is not a unit
    ("Acme to Pay $60 K Street Workers", 60),           # nor is one standing apart from the number
    ("Acme to Pay $50,000 Now and $1 Million Later", 50000),    # the first figure
    ("Acme to Pay Half Million", None),
    ("EEOC Sues Acme", None),
    ("Acme to Pay 40,000 Dollars", None),
]


# (name, key). The key is what two spellings of one employer share.
KEY_CASES = [
    ("Wal-Mart Stores, Inc.", "walmart stores"),
    ("Walmart Stores", "walmart stores"),
    ("JACO Enterprises, LLC", "jaco enterprises"),
    ("Sidley & Austin", "sidley and austin"),
    ("The Kroger Company", "kroger"),
    ("Kroger Co.", "kroger"),
    ("AT&T Corp.", "at and t"),
    ("McDonald's Corporation", "mcdonalds"),
    ("Meadowbrook Meat Co., Ltd.", "meadowbrook meat"),
    # accented letters lose the accent, not the letter
    ("Señor Frog's", "senor frogs"),
    ("Swami’s Café and Honey’s Bistro", "swamis cafe and honeys bistro"),
    ("Estée Lauder", "estee lauder"),
    ("Nestlé Waters North America", "nestle waters north america"),
    ("Cañon City Chili’s Restaurant", "canon city chilis restaurant"),
    ("Senor Frog's", "senor frogs"),                    # typed without the accent: same key
    ("", ""),
    ("Inc.", ""),
    # every word that is dropped as noise
    *[(f"Zenith Works {noise}", "zenith works")
      for noise in ("Inc", "Inc.", "Incorporated", "LLC", "L.L.C.", "Corp", "Corp.", "Corporation", "Co", "Co.",
                    "Company", "Ltd", "Ltd.", "LP", "L.P.", "LLP")],
    ("The Zenith Works", "zenith works"),
    ("ZENITH   WORKS", "zenith works"),
    ("Zenith-Works", "zenithworks"),
    # a slash separates two names, with or without spaces around it
    ("Olive Garden/GMRI Inc.", "olive garden gmri"),
    ("Regis Corporation/Smart Style Family Hair Salon", "regis smart style family hair salon"),
    ("Sunshine Raisin / National Raisin", "sunshine raisin national raisin"),
    ("Awon Phie LLC D/B/A Holiday Inn", "awon phie dba holiday inn"),
    ("Zenith Works Group", "zenith works group"),       # "Group" is part of the name
]


@one_test_per_case(AMOUNT_CASES)
class AmountTests(SimpleTestCase):
    """parse_amount reads the first dollar figure in a headline."""

    def check(self, title, amount):
        """Check one row of the table."""
        self.assertEqual(parse_amount(title), amount)
        self.assertEqual(classify(title, "")["amount"], amount)


@one_test_per_case(KEY_CASES)
class EmployerKeyTests(SimpleTestCase):
    """employer_key collapses spellings of one employer to one key."""

    def check(self, name, key):
        """Check one row of the table."""
        self.assertEqual(employer_key(name), key)
