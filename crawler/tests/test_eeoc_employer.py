"""
crawler/tests/test_eeoc_employer.py

Tests for the employer name: crawler.eeoc_classify finding it in the headline,
finding it in the teaser, and combining the two.
No database and no network. Run this file alone with

    python manage.py test crawler.tests.test_eeoc_employer

or every EEOC test with

    python manage.py test crawler.tests

Every row of a table becomes its own test (see one_test_per_case in
eeoc_testing.py). A row that says "made up" or uses "Acme" / "Zenith Works"
is invented to pin down one wording. Everything else is a real EEOC headline.

    EMPLOYER_HEADLINES    every headline shape in EMPLOYER_PATTERNS, on real headlines
    EMPLOYER_WORDINGS     every verb and ending those patterns accept, on made-up ones
    NO_EMPLOYER_HEADLINES headlines that name nobody
    TEASER_OPENINGS       every way the teaser carries the name
    NAME_CASES            how the headline and the teaser are combined into one name
    GENERIC_..., LEAD_IN_..., NOT_NAMES ...   one row per word in the long word lists
"""
from html import unescape

from django.test import SimpleTestCase

from crawler.eeoc_classify import (
    EMPLOYER_REGEXES,
    NOT_A_NAME,
    classify,
    clean_teaser_name,
    employer_key,
    looks_generic,
    without_lead_in,
)
from crawler.tests.eeoc_testing import one_test_per_case, winning_pattern


# (index into EMPLOYER_PATTERNS, headline, employer name). Real headlines, no
# teaser, so the name comes from that one pattern and nothing else.
EMPLOYER_HEADLINES = [
    (0, "EEOC Sues Royal Tire for Pay Bias", "Royal Tire"),
    (0, "EEOC Sues Olympia Construction", "Olympia Construction"),                 # headline ends at the name
    (0, "EEOC Sues Bigfoot Energy Services and Iron Mountain Energy", "Bigfoot Energy Services and Iron Mountain Energy"),
    (0, "EEOC Sues Damar Services, Inc., for Disability Discrimination", "Damar Services, Inc."),
    (0, "EEOC Sued Wal-Mart Stores for Disability Discrimination", "Wal-Mart Stores"),
    (1, "WAL-MART AGREES TO AIR TV AD AND PAY $427,500 AFTER COURT FINDS RETAILER IN CONTEMPT OF COURT", "WAL-MART"),
    (2, "WAL-MART VIOLATES DISABILITIES ACT AGAIN; EEOC FILES 16TH ADA SUIT AGAINST RETAIL GIANT", "WAL-MART"),
    (3, "Papa John's Discriminated Against Employee with Down Syndrome, EEOC Charges in Suit", "Papa John's"),
    (3, "SOUTHEASTERN TELECOM RETALIATED AGAINST ACCOUNT EXECUTIVE, EEOC CHARGES IN SUIT", "SOUTHEASTERN TELECOM"),
    (4, "Federal Court Refuses To Toss Out EEOC Claim That Chrysler Retaliated Against Employees", "Chrysler"),
    (4, "Jury in EEOC Suit Finds that RockAuto Discriminated Against Applicant Because of His Age", "RockAuto"),
    (4, "APPEALS COURT REVERSES DECISION THAT BOEING'S MESA PLANT DID NOT ENGAGE IN SEX HARASSMENT", "BOEING"),
    (5, "U.S. Supreme Court Denies United Airlines Petition", "United Airlines"),
    (5, "Court Denies Key Menards Motion in EEOC Pregnancy Discrimination Case", "Menards"),
    (5, "Federal Court Allows EEOC Disability Case to Proceed, Denying United Parcel Service's Appeal",
     "United Parcel Service"),
    (6, "U.S. SUPREME COURT DENIAL OF REVIEW ENDS SIDLEY & AUSTIN BID TO AVOID MONETARY RELIEF ISSUE IN AGE BIAS CASE",
     "SIDLEY & AUSTIN"),
    (7, "JUDGE SLAPS WAL-MART WITH MAJOR SANCTIONS FOR VIOLATING COURT ORDER IN EEOC DISABILITY BIAS CASE", "WAL-MART"),
    (7, "COURT OF APPEALS RULES TARGET MUST FACE TRIAL ON RACE DISCRIMINATION CHARGES", "TARGET"),
    (8, "Federal Court Approves EEOC Subpoena in Investigation of Union Pacific", "Union Pacific"),
    (9, "EEOC INVESTIGATING FEDEX ON CHARGES OF COMPANYWIDE RACE, NATIONAL ORIGIN DISCRIMINATION", "FEDEX"),
    (10, "Aerotek Required by Federal Appeals Court to Comply with EEOC Subpoena", "Aerotek"),
    (10, "Patterson UTI Drilling must Comply with Subpoena by EEOC and Disclose Databases on Workforce",
     "Patterson UTI Drilling"),
    (10, "L.A. WEIGHT LOSS TO FACE TRIAL FOR SEX BIAS AND RETALIATION", "L.A. WEIGHT LOSS"),
    (10, "Scion Dental, a Unit of SkyGen USA, Ordered to Face Trial for Race Discrimination in EEOC Suit",
     "Scion Dental, a Unit of SkyGen USA"),
    (11, "Henry's Turkey Service, Heirs Must Turn over Almost $600,000 Owed to Disabled Workers", "Henry's Turkey Service"),
    (12, "RACIAL HARASSMENT AND RETALIATION COSTS R.S. BRASWELL / BOBCAT OF MONROE $21,000",
     "R.S. BRASWELL / BOBCAT OF MONROE"),
    (12, "FORCED RETIREMENT COSTS DAWES COUNTY $50,000 IN AGE BIAS SETTLEMENT WITH EEOC", "DAWES COUNTY"),
    (13, "In Settlement with EEOC, Acme Agrees to Pay $50,000 to Fired Workers", "Acme"),        # made up
    (14, "EEOC OBTAINS $1 MILLION FOR LOW-WAGE WORKERS WHO WERE SEXUALLY HARASSED AT FOOD PROCESSING PLANT",
     "FOOD PROCESSING PLANT"),
    (15, "EEOC, Quietflex Manufacturing Company, L.P., and Others Announce Final Approval of Settlement with "
         "Hispanic Employees on Discrimination Claims", "Quietflex Manufacturing Company, L.P."),
    (16, "Hyatt to Provide $100,000 in Pay and Benefits to Settle EEOC Disability Discrimination Suit", "Hyatt"),
    (16, "Astra USA Agrees To Provide $10 Million To Victims Of Discrimination", "Astra USA"),
    (16, "Jacksonville Plumbers Training Trust to Revise Apprentice Selection Process to Settle EEOC Race "
         "Discrimination Lawsuit", "Jacksonville Plumbers Training Trust"),
    (16, "Restaurant Group Ordered to Implement Sexual Harassment Prevention", "Restaurant Group"),
    (17, "EEOC Charges AZ Metro Distributors with Age Discrimination", "AZ Metro Distributors"),
    (17, "EEOC Charges Sidley &amp; Austin With Age Discrimination", "Sidley & Austin"),
    (18, "Acme Waste Removal Admits Discrimination, Settles With EEOC For $95,000", "Acme Waste Removal"),   # made up
    (19, "JURY ORDERS HARRIS FARMS TO PAY $994,000 IN SEXUAL HARASSMENT SUIT BY EEOC", "HARRIS FARMS"),
    (19, "Court Orders Waikiki Sports Bar to Pay Over $250,000 for Sexual Harassment", "Waikiki Sports Bar"),
    (19, "FEDERAL COURT ORDERS AARON BROTHERS TO PRODUCE DOCUMENTS IN EEOC INVESTIGATION", "AARON BROTHERS"),
    (20, "U-Haul Sued for Racial Harassment", "U-Haul"),
    (20, "B. J. Con-Sew Sued By EEOC", "B. J. Con-Sew"),
    (20, "Sonic Drive-In Sued by EEOC for Sexual Harassment", "Sonic Drive-In"),
    (21, "EEOC AND WALGREENS RESOLVE LAWSUIT", "WALGREENS"),
    (21, "EEOC AND JOSEPHTHAL & CO., INC. SETTLE HARASSMENT SUIT", "JOSEPHTHAL & CO., INC."),
    (22, "Wal-Mart Settles EEOC Lawsuit for $50,000", "Wal-Mart"),
    (22, "Rite Way to Settle EEOC Retaliation Suit", "Rite Way"),
    (22, "ABM Resolves EEOC Disability Charge", "ABM"),
    (22, "Kroger to Pay $40,000 to Settle EEOC Disability Discrimination Lawsuit", "Kroger"),
    (22, "Town of Elkton Will Pay $235,000 to Resolve EEOC Age Discrimination Lawsuit", "Town of Elkton"),
    (22, "RYAN'S FAMILY STEAKHOUSE PAYS $500,000 FOR RACE BIAS, SEX DISCRIMINATION AND RETALIATION",
     "RYAN'S FAMILY STEAKHOUSE"),
    (22, "O'Reilly Automotive Consents to Early Entry of Decree Resolving EEOC Sexual Harassment Suit",
     "O'Reilly Automotive"),
    (22, "Swami’s Café and Honey’s Bistro Pay $650,000 in EEOC Sexual Harassment Suit",
     "Swami’s Café and Honey’s Bistro"),
    (23, "Court Holds Sherwood Food Distributors in Contempt for Violation of EEOC Consent Decree in Class Sex "
         "Discrimination Case", "Sherwood Food Distributors"),
    (23, "Federal Judge Finds Global Horizons Liable for Discriminating, Harassing, and Retaliating Against "
         "Hundreds of Thai Farm Workers in EEOC Suit", "Global Horizons"),
    (24, "Cannon & Wendt Held in Contempt for Failure to Comply Fully with Consent Decree", "Cannon & Wendt"),
    (25, "EEOC Obtains Judgment Ordering Ceviche House to Pay $130,691 for Sexual Harassment", "Ceviche House"),
    (25, "Court Reaffirms Imposition of Order Preventing UPS Freight from Paying Disabled Drivers Less", "UPS Freight"),
    (26, "EEOC Obtains $2.75 Million from WRS Compass for Victims of Race Harassment at Clean-Up Site", "WRS Compass"),
    (26, "EEOC Obtains Over $66,000 from Moonshine Group and True Country for Pregnancy Discrimination",
     "Moonshine Group and True Country"),
    (27, "EEOC Releases UPS from Future Consent Decree Reporting Obligations", "UPS"),
    (28, "EEOC v. Activision Blizzard Claims Process is Open", "Activision Blizzard"),
    (28, "Court Approves $6.2 Million Distribution in EEOC v. Sears Disability Settlement", "Sears"),
    (29, "Job Seekers Not Hired by Radiant Services in Gardena May Have Suffered Discrimination, EEOC Says",
     "Radiant Services"),
    (30, "EEOC'S Lawsuit Against Costco to Proceed", "Costco"),
    (30, "EEOC WINS DISABILITY BIAS SUIT AGAINST FEDEX", "FEDEX"),
    (30, "EEOC Files Subpoena Enforcement Action Against NIKE", "NIKE"),
    (30, "EEOC SETTLES BIAS SUIT FOR $2.6 MILLION AGAINST TWA", "TWA"),     # "EEOC" before "Settles" is skipped
    (31, "EEOC Settles Sexual Harassment Suit With Dollar General for $50,000", "Dollar General"),
    (31, "EEOC SETTLES RACE DISCRIMINATION SUIT WITH THE MIRAGE FOR $1.14 MILLION", "MIRAGE"),
    (32, "Furniture Retailer Rooms to Go Adopts Revised Criminal Background Check Procedures In Cooperation With "
         "The EEOC", "Rooms to Go"),
    (33, "Federal Court Enters Judgment in Favor Of EEOC In Suit Charging Equal Pay Act Violation By Pizza Restaurant",
     "Pizza Restaurant"),
    (34, "EEOC Lawsuit Challenges Sexual Harassment at Davis Typewriter Company", "Davis Typewriter Company"),
    (34, "EEOC Lawsuit Challenges Sexual Harassment and Retaliation at North Dakota Applebee's",
     "North Dakota Applebee's"),
    (35, "Barenbrug USA Reaches Agreement with EEOC", "Barenbrug USA"),
    (35, "Sandia Transportation Reaches $97,500 Settlement with EEOC in Harassment Case", "Sandia Transportation"),
    (35, "Meadowbrook Meat Co. Enters into Consent Decree to Eliminate Racist Graffiti Alleged by EEOC",
     "Meadowbrook Meat Co."),
    (36, "EEOC OBTAINS $127,500 SETTLEMENT FROM ATLANTIC CHEVROLET / CADILLAC FOR RACE HARASSMENT",
     "ATLANTIC CHEVROLET / CADILLAC"),
    (37, "COURT APPROVES $1.2 MILLION SETTLEMENT BETWEEN EEOC AND MCKESSON FOR RACE DISCRIMINATION", "MCKESSON"),
    (38, "Jury Finds Parker Drilling Liable in EEOC Disability Discrimination Suit", "Parker Drilling"),
    (38, "Jury Says AA Foundries Must Pay $200,000 for Creating Racially Hostile Work Environment", "AA Foundries"),
    (39, "Abercrombie & Fitch Liable for Religious Discrimination in EEOC Suit, Court Says", "Abercrombie & Fitch"),
    (39, "Major Washington Apple Grower Hit With Preliminary Injunction", "Major Washington Apple Grower"),
    (40, "EEOC SETTLES MAJOR AGE BIAS LAWSUIT FOR $7.1 MILLION WITH THOMSON CONSUMER ELECTRONICS AND LOCAL UNIONS",
     "THOMSON CONSUMER ELECTRONICS AND LOCAL UNIONS"),
    (41, "Bank of America's Failure to Accommodate Blind Employee Draws EEOC Disability Lawsuit", "Bank of America"),
    (41, "ALLSTATE'S REHIRE POLICY ADVERSELY AFFECTED OLDER AGENTS; EEOC RECEIVES FAVORABLE RULING", "ALLSTATE"),
    (42, "EEOC Wins Jury Verdict of $458,000 for Two Older Workers Fired by AZ Metro", "AZ Metro"),
    (43, "The GAP Unlawfully Fired Employee With Disability, EEOC Charges", "The GAP"),
    (43, "HEALTH DELIVERY REFUSED TO RETURN DISABLED EMPLOYEE TO WORK, EEOC CHARGES", "HEALTH DELIVERY"),
    (43, "Howard University Failed to Hire Applicant Due to His Disability, EEOC Says", "Howard University"),
    (44, "Best Buy and EEOC Reach Agreement to Resolve Discrimination Charge", "Best Buy"),
    (44, "American Samoa Government and EEOC Settle Age Discrimination Suit", "American Samoa Government"),
]


# The same patterns again, for the wordings the real headlines above do not
# happen to use: every verb and every ending each pattern accepts. Made-up
# headlines; the employer is always "Zenith Works". (index, headline)
EMPLOYER_WORDINGS = [
    *[(4, f"Court Agrees With EEOC That Zenith Works {rest}")
      for rest in ("Violated Federal Law", "Created Hostile Workplace", "Must Rehire Driver")],
    *[(5, f"Court Denies Zenith Works {word} to Dismiss EEOC Suit") for word in ("Bid", "Request")],
    (13, "In Agreement with the EEOC, Zenith Works to Pay $50,000"),
    (13, "In Settlement with EEOC, Zenith Works will Pay $50,000"),
    *[(16, f"Zenith Works to {verb} Fired Workers to Settle EEOC Suit")
      for verb in ("Establish Fund for", "Change Policy for", "Adopt Policy for", "Offer Jobs to", "Rehire", "Reinstate")],
    (19, "Judge Orders Zenith Works to Pay $50,000"),
    (19, "Federal Court Orders Zenith Works to Pay $50,000"),
    (19, "Appeals Court Orders Zenith Works to Pay $50,000"),
    *[(21, f"EEOC and Zenith Works {rest}")
      for rest in ("Agree to Settle Suit", "Reach Settlement", "Enter Consent Decree", "Conciliate Charge",
                   "Announce Settlement", "Sign Consent Decree")],
    (21, "U.S. EEOC and Zenith Works Settle Suit"),
    (22, "Zenith Works Must Pay $50,000 in EEOC Suit"),
    (22, "Zenith Works Charged With Age Bias"),
    (22, "Zenith Works Pays $50,000 in EEOC Suit"),
    (22, "Zenith Works Ordered to Pay $50,000 in EEOC Suit"),
    (22, "Zenith Works Required to Pay $50,000 in EEOC Suit"),
    (22, "Zenith Works Agrees to Settle EEOC Suit"),
    (22, "Zenith Works, Voluntarily Settles EEOC Suit"),
    (23, "Court Finds Zenith Works Guilty of Retaliation in EEOC Suit"),
    (23, "Judge Holds Zenith Works Liable in EEOC Suit"),
    (24, "Zenith Works Found in Contempt in EEOC Suit"),
    (25, "Court Enters Decree Requiring Zenith Works to Train Managers in EEOC Suit"),
    (25, "Court Enters Decree Barring Zenith Works from Firing Complainers in EEOC Suit"),
    (25, "Court Enters Decree Prohibiting Zenith Works from Firing Complainers in EEOC Suit"),
    (26, "EEOC Obtains $50,000 from Zenith Works, Ending Suit"),
    (26, "EEOC Obtains $50,000 from Zenith Works"),
    (28, "Jury Awards $50,000 in EEOC v. Zenith Works, Ending Suit"),
    (28, "Jury Awards $50,000 in EEOC vs. Zenith Works"),
    (28, "Jury Awards $50,000 in EEOC v. Zenith Works Trial"),
    (29, "Workers Who Applied to Zenith Works May Have Claims in EEOC Suit"),
    (30, "EEOC Files Suit Against Zenith Works, Alleging Retaliation"),
    (30, "EEOC Files Suit Against the Zenith Works Over Retaliation"),
    *[(31, f"EEOC Settles {word} With Zenith Works") for word in ("Lawsuit", "Case", "Charge", "Charges")],
    *[(31, f"EEOC Announces {word} With Zenith Works, Ending Suit") for word in ("Settlement", "Agreement", "Decree")],
    (32, "Zenith Works Revises Hiring Policy in Cooperation With EEOC"),
    (32, "Zenith Works Changes Hiring Policy in Cooperation With EEOC"),
    (33, "EEOC Wins Verdict on Violation by Zenith Works in Pay Suit"),
    (33, "EEOC Wins Verdict on Violations by Zenith Works, Jury Says"),
    (34, "EEOC Suit Challenges Harassment at Zenith Works"),
    (35, "Zenith Works Signs Consent Decree With EEOC"),
    (35, "Zenith Works Reaches Resolution With EEOC"),
    (35, "Zenith Works Reaches Accord With EEOC"),
    (36, "EEOC Obtains $50,000 Settlement From Zenith Works, Ending Suit"),
    (37, "Court Approves Settlement Between EEOC and Zenith Works, Ending Suit"),
    (37, "Court Approves Settlement Between the EEOC and Zenith Works"),
    (38, "Jury Rules Zenith Works Liable in EEOC Suit"),
    (38, "Jury Finds Zenith Works Guilty of Retaliation in EEOC Suit"),
    (38, "Jury Finds Zenith Works Violated Law in EEOC Suit"),
    (38, "Federal Jury Finds Zenith Works Discriminated in EEOC Suit"),
    (40, "EEOC Settles Suit for $50,000 With Zenith Works for Age Bias"),
    (40, "EEOC Settles Suit for $50,000 With Zenith Works, Ending Case"),
    *[(41, f"Zenith Works' {word} of Women Draws EEOC Suit") for word in ("Refusal", "Firing", "Treatment")],
    *[(42, f"EEOC Wins Verdict for Worker {verb} by Zenith Works")
      for verb in ("Terminated", "Laid Off", "Rejected", "Underpaid")],
    (42, "EEOC Wins Verdict for Worker Fired by Zenith Works for Complaining"),
    (42, "EEOC Wins Verdict for Worker Fired by Zenith Works, Jury Says"),
    *[(43, f"Zenith Works {verb} Its Drivers, EEOC Charges")
      for verb in ("Harassed", "Denied", "Paid", "Subjected", "Forced", "Terminated", "Rejected", "Demoted",
                   "Punished", "Allowed", "Permitted", "Tolerated", "Ignored", "Unlawfully Fired",
                   "Illegally Fired")],
    (43, "Zenith Works Discriminated in Hiring, EEOC Charges"),
    (43, "Zenith Works Retaliated After Complaint, EEOC Charges"),
    (43, "Zenith Works Violated Federal Law, EEOC Charges"),
    *[(43, f"Zenith Works Fired Its Drivers, EEOC {word}") for word in ("Charged", "Says", "Said", "Alleges", "Claims")],
    *[(44, f"Zenith Works and EEOC {rest}")
      for rest in ("Agree to Settle Suit", "Resolve Suit", "Enter Consent Decree", "Conciliate Charge",
                   "Announce Settlement", "Sign Consent Decree")],
    (44, "Zenith Works and the U.S. EEOC Settle Suit"),
    # the words each pattern lets end the name
    *[(0, f"EEOC Sues Zenith Works {rest}")
      for rest in ("Over Firing", "on Behalf of Drivers", "in Federal Court", "Under Equal Pay Act",
                   "After Firing of Driver", "Alleging Retaliation", "to Stop Retaliation")],
    (16, "Zenith Works Agreed to Provide Back Pay to Settle EEOC Suit"),
    (16, "Zenith Works Required to Provide Back Pay to Settle EEOC Suit"),
    (22, "Zenith Works Pays Back Wages in EEOC Suit"),
    (23, "Appeals Court Finds Zenith Works Liable in EEOC Suit"),
    *[(26, f"EEOC Obtains $50,000 from Zenith Works {rest}") for rest in ("for Drivers", "in Suit", "to End Suit", "Over Firings")],
    *[(28, f"Jury Awards $50,000 in EEOC v. Zenith Works {rest}")
      for rest in ("Settlement Dispute", "Lawsuit", "Case", "Disability Suit", "Age Suit", "Sex Suit", "Race Suit",
                   "Harassment Suit", "Discrimination Suit", "to End Dispute", "in Ohio", "for Drivers")],
    *[(30, f"EEOC Files Suit Against Zenith Works {rest}")
      for rest in ("for Retaliation", "Over Firings", "in Ohio", "to Stop Retaliation", "Following Firings",
                   "After Firings", "on Behalf of Drivers")],
    *[(30, f"Verdict Against Zenith Works {rest}")
      for rest in ("Reinforces Law", "Affirmed", "Ends Long Fight", "Moves Ahead", "Tops $1 Million")],
    (30, "EEOC Suit Against Zenith Works Settles for $50,000"),
    (30, "Court Enters Decree in EEOC Suit Against Zenith Works Requiring Training"),
    (30, "EEOC Wins Ruling Against Zenith Works That Limits Defense"),
    (30, "Court Rules EEOC Suit Against Zenith Works Can Proceed"),
    *[(31, f"EEOC Settles Suit With Zenith Works {rest}")
      for rest in ("for $50,000", "Over Firings", "in Ohio", "to End Case")],
    (31, "EEOC Settlement With Zenith Works Will End Suit"),
    *[(33, f"EEOC Wins Verdict on Violation by Zenith Works {rest}")
      for rest in ("for Third Time", "to Drivers' Rights", "Against Employees")],
    (36, "EEOC Obtains $50,000 Settlement From Zenith Works"),
    *[(36, f"EEOC Obtains $50,000 Settlement From Zenith Works {rest}") for rest in ("for Drivers", "in Suit", "Over Firings")],
    *[(37, f"Court Approves Settlement Between EEOC and Zenith Works {rest}")
      for rest in ("for $50,000", "in Suit", "Over Firings", "to End Suit")],
    *[(40, f"EEOC Settles Suit for $50,000 With Zenith Works {rest}") for rest in ("in Ohio", "Over Firings", "to End Case")],
    (40, "EEOC Settles Suit for $1.5 Million With Zenith Works"),
    *[(42, f"EEOC Wins Verdict for Worker Fired by Zenith Works {rest}")
      for rest in ("in Ohio", "Because of Age", "After Complaint", "Over Complaint", "to Cut Costs")],
]


# Headlines with no employer in them: the name must come out blank, not the
# nearest capitalised words. The comment says what would be wrong to store.
NO_EMPLOYER_HEADLINES = [
    "EEOC Sues to Redress Sexual Harassment of Teens",                  # "to Redress Sexual Harassment"
    "Muslim Pilot Fired Due to Religion and Appearance, EEOC Charges",  # "Muslim Pilot"
    "EEOC Settles Suit for Mineworkers",                                # "EEOC", "Mineworkers"
    "Federal Court Rules for EEOC in Age Bias Case",                    # "Federal Court"
    "Jury Awards $500,000 in EEOC Sexual Harassment Suit",              # "Jury"
    "Judge Approves $1 Million Consent Decree in EEOC Race Bias Case",  # "Judge"
    "EEOC Wins Verdict for Fired Employees",                            # "Fired Employees"
    "EEOC Obtains $1 Million for Harassment Victims",
    # a passive about the victim is not "<employer> Fired ..."
    *[f"Zenith Driver Fired {rest}, EEOC Charges"
      for rest in ("Due to Age", "Because of Age", "For Complaining", "After Complaint", "By Manager")],
]


class HeadlineCheck(SimpleTestCase):
    """Shared by the two employer-pattern test classes below. Has no tests of its own."""

    def check_headline(self, index, title, name):
        """The headline gives this name, and through the pattern the row says."""
        result = classify(title, "")
        self.assertEqual(result["employer_raw"], name)
        self.assertEqual(result["employer_key"], employer_key(name))
        # The row must be exercising the pattern it claims to, or the table
        # would pass while a pattern went untested.
        self.assertEqual(winning_pattern(" ".join(unescape(title).split())), index, "a different pattern matched first")


@one_test_per_case(EMPLOYER_HEADLINES)
class EmployerHeadlineTests(HeadlineCheck):
    """Each headline shape in EMPLOYER_PATTERNS finds the employer in a real headline."""

    def check(self, index, title, name):
        """Check one row of the table."""
        self.check_headline(index, title, name)


@one_test_per_case(EMPLOYER_WORDINGS)
class EmployerWordingTests(HeadlineCheck):
    """Each verb and ending a pattern accepts, on a made-up headline."""

    def check(self, index, title):
        """Check one row of the table."""
        self.check_headline(index, title, "Zenith Works")


class EmployerPatternCoverageTests(SimpleTestCase):
    """The table above has to keep up with EMPLOYER_PATTERNS."""

    def test_every_pattern_has_a_headline(self):
        """A pattern added to EMPLOYER_PATTERNS without a headline here fails this test."""
        tested = {index for index, _title, _name in EMPLOYER_HEADLINES}
        missing = sorted(set(range(len(EMPLOYER_REGEXES))) - tested)
        self.assertEqual(missing, [], "add a headline to EMPLOYER_HEADLINES for these pattern numbers")

    def test_no_headline_points_past_the_end(self):
        """A pattern removed from EMPLOYER_PATTERNS leaves no row pointing at nothing."""
        self.assertLess(max(index for index, _title, _name in EMPLOYER_HEADLINES), len(EMPLOYER_REGEXES))


@one_test_per_case([(headline,) for headline in NO_EMPLOYER_HEADLINES])
class NoEmployerHeadlineTests(SimpleTestCase):
    """A headline that names nobody gives a blank name, never the nearest words."""

    def check(self, title):
        """Check one headline."""
        self.assertEqual(classify(title, "")["employer_raw"], "")


# How the headline and the teaser are combined into one name. Real releases,
# with the teaser shortened; three have a teaser reworded to show one thing.
# (what the case shows, headline, teaser, employer name)
NAME_CASES = [
    ("headline name wins over the teaser's legal name",
     "Thomas Dodge Subaru Settles EEOC Sex Harassment Suit",
     "Long Island-based car dealer Thomas Dodge Subaru, now doing business as Thomas Subaru, will pay $132,250 to "
     "settle a sex harassment lawsuit brought by the U.S. Equal Employment Opportunity Commission (EEOC)",
     "Thomas Dodge Subaru"),
    ("no name in the headline: the teaser's opening words are used",
     "EEOC Alleges Wood Group Refused to Hire Worker Because of His Disability",
     "Wood Group PSN, Inc., a global company which provides operations and maintenance to the oil, petrochemical "
     "and gas industries, denied employment to an offshore worker because of his disability",
     "Wood Group PSN"),
    ("teaser name after a dateline",
     "Federal Court Orders Company to Rehire Driver",
     "LOUISVILLE, Ky. — Jaco Enterprises, L.L.C., a transportation company, must rehire a driver, a federal "
     "court ruled in a lawsuit brought by the EEOC",
     "Jaco Enterprises"),
    ("teaser name after a '-based' location",
     "EEOC Sues Orion Energy for Disability Discrimination",
     "Manitowoc, Wis.-based Orion Energy Systems, Inc. violated federal law by firing an employee because of his "
     "disability, a mobility impairment",
     "Orion Energy"),
    ("headline name is the teaser's name plus a describing word: the teaser's is used",
     "El Vallarta Restaurant Sued for Sexual Harassment",
     "El Vallarta, a Nebraska restaurant, violated Title VII when it allowed a supervisor and other workers to "
     "sexually harass a teenage female employee",
     "El Vallarta"),
    ("headline name is a place plus the teaser's name",
     "Arizona Walmart to Pay $100,000 in EEOC Disability Lawsuit",
     "PHOENIX – Walmart, Inc., the largest grocery store chain in the United States, will pay $100,000 and "
     "furnish other relief to settle a disability discrimination lawsuit",
     "Walmart"),
    ("two employers in the headline: both are kept, not just the one the teaser leads with",
     "Cardinal Health and AppleOne Settle EEOC Race Harassment / Retaliation Lawsuit",
     "LOS ANGELES – Global health care services and products company Cardinal Health will pay $1.45 million to "
     "resolve a racial harassment and retaliation discrimination lawsuit",
     "Cardinal Health and AppleOne"),
    ("two employers joined by a slash are both kept",
     "Olive Garden/GMRI Inc. To Pay $30,000 To Settle EEOC Disability Discrimination Suit",
     "PITTSBURGH – GMRI, Inc., doing business as Olive Garden, will pay $30,000 and agreed to significant "
     "non-monetary remedies under a consent decree",
     "Olive Garden/GMRI Inc."),
    ("two employers joined by '&' are both kept",
     "Tarr & Zenith Settle EEOC Pregnancy Discrimination Lawsuit",
     "Tarr, Inc. and Zenith, LLC, a San Diego-based company that sells dietary supplements, will pay $50,000",
     "Tarr & Zenith"),
    ("'the' inside a name does not cut the teaser name short",
     "Bank Of The West To Pay $48,000 To Settle EEOC Sex Bias Hiring Lawsuit",
     "Bank of the West, one of the nation's largest banks, will pay $48,000 and furnish other relief to settle a "
     "sex discrimination lawsuit",
     "Bank Of The West"),
    ("'&' then 'the' inside a name",
     "Joe & The Juice Resolves Sex Discrimination Charge",
     "LOS ANGELES – Joe & the Juice, a nationwide restaurant specializing in juice, coffee and sandwiches, has "
     "settled a federal charge of discrimination",
     "Joe & The Juice"),
    ("a trailing clause after the name is not part of it",
     "EEOC Sues Rizza Cadillac of Tinley Park, Citing Harassment of Arab and Muslim Sales Staff",
     "Rizza Cadillac, Inc. of Tinley Park, Ill., a suburb south of Chicago, violated federal law by encouraging a "
     "work environment which was hostile and offensive to Muslim and Arab sales staff",
     "Rizza Cadillac"),
    ("name ending in a generic word, repeated with capitals in the teaser: a real name",
     "EEOC Sues Turner Machine Company for Retaliation",
     "Turner Machine Company retaliated against an employee by firing him because he filed a discrimination charge",
     "Turner Machine Company"),
    ("name ending in a generic word, teaser says nothing: kept",
     "EEOC SUES DOLLINS CONSTRUCTION COMPANY FOR RACE DISCRIMINATION AND RETALIATION AGAINST BLACK WORKERS",
     "Suit Cites Racist Comments, Noose and Retaliation for Complaints",
     "DOLLINS CONSTRUCTION COMPANY"),
    ("headline has a description, teaser has the name",
     "Modesto Retailer Settles Disability Discrimination Suit",
     "Modesto retailer Buy Rite Thrift Store has agreed to pay $50,000 to settle a disability discrimination "
     "lawsuit filed by the U.S. Equal Employment Opportunity Commission (EEOC)",
     "Buy Rite Thrift Store"),
    ("headline has a description, teaser opens with the legal name",
     "EEOC Sues Louisville Hospital for Race Discrimination",
     "Jewish Hospital and St. Mary's Healthcare, Inc., a Louisville hospital, unlawfully fired an employee because "
     "he is African-American",
     "Jewish Hospital and St. Mary's Healthcare"),
    ("description in the headline, name after 'filed suit against'",
     "Wendy's Franchisee Sued by EEOC for Disability Discrimination",
     "The U.S. Equal Employment Opportunity Commission announced today that it has filed suit against CTW L.L.C., "
     "a Wendy's franchisee, for denying employment to a hearing-impaired applicant because of his disability",
     "CTW L.L.C."),
    ("description in the headline, name after 'owned and operated by'",
     "Carmel Restaurants to Pay $175,000 to Settle Sexual Harassment Lawsuit",
     "Carmel restaurants owned and operated by JCFB, Inc. agreed to pay $175,000 to settle a federal sexual "
     "harassment lawsuit filed on behalf of male and female kitchen staff",
     "JCFB"),
    ("description in the headline, name after 'EEOC sued'",
     "Security Firm To Pay $115,000 To Settle EEOC Retaliation Suit",
     "Security giant Guardsmark has agreed to pay $115,000 and to provide other relief to settle a retaliation "
     "discrimination case brought by the U.S. Equal Employment Opportunity Commission (EEOC), the agency announced "
     "today. EEOC sued Guardsmark for retaliating against a security guard who opposed a sexually hostile work "
     "environment.",
     "Guardsmark"),
    ("description in both, name opens a later sentence with a legal suffix",
     "Restaurant Admits to Pregnancy Discrimination and Pays $30,000 to Resolve EEOC Lawsuit",
     "NEW ORLEANS – A Louisiana restaurant admitted that it violated federal law when it fired and then later "
     "refused to rehire a worker because she was pregnant, the EEOC announced today. Bourne’s House, LLC, doing "
     "business as Empire Buffet, will pay $30,000",
     "Bourne’s House"),
    ("no name anywhere: the headline's description is stored",
     "St. Louis Restaurant Settles EEOC Sexual Harassment Lawsuit",
     "A St. Louis restaurant will pay $23,000 and furnish other relief to settle a sexual harassment lawsuit filed "
     "by the U.S. Equal Employment Opportunity Commission (EEOC), the agency announced today.",
     "St. Louis Restaurant"),
    ("no name anywhere, public employer",
     "Kansas School District to Pay $11,250 to Settle Equal Pay Act Lawsuit",
     "A Kansas school district has agreed to pay $11,250 and provide other relief to settle an employment "
     "discrimination lawsuit filed by the U.S. Equal Employment Opportunity Commission (EEOC)",
     "Kansas School District"),
    ("a count is a description even when the teaser does not echo it",
     "Two Washington Resorts Sued by EEOC for Sexual Harassment",
     "Two resorts located along the Columbia River violated federal law when their owner repeatedly subjected "
     "female employees to sexual harassment",
     "Two Washington Resorts"),
    ("nothing in the headline: the teaser's 'A ... restaurant' description is stored",
     "EEOC Conciliates Discriminatory Wage Theft Case",
     "A Steamboat Springs, Colo., restaurant has agreed to pay $50,000 to resolve race and national origin "
     "discrimination charges, including charges of wage theft",
     "Steamboat Springs, Colo., restaurant"),
    ("an 'A ...' teaser opening about a judge is not an employer",
     "EEOC Wins Disability Bias Ruling",
     "A federal judge in Chicago has ruled for the U.S. Equal Employment Opportunity Commission in a disability "
     "lawsuit, the agency announced today.",
     ""),
    ("teaser opens with the EEOC itself: no name",
     "EEOC Wins Disability Bias Ruling",
     "The U.S. Equal Employment Opportunity Commission (EEOC) today announced a favorable ruling in its lawsuit.",
     ""),
    ("announcement: a company in the headline is not stored as an employer",
     "EEOC and Family Dollar Stores Sign Mediation Pact",
     "The U.S. Equal Employment Opportunity Commission (EEOC) and Family Dollar Stores, Inc. (NYSE:FDO) today "
     "announced the signing of a National Universal Agreement to Mediate (NUAM)",
     ""),
    ("announcement: the teaser's opening words are not stored either",
     "EEOC's Dallas District Names New Deputy Director",
     "Belinda McCallister, a longtime manager, has been selected as the new deputy director of the Dallas "
     "District Office, the EEOC announced.",
     ""),
    ("the victim after 'Against' is not the employer",
     "Triborough Bridge & Tunnel Authority Discriminated Against Pregnant Female Officers, EEOC Charges",
     "", "Triborough Bridge & Tunnel Authority"),
    ("a describing lead-in is dropped from the headline name",
     "Pancake Chain IHOP to Pay $700,000 to Settle Sexual Harassment and Retaliation Lawsuit",
     "Several franchisees of the popular IHOP restaurant chain in Nevada and New York will pay $700,000",
     "IHOP"),
    ("a lead-in that is part of the real name stays",
     "EEOC Sues Coca-Cola Bottling Company United for Disability Discrimination",
     "NEW ORLEANS – Coca-Cola Bottling Company United, Inc. (CCBCU), the third-largest bottler and distributor "
     "of Coca-Cola products in the United States, violated federal law",
     "Coca-Cola Bottling Company United"),
    ("the EEOC's own typo in the headline",
     "EECO Sues 40 Steak & Seafood for Pregnancy Discrimination",
     "", "40 Steak & Seafood"),
    ("HTML entity and doubled spaces in the headline",
     "EEOC Sues   Sidley &amp; Austin   for Age Discrimination",
     "", "Sidley & Austin"),
    ("Windows-1252 apostrophe from the old archive pages",
     "DILLARD\x92S TO PAY $110,000 FOR SAME-SEX HARASSMENT",
     "", "DILLARD'S"),
    ("'In Agreement with EEOC, X to ...': the action comes from the teaser, the name from the headline",
     "In Agreement with EEOC, Groupon to Establish Educational Fund for Black Students Pursuing STEM Careers",
     "CHICAGO - The U.S. Equal Employment Opportunity Commission (EEOC) announced today that following an "
     "investigation, the EEOC and Groupon, Inc. (Groupon) have entered into a voluntary agreement in which "
     "Groupon has agreed to contribute $350,000",
     "Groupon"),
]


# Where the teaser's first sentence stops being the name. Made-up teasers under
# a headline that names nobody; the employer is always "Zenith Works".
TEASER_OPENINGS = [
    # a legal suffix ends the name
    *[f"Zenith Works{suffix} violated federal law, the EEOC charged."
      for suffix in (", Inc.", " Inc.", ", Inc", ", LLC,", ", L.L.C.,", " LLC", ", Corp.", " Corp", ", Co.,", ", Ltd.",
                     ", L.P.,", ", LP,")],
    # a describing clause ends the name
    *[f"Zenith Works, {clause} violated federal law, the EEOC charged."
      for clause in ("a tool maker,", "an Ohio tool maker,", "the largest tool maker in Ohio,",
                     "which makes tools,", "one of Ohio's largest tool makers,", "operator of three plants,",
                     "operators of three plants,", "owner of three plants,", "owners of three plants,",
                     "franchisee of a tool chain,", "franchisor of a tool chain,",
                     "doing business as Zenith Tools,", "d/b/a Zenith Tools,")],
    # a verb ends the name
    *[f"Zenith Works {verb} the law, the EEOC charged."
      for verb in ("violated", "unlawfully broke", "discriminated against workers and broke", "fired a clerk and broke",
                   "refused to follow")],
    "Zenith Works agreed to pay $50,000 in a lawsuit.",
    "Zenith Works will pay $50,000 in a lawsuit.",
    "Zenith Works has agreed to pay $50,000 in a lawsuit.",
    "Zenith Works reached a settlement in a lawsuit.",
    # a dateline comes first
    *[f"{dateline}Zenith Works, Inc. violated federal law, the EEOC charged."
      for dateline in ("CLEVELAND — ", "CLEVELAND – ", "CLEVELAND -- ", "CLEVELAND - ", "ST. LOUIS, Mo. — ",
                       "TUCSON and PHOENIX - ")],
    # a place or a description comes first
    "Cleveland-based Zenith Works, Inc. violated federal law, the EEOC charged.",
    "Cleveland-area Zenith Works, Inc. violated federal law, the EEOC charged.",
    "Cleveland, Ohio-headquartered Zenith Works, Inc. violated federal law, the EEOC charged.",
    "Tool giant Zenith Works violated federal law, the EEOC charged.",
    # the opening only describes the employer; the name comes later
    *[f"Ohio restaurants {verb} by Zenith Works agreed to pay $50,000."
      for verb in ("owned", "operated", "run", "managed", "owned and operated", "owned and managed")],
    *[f"An Ohio restaurant will pay $50,000. The {who} {verb} Zenith Works {rest}"
      for who in ("EEOC", "agency", "Commission")
      for verb, rest in (("charged", "with firing a clerk."), ("had charged", "with firing a clerk."),
                         ("has sued", "for firing a clerk."), ("charged that", "violated the law."),
                         ("charged", "discriminated against a clerk."), ("charged", "fired a clerk."),
                         ("charged", "failed to pay a clerk."))],
    "An Ohio restaurant will pay $50,000. The EEOC had charged Wood River, Neb.-based Zenith Works with firing a clerk.",
    "An Ohio restaurant will pay $50,000 in a case the EEOC filed against Zenith Works, Inc., of Akron.",
    "An Ohio restaurant will pay $50,000 in a suit filed last year against the Zenith Works.",
    "An Ohio restaurant admitted it broke the law. Zenith Works, LLC, doing business as Zed's, will pay $50,000.",
    "An Ohio restaurant admitted it broke the law. Zenith Works Inc. will pay $50,000.",
]


# Teaser openings that must give no name at all.
TEASER_OPENINGS_WITHOUT_A_NAME = [
    "The U.S. Equal Employment Opportunity Commission (EEOC) today announced a ruling in its lawsuit.",
    "Today, the EEOC announced a ruling in its lawsuit.",
    "On March 3, a federal judge ruled in the lawsuit.",
    "A federal judge has ruled in the lawsuit, the agency said.",
    "An appeals court has ruled in the lawsuit, the agency said.",
    "Three workers will share $50,000, the agency said. Their lawyer praised the lawsuit.",
    "Workers who complained will share $50,000 in a lawsuit.",
    "In a ruling issued today, a court sided with the agency. Later, Inc. magazine covered the lawsuit.",
    "",
]


@one_test_per_case([(teaser,) for teaser in TEASER_OPENINGS])
class TeaserOpeningTests(SimpleTestCase):
    """Every way the teaser can carry the name when the headline has none."""

    def check(self, teaser):
        """Check one teaser."""
        self.assertEqual(classify("EEOC Announces End of Lawsuit", teaser)["employer_raw"], "Zenith Works")


@one_test_per_case([(teaser,) for teaser in TEASER_OPENINGS_WITHOUT_A_NAME])
class TeaserWithoutANameTests(SimpleTestCase):
    """Teasers that open with the agency, a date or a court give no employer."""

    def check(self, teaser):
        """Check one teaser."""
        self.assertEqual(classify("EEOC Announces End of Lawsuit", teaser)["employer_raw"], "")


@one_test_per_case(NAME_CASES)
class EmployerNameTests(SimpleTestCase):
    """The headline and the teaser are combined into the right employer name."""

    def check(self, _why, title, teaser, name):
        """Check one row of the table."""
        result = classify(title, teaser)
        self.assertEqual(result["employer_raw"], name)
        self.assertEqual(result["employer_key"], employer_key(name)[:300])


# (the teaser's opening words, the name they give or "")
TEASER_NAME_CASES = [
    ("Tenet Healthcare", "Tenet Healthcare"),
    ("Dallas-based Tenet Healthcare", "Tenet Healthcare"),
    ("Las Vegas, Nev.-headquartered Golden Entertainment", "Golden Entertainment"),
    ("Chicago-area Rizza Cadillac", "Rizza Cadillac"),
    ("Multinational retailer Walmart", "Walmart"),
    ("Security giant Guardsmark", "Guardsmark"),
    ("Atlantic Property Corp and its affiliate", "Atlantic Property Corp"),
    ("Bank of America", "Bank of America"),
    ("Bank of America and", "Bank of America"),
    ("Mariscos del Puerto", "Mariscos del Puerto"),
    ("Volunteer fire companies in the Town", ""),
    ("The U.S. Equal Employment Opportunity Commission", ""),
    ("The EEOC", ""),
    ("Today", ""),
    ("On March 3", ""),
    ("A federal Judge", ""),
    ("The Supreme Court", ""),
    ("Three Employees", ""),
    ("Several Texas Companies", ""),
    ("EEOC Chair Jenny Yang", ""),
    ("", ""),
]


# (headline name, teaser, True = description, False = real name, None = can't tell)
GENERIC_CASES = [
    ("HOUSTON RESTAURANT", "A Houston restaurant will pay $20,000.", True),
    ("Georgia Car Dealership", "A Georgia car dealership violated federal law.", True),
    ("Two Employers", "The companies violated federal law.", True),
    ("Several Staffing Agencies", "", True),
    ("Turner Machine Company", "Turner Machine Company retaliated against an employee.", False),
    ("JPMORGAN CHASE BANK", "JPMorgan Chase Bank will pay $1 million.", False),
    ("Georgia Power Company", "The utility violated federal law.", None),
    ("Georgia Power Company", "", None),
]


# (headline name, teaser, name after a describing lead-in is dropped)
LEAD_IN_CASES = [
    ("Pancake Chain IHOP", "", "IHOP"),
    ("Frozen Food Giant Schwan's", "", "Schwan's"),
    ("National Staffing Agency BaronHR", "", "BaronHR"),
    ("Financial Services Giant Northwestern Mutual", "", "Northwestern Mutual"),
    ("TRUCKING COMPANY YRC", "", "TRUCKING COMPANY YRC"),     # all capitals: left for the teaser to settle
    ("Furniture Retailer Rooms to Go", "", "Rooms to Go"),
    ("Apparel Retailer 'Finish Line'", "", "Finish Line"),
    ("IHOP", "", "IHOP"),
    ("Coca-Cola Bottling Company United", "Coca-Cola Bottling Company United, Inc. violated federal law",
     "Coca-Cola Bottling Company United"),                              # the teaser repeats it: a real name
    ("Acme Trucking Company Inc", "", "Acme Trucking Company Inc"),      # what follows is a suffix
    ("Acme Company of Texas", "", "Acme Company of Texas"),
    ("Administaff and Cable TV Provider Conn-X", "", "Administaff and Cable TV Provider Conn-X"),   # two employers
    ("Staffing Agency Restaurant Supplier", "", "Staffing Agency Restaurant Supplier"),   # still a description
    ("Media Giant", "", "Media Giant"),
]


@one_test_per_case(TEASER_NAME_CASES)
class CleanTeaserNameTests(SimpleTestCase):
    """clean_teaser_name turns the teaser's opening words into a name, or nothing."""

    def check(self, words, name):
        """Check one row of the table."""
        self.assertEqual(clean_teaser_name(words), name)


@one_test_per_case(GENERIC_CASES)
class LooksGenericTests(SimpleTestCase):
    """looks_generic tells a description from a real name ending in a generic word."""

    def check(self, name, teaser, verdict):
        """Check one row of the table."""
        self.assertIs(looks_generic(name, teaser), verdict)


@one_test_per_case(LEAD_IN_CASES)
class WithoutLeadInTests(SimpleTestCase):
    """without_lead_in drops 'Pancake Chain' from 'Pancake Chain IHOP', and only that."""

    def check(self, name, teaser, expected):
        """Check one row of the table."""
        self.assertEqual(without_lead_in(name, teaser), expected)


# Business nouns that make a headline "name" a description when the teaser has
# the real name: "Ohio Diner Sued ..." + "Bob's Eats, Inc., an Ohio diner, ...".
GENERIC_NOUNS = [
    "Company", "Companies", "Hospital", "Center", "Agency", "Firm", "Chain", "Provider", "Restaurant", "Diner",
    "Retailer", "Dealer", "Dealership", "Manufacturer", "Contractor", "Franchise", "Franchisee", "Franchisor",
    "Operator", "Owner", "Facility", "Employer", "Business", "Businesses", "Store", "Hotel", "Resort", "Farm",
    "Grower", "Plant", "Club", "Nightclub", "Bar", "School", "District", "Home", "Practice", "Clinic", "Venue",
    "Shop", "Market", "Supplier", "Distributor", "Wholesaler", "Recruiter", "Nonprofit", "Non-Profit",
    "Organization", "Subsidiary", "Affiliate", "Giant", "Maker", "Processor", "Cleaner", "Cleaners", "Lodge",
    "Hotels",
]


# Last words that are NOT generic: the headline name stays even with a teaser name.
NOT_GENERIC_NOUNS = ["Airlines", "Foods", "Motors", "University", "Systems", "Bank", "County", "Group"]


# Openings that make a headline name a description on their own.
GENERIC_STARTS = ["2", "15", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Several",
                  "Multiple", "Major", "National", "Nationwide", "Local", "Large", "Largest", "Former", "Owner",
                  "Owners", "Operator", "Operators"]


# Nouns that end a describing lead-in: "Regional <noun> Zenith Corp" -> "Zenith Corp".
LEAD_IN_NOUNS = ["Giant", "Company", "Provider", "Agency", "Retailer", "Lender", "Contractor", "Maker", "Chain",
                 "Firm", "Processor", "Manufacturer", "Distributor", "Franchisee", "Operator", "Grower", "Dealer",
                 "Dealership", "Subcontractor"]


# Words after such a noun that show it was the end of a real name, not a lead-in.
NOT_A_REST_WORDS = ["Inc", "Inc.", "LLC", "L.L.C.", "Corp", "Co", "Ltd", "LP", "Of Texas", "And Sons", "In Ohio",
                    "For Kids", "To Go", "At Large", "D/B/A Zenith", "Sued", "Settles", "Settle", "Pays", "Pay",
                    "Will", "Agrees", "Agree", "Admits", "That Cares", "Who Cares", "Which Cares"]


# Words a headline pattern can capture that are not an employer.
NOT_NAMES = [
    "EEOC", "U.S. EEOC", "Equal Employment Opportunity Commission", "Commission", "Justice Department",
    "Federal Agency", "Federal Agencies", "Court", "Federal Court", "Judge", "Federal Judge", "Jury", "Federal Jury",
    "Texas Judge", "On March 3", "On Jan. 5", "On Tuesday",
    "Today", "Yesterday", "Over", "Under", "In", "On", "At", "As", "Since", "During", "After", "Following", "This",
    "For", "The", "A", "An", "Whereas", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Several",
    "The San Francisco District of", "Relief for", "Workers in", "Agrees to", "Fired by", "Harassed at",
    "Acme and", "Owner of the", "Charged with", "Sued by",
    "Fired Employees", "Acme Employee", "Mineworkers", "Mineworker", "Job Applicants", "Applicant", "Victims",
    "Harassment Victim", "Women", "Individuals", "Farm Workers", "Farmworkers", "Job Seekers", "Muslim Pilot",
    "Egyptian Manager", "Teens", "PREGNANT EMPLOYEES",
    "Overturning Lower Court", "Rejecting Acme Appeal", "Citing Harassment", "By Acme", "Upon Review",
    "Agency Lawsuit", "$50,000", "Harassment", "Discrimination", "RETALIATION", "Bias", "Worker Fired",
    "Manager fired",
]


# Real employers that look a little like the list above and must be accepted.
REAL_NAMES = [
    "Sonic Drive-In", "On Sight", "The GAP", "In-N-Out Burger", "Under Armour", "After Hours Formalwear",
    "Two Men and a Truck", "Three Rivers Hospital", "Target", "A&P", "Women's Health Center",
    "Individuals With Disabilities Education Center", "Teens Unlimited", "Bias Tape Makers of America",
    "Employees Only Bar", "At Home Stores", "Today's Staffing", "Commissioned Sales Associates",
    "Pilot Travel Centers", "Manager Tools LLC", "Victims Advocacy Group", "Applicant Insight",
]


# Teaser openings that are the sentence's subject, not an employer. (TEASER_NOT_A_NAME)
TEASER_NOT_NAMES = [
    "The Supreme Court", "Supreme Beverage", "District Court", "The Commission", "Chairman Roe", "Chairwoman Roe",
    "Chair Roe", "General Counsel", "White House", "Phoenix District", "Legal Experts", "Acme Employees",
    "Acme Workers", "Acme Applicants", "Employees Union Local", "Applicants Group", "One Acme", "Two Acme", "Three Acme", "Four Acme", "Five Acme",
    "Six Acme", "Seven Acme", "Eight Acme", "Nine Acme", "Ten Acme", "Several Acme", "Some Acme", "Many Acme",
]


@one_test_per_case([(noun,) for noun in GENERIC_NOUNS])
class GenericNounTests(SimpleTestCase):
    """A headline 'name' ending in a business noun gives way to the teaser's real name."""

    def check(self, noun):
        """Check one noun."""
        result = classify(f"Ohio {noun} Sued by EEOC for Retaliation",
                          f"Zenith Works, Inc., an Ohio {noun.lower()}, violated federal law.")
        self.assertEqual(result["employer_raw"], "Zenith Works")
        # With no name in the teaser, the description is what gets stored.
        result = classify(f"Ohio {noun} Sued by EEOC for Retaliation",
                          f"An Ohio {noun.lower()} violated federal law, the EEOC charged.")
        self.assertEqual(result["employer_raw"], f"Ohio {noun}")


@one_test_per_case([(noun,) for noun in NOT_GENERIC_NOUNS])
class NotGenericNounTests(SimpleTestCase):
    """Any other last word is taken as a real name, whatever the teaser opens with."""

    def check(self, noun):
        """Check one noun."""
        result = classify(f"Ohio {noun} Sued by EEOC for Retaliation",
                          f"Zenith Works, Inc., an Ohio {noun.lower()}, violated federal law.")
        self.assertEqual(result["employer_raw"], f"Ohio {noun}")


@one_test_per_case([(word,) for word in GENERIC_STARTS])
class GenericStartTests(SimpleTestCase):
    """A count or a vague size at the front makes a description: 'Two Texas Staffing Agencies'."""

    def check(self, word):
        """Check one opening word."""
        self.assertIs(looks_generic(f"{word} Texas Staffing Agencies", ""), True)
        self.assertIsNone(looks_generic("Texas Staffing Agencies", ""))


@one_test_per_case([(noun,) for noun in LEAD_IN_NOUNS])
class LeadInNounTests(SimpleTestCase):
    """Each noun that can end a describing lead-in."""

    def check(self, noun):
        """Check one noun."""
        self.assertEqual(without_lead_in(f"Regional {noun} Zenith Works", ""), "Zenith Works")
        self.assertEqual(classify(f"Regional {noun} Zenith Works to Pay $50,000", "")["employer_raw"], "Zenith Works")


@one_test_per_case([(word,) for word in NOT_A_REST_WORDS])
class NotALeadInTests(SimpleTestCase):
    """'Acme Trucking Company Inc' is one name: the noun is not a lead-in when a suffix or joining word follows."""

    def check(self, word):
        """Check one following word."""
        name = f"Acme Trucking Company {word}"
        self.assertEqual(without_lead_in(name, ""), name)


@one_test_per_case([(words,) for words in NOT_NAMES])
class NotANameTests(SimpleTestCase):
    """Words a headline pattern can capture that must not be stored as an employer."""

    def check(self, words):
        """Check one capture."""
        self.assertRegex(words, NOT_A_NAME)


@one_test_per_case([(name,) for name in REAL_NAMES])
class RealNameTests(SimpleTestCase):
    """Real employers that NOT_A_NAME must let through, in a headline and in a teaser."""

    def check(self, name):
        """Check one name."""
        self.assertNotRegex(name, NOT_A_NAME)
        self.assertEqual(classify(f"{name} Sued by EEOC for Retaliation", "")["employer_raw"], name)
        self.assertEqual(classify(f"EEOC Sues {name} for Retaliation", "")["employer_raw"], name)


@one_test_per_case([(words,) for words in TEASER_NOT_NAMES])
class TeaserNotANameTests(SimpleTestCase):
    """Teaser openings that are not an employer, though a headline could use the same words."""

    def check(self, words):
        """Check one opening."""
        self.assertEqual(clean_teaser_name(words), "")
        self.assertEqual(classify("Changes Ordered After Lawsuit", f"{words}, a body of note, will pay $50,000.")
                         ["employer_raw"], "")
