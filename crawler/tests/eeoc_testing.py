"""
crawler/tests/eeoc_testing.py

Shared helpers for the EEOC test files. Not a test file itself: the name does
not start with test_, so the test runner does not collect it.
"""
import re

from crawler.eeoc_classify import EMPLOYER_REGEXES, NOT_A_NAME


def one_test_per_case(cases):
    """Class decorator: add one test method per row of cases.

    Each method calls self.check(*row), so a class only has to say how one row
    is checked. The method name carries the row number and the start of the
    row's text, which is what shows up when a test fails.
    """
    def decorate(cls):
        for number, case in enumerate(cases, 1):
            row = tuple(case.values()) if isinstance(case, dict) else case
            label = re.sub(r"\W+", "_", " ".join(str(part) for part in row[:2]))[:60].strip("_")

            def test(self, row=row):
                self.check(*row)
            test.__doc__ = f"{cls.__name__} row {number}: {row[0]}"
            setattr(cls, f"test_{number:03}_{label}", test)
        return cls
    return decorate


def winning_pattern(title):
    """Index of the first EMPLOYER_PATTERNS entry that gives a usable name, as classify() picks it."""
    for index, regex in enumerate(EMPLOYER_REGEXES):
        match = regex.search(title)
        if match and not NOT_A_NAME.search(match.group("name").strip()):
            return index
    return None
