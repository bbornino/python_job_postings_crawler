"""
crawler/tests/test_eeoc_tags.py

Tests for the tags crawler.eeoc_classify sets: wording that must set each tag,
look-alike wording that must not, and the law-boilerplate filter on the teaser.
No database and no network. Run this file alone with

    python manage.py test crawler.tests.test_eeoc_tags

or every EEOC test with

    python manage.py test crawler.tests

Every row of a table becomes its own test (see one_test_per_case in
eeoc_testing.py). A row that says "made up" or uses "Acme" / "Zenith Works"
is invented to pin down one wording. Everything else is a real EEOC headline.
"""
from django.test import SimpleTestCase

from crawler.eeoc_classify import TAG_PATTERNS, classify, without_law_boilerplate
from crawler.tests.eeoc_testing import one_test_per_case


# (tag, text that must set it). The text is used as a headline with no teaser.
# One row per kind of wording the tag's pattern knows.
TAG_PRESENT = [
    ("age", "Acme Sued for Age Discrimination"),
    ("age", "Acme Settles Age-Bias Suit"),
    ("age", "Acme to Pay $50,000 to Settle Age Harassment Claims"),
    ("age", "Acme Accused of Ageism"),
    ("age", "Acme Violated the ADEA, EEOC Says"),
    ("age", "Acme Laid Off Older Workers, EEOC Charges"),
    ("age", "Acme Rejected Applicants Over the Age of 40"),
    ("age", "Acme Refused to Hire Workers Age 40 and Older"),
    ("age", "Acme Fired Manager Due to His Age, EEOC Says"),
    ("age", "Acme Sued Regarding the Manager's Age"),
    ("age", "Acme Sued for Race, Sex, National Origin and Age Bias"),
    ("age", "Acme Replaced Them With Younger Employees Who Were Paid Less"),
    ("age", "Acme Fired Nurse Because of Her Age"),
    ("age", "Acme Sued on the Basis of Age"),
    ("age", "Acme Sued for Age and Sex Discrimination"),
    *[("age", f"Acme Settles Age {word}") for word in ("Suit", "Lawsuit", "Claims", "Charges")],
    ("age", "Acme Sued Over Age-Based Layoffs"),
    *[("age", f"Acme Laid Off Older {who}, EEOC Charges")
      for who in ("Employees", "Applicants", "Agents", "Staff", "Individuals", "Women", "Men")],
    *[("age", f"Acme Sued Over {other} and Age") for other in ("Race", "Gender", "Disability", "Religion", "Color")],
    ("age", "Acme Sued Over Sex and Age"),
    ("age", "Acme Sued Over National Origin and Age"),
    ("trans", "Acme Sued for Firing Transgender Employee"),
    ("trans", "Acme Sued for Gender Identity Discrimination"),
    ("lgbtq", "Acme Sued for Sexual Orientation Discrimination"),
    ("lgbtq", "EEOC Sues Acme Over Treatment of LGBTQ Workers"),
    ("lgbtq", "Acme Harassed Gay Employee, EEOC Charges"),
    ("lgbtq", "Acme Fired Lesbian Manager, EEOC Says"),
    ("pro_trans", "EEOC Sues Acme Over Access to Single-Sex Spaces at Work"),
    ("pro_trans", "Acme Let Biological Men Use Women's Locker Room, EEOC Charges"),
    ("pro_trans", "Acme Forced Biologically Male Employee on Coworkers, EEOC Says"),
    *[("pro_trans", f"EEOC Sues Acme Over Policy on Biological {word}") for word in ("Sex", "Women", "Females")],
    ("pro_trans", "EEOC Sues Acme Over Gender Ideology Policy"),
    ("pro_trans", "Acme Denied Women Access to Intimate Spaces, EEOC Says"),
    ("pro_trans", "EEOC Sues Acme Over Sex-Rejecting Procedures Coverage"),
    ("pro_dei", "EEOC Sues Acme Over DEI Program"),
    ("pro_dei", "EEOC Sues Acme Over Diversity, Equity and Inclusion Training"),
    ("pro_dei", "EEOC Sues Acme Over Diversity Equity Hiring Goals"),
    ("pro_dei", "EEOC Challenges Acme Diversity Program"),
    ("pro_dei", "EEOC Challenges Acme Diversity Initiative"),
    ("pro_dei", "EEOC Challenges Acme Diversity Policies"),
    ("sex", "Acme Sued for Sex Discrimination"),
    ("sex", "Acme Sued for Sex-Based Wage Discrimination"),
    ("sex", "Acme Settles Sex Bias Suit"),
    ("sex", "Acme Sued for Sex-Based Harassment"),
    ("sex", "Acme Sued for Gender Discrimination"),
    ("sex", "Acme Sued for Gender-Based Pay Bias"),
    ("sex", "Acme Fired Worker Based on Sex, EEOC Says"),
    ("sex", "Acme Fired Welder Because of Her Sex"),
    ("sex", "Acme Sued for Refusing to Hire Women"),
    ("sex", "Acme Sued for Discriminating Against Women"),
    ("sex", "Acme Sued for Bias Against Female Drivers"),
    ("sex", "Acme Sued for Paying Women Less Than Men"),
    ("sex", "Acme Sued for Paying Female Managers Less"),
    ("sex", "Acme Refused to Hire Females, EEOC Says"),
    ("sex", "Acme Blocked Hiring of Women for Dock Jobs"),
    ("sex", "Acme Sued for Gender-Based Hiring"),
    ("sex", "Acme Denied Jobs to Qualified Women, EEOC Says"),
    ("sex", "Acme Fired Staff Based on Age (Over 40), Sex and Race"),
    ("sex", "Acme Sued for Sex and Age Bias"),
    ("sex", "Acme Sued for Sex/Race Harassment"),
    ("sex", "Acme Fired Welders Because of Their Sex"),
    *[("sex", f"Acme Sued Over {other} and Sex") for other in ("Color", "Religion", "National Origin", "Disability")],
    *[("sex", f"Acme Sued Over Sex and {other}") for other in ("Color", "National Origin", "Disability")],
    *[("sex", f"Acme Sued Over Sex and {other}") for other in ("Age", "Race", "Religion")],
    ("sex", "Acme Accused of Gender Bias"),
    ("religion", "Acme Sued for Religious Discrimination"),
    ("religion", "Acme Fired Muslim Driver, EEOC Says"),
    ("religion", "Acme Sued Over Antisemitic Harassment"),
    ("religion", "Acme Refused to Hire Sikh Applicant"),
    ("religion", "Acme Fired Worker for Wearing Hijab"),
    ("religion", "Acme Fired Worker Who Observed the Sabbath"),
    ("national_origin", "Acme Sued for National Origin Discrimination"),
    ("national_origin", "Acme Sued Over Anti-Immigrant Slurs"),
    ("national_origin", "Acme Sued for Ethnic Harassment"),
    ("national_origin", "Acme Favored Non-Hispanic Workers, EEOC Says"),
    ("national_origin", "Acme Sued Over 9/11 Backlash Firing"),
    ("national_origin", "Acme Sued for Paying Hispanic Workers Less"),
    ("national_origin", "Acme Sued for Discriminating Against Hispanics"),
    ("national_origin", "Acme Sued for Harassment of Latino Employees"),
    ("national_origin", "Acme Segregated Filipino Nurses, EEOC Says"),
    ("national_origin", "Acme Sued for Bias Against Haitian Workers"),
    ("visa_preference", "Acme Favored H-1B Workers Over Americans, EEOC Says"),
    ("visa_preference", "Acme Preferred Visa Holders, EEOC Charges"),
    ("visa_preference", "Acme Sued for Visa-Based Hiring"),
    ("visa_preference", "Acme Sued for Bias Against American Workers"),
    ("visa_preference", "Acme Sued for Discriminating Against U.S. Workers"),
    ("visa_preference", "Acme Favored Foreign Workers, EEOC Says"),
    ("visa_preference", "Acme Sued for Preferring Visa Workers"),
    ("visa_preference", "Acme Hired Based on Visa Status, EEOC Says"),
    ("visa_preference", "Acme Sued for Bias Against Domestic Workers"),
    ("visa_preference", "Acme Hired Only Visa Holders, EEOC Says"),
    ("visa_preference", "Acme Hired Only Visa Workers, EEOC Says"),
    ("race", "Acme Sued for Race Discrimination"),
    ("race", "Acme Sued for Race-Based Harassment"),
    ("race", "Acme Sued for Racial Harassment"),
    ("race", "Acme Sued Over Racial Slurs"),
    ("race", "Acme Sued for Racially Hostile Workplace"),
    ("race", "Acme Fired Clerk Because of His Race"),
    ("race", "Acme Refused Promotions on the Basis of Race"),
    ("race", "Acme Refused to Hire African-Americans, EEOC Says"),
    ("race", "Acme Sued for Bias Against Black Applicants"),
    ("race", "Acme Fired Black Employees, EEOC Says"),
    ("race", "Acme Excluded Minorities From Sales Jobs"),
    ("race", "Acme Sued for Sex and Race Bias"),
    ("race", "Acme Sued for Race and National Origin Harassment"),
    ("race", "Acme Sued for Race, Color and Religious Discrimination"),
    ("race", "Acme Sued for Race Harassment"),
    ("race", "Acme Sued for Racial Discrimination"),
    ("race", "Acme Sued for Racial Bias"),
    ("race", "Acme Sued for Bias Against Non-White Staff"),
    ("race", "Acme Fired Black Workers, EEOC Says"),
    ("race", "Acme Rejected Black Job Candidates, EEOC Says"),
    *[("race", f"Acme Sued Over {other} and Race")
      for other in ("Age", "Gender", "Color", "Religion", "National Origin", "Disability")],
    *[("race", f"Acme Sued Over Race and {other}") for other in ("Age", "Gender", "Religion", "Disability")],
    *[("race", f"Acme Sued Over Race and {other}") for other in ("Color", "National Origin")],
    ("race", "Acme Accused of Race Bias"),
    ("race", "Acme Accused of Bias Against Black Staff"),
    ("race", "Acme Rejected Black Applicants, EEOC Says"),
    ("race", "Acme Settles Race & Pay Discrimination Claims"),
    ("pregnancy", "Acme Sued for Pregnancy Discrimination"),
    ("pregnancy", "Acme Fired Pregnant Worker, EEOC Says"),
    ("pregnancy", "Acme Violated the PWFA, EEOC Charges"),
    ("pregnancy", "Acme Denied Breaks to Use Breast Pump"),
    ("pregnancy", "Acme Fired Nursing Mother, EEOC Says"),
    ("pregnancy", "Acme Refused Lactation Breaks"),
    ("pregnancy", "Acme Fired Worker After Maternity Leave"),
    ("retaliation", "Acme Sued for Retaliation"),
    ("retaliation", "Acme Retaliated Against Whistleblower, EEOC Says"),
    ("harassment", "Acme Sued for Sexual Harassment"),
    ("harassment", "Acme Manager Harassed Teen Workers, EEOC Says"),
    ("hostile_env", "Acme Sued for Hostile Work Environment"),
    ("disability", "Acme Sued for Disability Discrimination"),
    ("disability", "Acme Settles Disability Bias Suit"),
    ("disability", "Acme Denied Disability Accommodation, EEOC Says"),
    ("disability", "Acme Violated the ADA, EEOC Charges"),
    ("disability", "Acme Sued Under Americans with Disabilities Act"),
    ("disability", "Acme Fired Disabled Workers, EEOC Says"),
    ("disability", "Acme Fired Employee With a Disability"),
    ("disability", "Acme Rejected Applicants With Disabilities"),
    ("disability", "Acme Fired Cashier Because of Her Disability"),
    ("disability", "Acme Refused to Hire Deaf Applicant"),
    ("disability", "Acme Fired Blind Employee, EEOC Says"),
    ("disability", "Acme Rejected Hearing-Impaired Applicant"),
    ("disability", "Acme Fired Worker With HIV, EEOC Says"),
    ("disability", "Acme Fired Veteran With PTSD, EEOC Says"),
    ("disability", "Acme Fired Worker With Bipolar Disorder"),
    ("disability", "Acme Fired Worker With Epilepsy"),
    ("disability", "Acme Fired Diabetic Driver, EEOC Says"),
    ("disability", "Acme Fired Worker With Cancer, EEOC Says"),
    ("disability", "Acme Fired Worker Who Uses a Wheelchair"),
    ("disability", "Acme Fired Worker With Autism, EEOC Says"),
    ("disability", "Acme Fired Amputee, EEOC Says"),
    ("disability", "Acme Fired Worker Over Medical Condition"),
    ("disability", "Acme Made Illegal Medical Inquiries, EEOC Says"),
    ("disability", "Acme Sued for Disability and Age Discrimination"),
    ("disability", "Acme Ignored EEOC Disability Finding"),
    ("disability", "Acme Sued by EEOC for Disability"),
    ("disability", "Acme Fired Clerk Due to His Disability"),
    ("disability", "Acme Fired Worker With Vision Impairment"),
    ("disability", "Acme Fired Paraplegic Worker, EEOC Says"),
    ("disability", "Acme Fired Quadriplegic Worker, EEOC Says"),
    ("disability", "Acme Fired Worker With Tourette Syndrome"),
    ("disability", "Acme Sued Over Fitness-for-Duty Policy"),
    ("disability", "Acme Required Illegal Medical Exams, EEOC Says"),
    ("disability", "Acme Fired Worker on Medical Leave"),
    ("disability", "Acme Fired Worker Who Took Leave for Knee Surgery"),
    ("disability", "Acme Fired Worker Who Used Crutches"),
    ("disability", "Acme Sued for Race and Disability Bias"),
    *[("disability", f"Acme Settles Disability {word}") for word in ("Harassment", "Charge", "Case", "Claim")],
    ("disability", "Acme Fired Disabled Employees, EEOC Says"),
    ("disability", "Acme Rejected Disabled Applicants, EEOC Says"),
    ("disability", "Acme Fired Workers With Disabilities"),
    ("disability", "Acme Demanded Medical Information From Applicants"),
    ("disability", "Acme Sued Over Medical Leave Policy"),
    ("disability", "Acme Sued for Disability, Race Discrimination"),
    ("disability", "Acme Sued for Disability or Race Discrimination"),
    ("disability", "Acme Sued for Disability & Race Discrimination"),
    ("disability", "Acme Blocked EEOC Disability Investigation"),
    ("disability", "Acme Ignored Charge of Disability, EEOC Says"),
    ("disability", "Acme Refused to Treat Her Disability as Real"),
    ("disability", "Acme Required Medical Examinations, EEOC Says"),
    ("disability", "Acme Demanded Medical Releases, EEOC Says"),
    *[("disability", f"Acme Sued Over {other} and Disability")
      for other in ("Sex", "Gender", "Color", "Religion", "National Origin")],
    *[("disability", f"Acme Sued Over {other} and Disability") for other in ("Age", "Race")],
    ("disability", "Acme Accused of Disability Discrimination"),
    ("disability", "Acme Accused of Disability Bias"),
    ("disability", "Acme Settles Disability Lawsuit"),
    ("disability", "Acme Settles Disability Suit"),
    *[("disability", f"Acme Settles Disability{joiner} Race Discrimination Claims") for joiner in (",", " and", " or", " &")],
    ("genetic_info", "Acme Sued for Genetic Information Discrimination"),
    ("genetic_info", "Acme Violated Genetic Non-Discrimination Law"),
    ("genetic_info", "EEOC Sues Acme Over Genetic Testing of Workers"),
    ("genetic_info", "Acme Asked Applicants for Family Medical History"),
    ("genetic_info", "Acme Asked About Medical History of Employees' Family Members"),
    ("genetic_info", "Acme Violated GINA, EEOC Says"),
    ("genetic_info", "Acme Sued for Genetic Discrimination"),
    ("genetic_info", "Acme Sued for Genetic Bias"),
    ("equal_pay", "Acme Sued for Equal Pay Act Violation"),
    ("equal_pay", "Acme Sued for Unequal Pay"),
    ("equal_pay", "Acme Sued for Pay Discrimination"),
    ("equal_pay", "Acme Sued for Wage Discrimination"),
    ("equal_pay", "Acme Sued Over Pay Disparity"),
    ("equal_pay", "Acme Sued for Sex-Based Pay Gap"),
    ("equal_pay", "Acme Sued for Gender-Based Wage Gap"),
    ("equal_pay", "Acme Paid Her Less Than Male Peers, EEOC Says"),
    ("equal_pay", "Acme Sued for Paying Female Managers Less"),
]


# (tag, text that must NOT set it). Each is a mistake the patterns made once or
# would make if loosened.
TAG_ABSENT = [
    ("age", "Acme Sued for Wage Discrimination"),                   # "wage" contains "age"
    ("age", "Page Company Sued for Sexual Harassment"),
    ("age", "Acme Management Sued for Sexual Harassment"),
    ("age", "Acme Sued for Harassing Teenage Workers"),
    ("age", "Adea Foods Sued for Retaliation"),                     # the acronym is case-sensitive
    ("trans", "Acme Transportation Sued for Retaliation"),
    ("lgbtq", "Gaylord Hotel Sued for Retaliation"),
    ("pro_dei", "Deidre's Diner Sued for Retaliation"),
    ("pro_dei", "EEOC Celebrates Diversity at Annual Event"),
    ("sex", "Acme Sued for Sexual Harassment"),                     # harassment, not sex discrimination
    ("sex", "Acme Sued for Same-Sex Harassment"),
    ("sex", "Sussex County Sued for Retaliation"),
    ("religion", "Acme Sued for Retaliation in the Region"),
    ("national_origin", "Hispanic Employee Sexually Harassed, EEOC Says"),      # who the victim is, not why
    ("national_origin", "Acme Sued for Sexual Harassment of Teens"),
    ("visa_preference", "Visalia Farm Sued for Retaliation"),
    ("race", "Acme Race Track Sued for Sexual Harassment"),
    ("race", "Grace Hospital Sued for Retaliation"),
    ("race", "Acme Sued for Sexual Harassment of Bracero Workers"),
    ("pregnancy", "Acme Sued for Retaliation"),
    ("retaliation", "Acme Sued for Sexual Harassment"),
    ("harassment", "Acme Sued for Retaliation"),
    ("hostile_env", "Acme Sued for Hostile Takeover Dispute"),
    ("disability", "Disability Services Provider Sued for Sexual Harassment"),  # describes the employer
    ("disability", "Ada's Diner Sued for Sexual Harassment"),                   # "Ada" is not "ADA"
    ("disability", "Acme Refused Reasonable Accommodation for Sabbath, EEOC Says"),
    ("disability", "Acme Sued Over Hiv-Tex Fabric Dispute"),
    ("genetic_info", "Gina's Pizza Sued for Sexual Harassment"),
    ("genetic_info", "Acme Fired Worker Over Medical Condition"),
    ("equal_pay", "Acme to Pay $50,000 for Sexual Harassment"),
    ("equal_pay", "Acme Sued for Failing to Pay Overtime to Women"),
]


# Tags come from the teaser too, except its sentences that only recite the law.
# (what the case shows, teaser, tags expected from an untagged headline)
TEASER_TAG_CASES = [
    ("the teaser supplies the tags",
     "Acme fired a clerk because of her race and then retaliated against a coworker who complained.",
     ["race", "retaliation"]),
    ("a sentence listing what Title VII covers adds nothing",
     "Acme fired a clerk because of her race. Title VII prohibits employment discrimination on the basis of sex, "
     "race, color, national origin and religion.",
     ["race"]),
    ("a sentence listing the statutes adds nothing",
     "Acme fired a pregnant clerk. The EEOC enforces Title VII, the ADA, the ADEA and the Equal Pay Act.",
     ["pregnancy"]),
    ("one law named in the case's own sentence still counts",
     "Acme violated the Americans with Disabilities Act (ADA) by firing a clerk.",
     ["disability"]),
    ("'prohibits' with one class is about this case and counts",
     "Acme violated Title VII, which prohibits discrimination based on sex.",
     ["sex"]),
    ("tags are stored in the order the model lists them, not the order found",
     "Acme was sued for retaliation and age discrimination.",
     ["age", "retaliation"]),
    ("Spanish wording in the teaser of an English headline",
     "Acme violó la ley federal: discriminación por discapacidad.",
     ["disability"]),
    ("no topic in the text: no tags",
     "Acme will pay $50,000 and furnish other relief, the agency announced today.",
     []),
]


@one_test_per_case(TAG_PRESENT)
class TagPresentTests(SimpleTestCase):
    """Each kind of wording a tag's pattern knows sets that tag."""

    def check(self, tag, text):
        """Check one row of the table."""
        self.assertIn(tag, classify(text, "")["tags"])


@one_test_per_case(TAG_ABSENT)
class TagAbsentTests(SimpleTestCase):
    """Look-alike wording does not set the tag."""

    def check(self, tag, text):
        """Check one row of the table."""
        self.assertNotIn(tag, classify(text, "")["tags"])


@one_test_per_case(TEASER_TAG_CASES)
class TeaserTagTests(SimpleTestCase):
    """Tags from the teaser, minus its law-boilerplate sentences."""

    def check(self, _why, teaser, tags):
        """Check one row of the table."""
        self.assertEqual(classify("Acme Sued by EEOC", teaser)["tags"], tags)


class TagTableTests(SimpleTestCase):
    """The tag tables have to keep up with TAG_PATTERNS."""

    def test_every_tag_has_a_present_and_an_absent_case(self):
        """A tag added to TAG_PATTERNS without rows here fails this test."""
        self.assertEqual({tag for tag, _text in TAG_PRESENT}, set(TAG_PATTERNS))
        self.assertEqual({tag for tag, _text in TAG_ABSENT}, set(TAG_PATTERNS) - {"pro_trans"})

    def test_tags_are_a_list_of_known_names(self):
        """Tags come back as a plain list, in TAG_PATTERNS order."""
        tags = classify("Acme Sued for Age, Race and Disability Discrimination and Retaliation", "")["tags"]
        self.assertIsInstance(tags, list)
        self.assertEqual(tags, ["age", "race", "retaliation", "disability"])


# (teaser, teaser with the law-boilerplate sentences removed)
BOILERPLATE_CASES = [
    ("Acme fired a worker because of her race. Title VII is a federal statute that prohibits employment "
     "discrimination on the basis of sex, race, color, national origin and religion.",
     "Acme fired a worker because of her race."),
    ("Acme fired a worker. The law forbids discrimination because of age, disability or genetic information. "
     "The suit was filed today.",
     "Acme fired a worker. The suit was filed today."),
    ("Acme fired a worker. Federal law makes it illegal to discriminate based on race, sex or religion.",
     "Acme fired a worker."),
    ("Acme fired a worker. The EEOC enforces Title VII, the ADA, the ADEA and GINA.",
     "Acme fired a worker."),
    ("Acme fired a worker. The law prohibits bias based on gender identity, sexual orientation or pregnancy.",
     "Acme fired a worker."),
    ("Acme fired a worker. The law prohibits bias based on color, religion or pregnancy.",
     "Acme fired a worker."),
    ("Acme fired a worker. The law prohibits bias based on national origin, religion or pregnancy.",
     "Acme fired a worker."),
    ("Acme fired a worker. The law prohibits bias based on race, sex or disability.",
     "Acme fired a worker."),
    ("Acme fired a worker. The law prohibits bias based on age, genetic information or disabilities.",
     "Acme fired a worker."),
    ("Acme fired a worker. Cases arise under the Equal Pay Act, the Rehabilitation Act and the Pregnant Workers "
     "Fairness Act.",
     "Acme fired a worker."),
    # left alone
    ("The suit was filed under the Americans with Disabilities Act (ADA) and the ADEA.",
     "The suit was filed under the Americans with Disabilities Act (ADA) and the ADEA."),     # two laws, not three
    ("Acme violated Title VII, which prohibits discrimination based on sex.",
     "Acme violated Title VII, which prohibits discrimination based on sex."),               # one class
    ("Acme fired workers because of race, sex and age.",
     "Acme fired workers because of race, sex and age."),          # three classes but no 'prohibits': the case itself
    ("Acme prohibits beards. A Sikh applicant was rejected.",
     "Acme prohibits beards. A Sikh applicant was rejected."),
    ("", ""),
]


@one_test_per_case(BOILERPLATE_CASES)
class LawBoilerplateTests(SimpleTestCase):
    """without_law_boilerplate drops sentences that only recite the law."""

    def check(self, teaser, expected):
        """Check one row of the table."""
        self.assertEqual(without_law_boilerplate(teaser), expected)
