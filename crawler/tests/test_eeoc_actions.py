"""
crawler/tests/test_eeoc_actions.py

Tests for the action type crawler.eeoc_classify gives a release: sued, settled,
verdict, investigation, announcement, translation or unclear, and which check
wins when more than one could apply.
No database and no network. Run this file alone with

    python manage.py test crawler.tests.test_eeoc_actions

or every EEOC test with

    python manage.py test crawler.tests

Every row of a table becomes its own test (see one_test_per_case in
eeoc_testing.py). A row that says "made up" or uses "Acme" / "Zenith Works"
is invented to pin down one wording. Everything else is a real EEOC headline.
"""
from django.test import SimpleTestCase

from crawler.eeoc_classify import classify, employer_key
from crawler.tests.eeoc_testing import one_test_per_case


LONG_OPENING = "The U.S. Equal Employment Opportunity Commission (EEOC) enforces federal laws. " * 6


# (what the case shows, headline, teaser, action type). "" means unclear.
ACTION_CASES = [
    # sued
    ("'EEOC Sues' opens the headline", "EEOC Sues Acme for Retaliation", "", "sued"),
    ("'EEOC Sues' wins even when the headline mentions paying or settling",
     "EEOC Sues Acme for Refusing to Pay Settlement", "", "sued"),
    ("'Sued by EEOC'", "Acme Sued by EEOC for Retaliation", "", "sued"),
    ("'Sues' later in the headline", "EEOC Again Sues Acme", "", "sued"),
    ("older 'SUED FOR'", "MOUNTAIRE FARMS SUED FOR RETALIATION", "", "sued"),
    ("a suit still in court", "EEOC'S Lawsuit Against Costco to Proceed", "", "sued"),
    ("'Files Suit'", "EEOC Files Suit Against Acme for Sex Bias", "", "sued"),
    ("'Case Against'", "EEOC Announces New Case Against Acme", "", "sued"),
    ("'EEOC Charges'", "EEOC Charges Acme With Age Discrimination", "", "sued"),
    ("'EEOC Alleges'", "EEOC Alleges Acme Refused to Hire Worker Because of His Disability", "", "sued"),
    ("'EEOC Challenges'", "EEOC Challenges Sexual Harassment at Acme", "", "sued"),
    ("'Charged With'", "Acme Charged With Race Discrimination", "", "sued"),
    ("', EEOC Says'", "Acme Failed to Hire Applicant Due to His Disability, EEOC Says", "", "sued"),
    ("'EEOC Claims'", "EEOC Claims Acme Fired Whistleblower", "", "sued"),
    ("'EEOC Accuses'", "EEOC Accuses Acme of Firing Whistleblower", "", "sued"),
    ("'Charged by'", "Acme Charged by EEOC Over Firing", "", "sued"),
    ("', EEOC Charged'", "Acme Fired Whistleblower, EEOC Charged", "", "sued"),
    # verdict
    ("jury verdict", "EEOC Wins Jury Verdict of $458,000 for Two Older Workers Fired by AZ Metro", "", "verdict"),
    ("a jury ordering payment is a verdict, not a settlement",
     "JURY ORDERS HARRIS FARMS TO PAY $994,000 IN SEXUAL HARASSMENT SUIT BY EEOC", "", "verdict"),
    ("judgment", "EEOC Obtains Judgment Ordering Ceviche House to Pay $130,691 for Sexual Harassment", "", "verdict"),
    ("'Court Rules'", "Court Rules Acme Must Rehire Worker", "", "verdict"),
    ("'Judge Orders'", "Judge Orders Acme to Reinstate Driver", "", "verdict"),
    ("'Court Affirms'", "Appeals Court Affirms Award in EEOC Suit Against Acme", "", "verdict"),
    ("injunction granted", "Federal Court Grants Preliminary Injunction Against Acme", "", "verdict"),
    ("'Court Issues Ruling'", "Court Issues Landmark Ruling in EEOC Suit Against Acme", "", "verdict"),
    ("'Favorable Ruling'", "ALLSTATE'S REHIRE POLICY ADVERSELY AFFECTED OLDER AGENTS; EEOC RECEIVES FAVORABLE RULING",
     "", "verdict"),
    ("'Liable'", "Abercrombie & Fitch Liable for Religious Discrimination in EEOC Suit, Court Says", "", "verdict"),
    ("'EEOC Wins'", "EEOC WINS DISABILITY BIAS SUIT AGAINST FEDEX", "", "verdict"),
    ("'EEOC Prevails'", "EEOC Prevails in Age Bias Suit Against Acme", "", "verdict"),
    ("'Victory'", "Victory for EEOC in Suit Against Acme", "", "verdict"),
    ("'Awarded $'", "Fired Acme Worker Awarded $300,000 in EEOC Suit", "", "verdict"),
    ("injunction entered", "Court Enters Permanent Injunction Against Acme", "", "verdict"),
    ("'Court Issues Decision'", "Court Issues Decision in EEOC Suit Against Acme", "", "verdict"),
    ("'EEOC Scores'", "EEOC Scores Win Against Acme", "", "verdict"),
    ("the word 'verdict' alone", "Verdict Against Acme Upheld", "", "verdict"),
    ("an injunction granted in a suit is a verdict, not 'sued'",
     "Court Grants Injunction in EEOC Suit Against Acme", "", "verdict"),
    ("an injunction entered in a suit is a verdict, not 'sued'",
     "Court Enters Permanent Injunction in EEOC Suit Against Acme", "", "verdict"),
    ("injunction, no court named", "Acme Hit With Injunction Over Firings", "", "verdict"),
    ("sanctions, no court named", "Acme Hit With Sanctions Over Destroyed Records", "", "verdict"),
    # verdict, by the wider court wording that is checked second
    ("court denies a motion", "Court Denies Key Menards Motion in EEOC Pregnancy Discrimination Case", "", "verdict"),
    ("Supreme Court denies review", "U.S. Supreme Court Denies United Airlines Petition", "", "verdict"),
    ("court refuses", "Federal Court Refuses To Toss Out EEOC Claim That Chrysler Retaliated Against Employees",
     "", "verdict"),
    ("'to Face Trial'", "L.A. WEIGHT LOSS TO FACE TRIAL FOR SEX BIAS AND RETALIATION", "", "verdict"),
    ("sanctions", "JUDGE SLAPS WAL-MART WITH MAJOR SANCTIONS FOR VIOLATING COURT ORDER IN EEOC DISABILITY BIAS CASE",
     "", "verdict"),
    ("'Must Turn Over'", "Henry's Turkey Service, Heirs Must Turn over Almost $600,000 Owed to Disabled Workers",
     "", "verdict"),
    ("'Ordered to'", "Restaurant Group Ordered to Implement Sexual Harassment Prevention", "", "verdict"),
    ("contempt", "Dairy Queen Franchisee Held in Contempt for Breaching Agreement with EEOC", "", "verdict"),
    ("'to Proceed to Trial'", "EEOC Claim Over Acme Firing to Proceed to Trial", "", "verdict"),
    ("sent to trial is a ruling even when the headline also says 'Suit'",
     "Scion Dental, a Unit of SkyGen USA, Ordered to Face Trial for Race Discrimination in EEOC Suit", "", "verdict"),
    ("'Suit ... to Proceed to Trial'", "EEOC Suit Against Acme to Proceed to Trial", "", "verdict"),
    ("a suit that merely proceeds is still 'sued'", "EEOC Disability Suit Against Acme to Proceed", "", "sued"),
    # settled
    ("'to Pay'", "Kroger to Pay $40,000 to Settle EEOC Disability Discrimination Lawsuit", "", "settled"),
    ("'Will Pay'", "Town of Elkton Will Pay $235,000 to Resolve EEOC Age Discrimination Lawsuit", "", "settled"),
    ("'Pays $'", "RYAN'S FAMILY STEAKHOUSE PAYS $500,000 FOR RACE BIAS, SEX DISCRIMINATION AND RETALIATION",
     "", "settled"),
    ("'Settles'", "Wal-Mart Settles EEOC Lawsuit for $50,000", "", "settled"),
    ("a settlement headline that mentions the suit is still a settlement",
     "Rite Way to Settle EEOC Retaliation Suit", "", "settled"),
    ("'Resolves'", "ABM Resolves EEOC Disability Charge", "", "settled"),
    ("'Resolution of 2'", "EEOC Announces Resolution of 2 Charges Against Acme", "", "settled"),
    ("'Recovers'", "EEOC Recovers Back Pay for Acme Workers", "", "settled"),
    ("consent decree", "Meadowbrook Meat Co. Enters into Consent Decree to Eliminate Racist Graffiti Alleged by EEOC",
     "", "settled"),
    ("a contempt ruling about a consent decree counts as settled",
     "Cannon & Wendt Held in Contempt for Failure to Comply Fully with Consent Decree", "", "settled"),
    ("'Conciliates'", "EEOC Conciliates Discriminatory Wage Theft Case", "", "settled"),
    ("'Conciliation Agreement'", "Acme Signs Conciliation Agreement With EEOC", "", "settled"),
    ("'EEOC Obtains $'", "EEOC Obtains $2.75 Million from WRS Compass for Victims of Race Harassment", "", "settled"),
    ("'Reaches Agreement'", "Barenbrug USA Reaches Agreement with EEOC", "", "settled"),
    ("'Reach ... Resolution'", "Acme and EEOC Reach Voluntary Resolution", "", "settled"),
    ("'Enters Into Agreement'", "Acme Enters Into Agreement With EEOC", "", "settled"),
    ("'Agrees to Revise'", "Acme Agrees to Revise Hiring Practices", "", "settled"),
    ("'Agrees to Clarify'", "Acme Agrees to Clarify Leave Policy", "", "settled"),
    ("'Agrees to Change'", "Acme Agrees to Change Hiring Practices", "", "settled"),
    ("'Agrees to Adopt'", "Acme Agrees to Adopt New Policy", "", "settled"),
    ("'Reach Accord'", "Acme and EEOC Reach Accord", "", "settled"),
    ("'Enters Into Settlement'", "Acme Enters Into Settlement With EEOC", "", "settled"),
    ("'to Pay' with no figure", "Acme to Pay Back Wages to Drivers", "", "settled"),
    ("'Will Pay' with no figure", "Acme Will Pay Back Wages to Drivers", "", "settled"),
    ("'Must Pay' with no figure", "Acme Must Pay Back Wages to Drivers", "", "settled"),
    ("'Agrees to Provide'", "Astra USA Agrees To Provide $10 Million To Victims Of Discrimination", "", "settled"),
    ("'Costs X $'", "RACIAL HARASSMENT AND RETALIATION COSTS R.S. BRASWELL / BOBCAT OF MONROE $21,000", "", "settled"),
    ("claims process", "EEOC v. Activision Blizzard Claims Process is Open", "", "settled"),
    ("'In Cooperation With the EEOC'",
     "Furniture Retailer Rooms to Go Adopts Revised Criminal Background Check Procedures In Cooperation With The EEOC",
     "", "settled"),
    # investigation
    ("subpoena approved", "Federal Court Approves EEOC Subpoena in Investigation of Union Pacific", "",
     "investigation"),
    ("a court order about a subpoena is an investigation, not a verdict",
     "Federal Court Orders Vallarta Food Enterprises to Comply with EEOC Subpoenas", "", "investigation"),
    ("subpoena filing", "EEOC Files Subpoena Enforcement Action Against NIKE", "", "investigation"),
    ("'EEOC Investigating'", "EEOC INVESTIGATING FEDEX ON CHARGES OF COMPANYWIDE RACE, NATIONAL ORIGIN DISCRIMINATION",
     "", "investigation"),
    # announcement: agency news
    ("the EEOC launching something", "EEOC Launches E-File for Attorneys", "", "announcement"),
    ("'Issues' and 'Plan'", "EEOC Issues Quality Practices Plan", "", "announcement"),
    ("'Issued' is not 'sued'", "New 'Digest of EEO Law' Issued by EEOC", "", "announcement"),
    ("a person in the headline", "Andrea Lucas Confirmed by United States Senate for a Second Term",
     "Lucas has led the agency's lawsuits and settlements since 2025.", "announcement"),
    ("a statement about a court stays agency news",
     "EEOC Chair Burrows Issues Statement on Supreme Court Rulings", "", "announcement"),
    ("meeting", "Commission Meeting to Examine Workplace Harassment", "", "announcement"),
    ("yearly statistics", "EEOC Reports Job Bias Charges Hit Record High", "", "announcement"),
    ("office news", "EEOC Phoenix District Office Moves to New Location", "", "announcement"),
    ("'EEOC to Hold'", "EEOC to Hold Public Meeting on Wellness Programs", "", "announcement"),
    ("guidance", "EEOC Updates Guidance on Pregnancy Discrimination", "", "announcement"),
    ("proposed rule", "EEOC Publishes Proposed Rule on Wellness Plans", "", "announcement"),
    ("nothing case-like in headline or teaser", "Youth@Work Comes to Phoenix",
     "Students will learn about their rights on the job.", "announcement"),
    ("agency news is not rescued by a teaser that mentions a settlement",
     "EEOC Names New Director of Chicago District",
     "She will pay close attention to systemic cases and has agreed to pay a visit to every field office.",
     "announcement"),
    # announcement: deals with an employer that are not a case
    ("mediation partnership", "Acme and EEOC Enter Mediation Partnership to Resolve Workplace Disputes", "",
     "announcement"),
    ("agreement to mediate", "EEOC and Acme Sign Universal Agreement to Mediate", "", "announcement"),
    ("outreach agreement", "EEOC Baltimore Field Office and Consular Section of the Mexican Embassy Sign Historic "
                           "Outreach Agreement", "", "announcement"),
    ("memorandum of understanding", "EEOC to Sign National Memorandum of Understanding with Mexico Aug. 29", "",
     "announcement"),
    ("'Partner to Resolve'", "EEOC and Acme Partner to Resolve Disputes Early", "", "announcement"),
    ("mediation agreement", "EEOC and Acme Enter Into National Mediation Agreement", "", "announcement"),
    ("national partnership", "EEOC and Acme Renew National Partnership", "", "announcement"),
    ("historic partnership", "EEOC and Acme Sign Historic Partnership Agreement", "", "announcement"),
    ("an agreement to mediate is not a settlement", "Acme Enters Into Agreement to Mediate With EEOC", "",
     "announcement"),
    ("a memorandum of understanding is not a settlement",
     "Acme Reaches Agreement With EEOC on Memorandum of Understanding", "", "announcement"),
    ("a national partnership is not a settlement", "Acme Reaches National Partnership Agreement With EEOC", "",
     "announcement"),
    ("a historic partnership is not a settlement", "Acme Reaches Historic Partnership Agreement With EEOC", "",
     "announcement"),
    ("a company called a Partnership is still a case",
     "Kroger Limited Partnership to Pay $40,000 to Settle EEOC Disability Suit", "", "settled"),
    # translation
    ("Spanish headline", "WirelessComm Demandado Por Acoso Sexual", "", "translation"),
    ("Spanish settlement headline", "Acme Pagará $50,000 Para Resolver Demanda de la EEOC", "", "translation"),
    ("Spanish office news", "Oficina De La EEOC En El Paso Nombra A Nueva Directora", "", "translation"),
    ("a Spanish name in an English headline is not a translation",
     "El Pollo Loco to Pay $50,000 to Settle EEOC Suit", "", "settled"),
    ("one Spanish word is not enough", "EEOC Sues Por Favor Cantina for Retaliation", "", "sued"),
    # Spanish headlines too short to be sure of: classified by their own action word instead
    ("short Spanish headline: 'pagará'", "Acme Pagará $50,000", "", "settled"),
    ("short Spanish headline: 'resuelve' wins over 'demanda'", "Acme Resuelve Demanda", "", "settled"),
    ("short Spanish headline: 'acuerdo'", "Acme Firma Acuerdo", "", "settled"),
    ("short Spanish headline: 'arreglo'", "Acme Paga Arreglo", "", "settled"),
    ("short Spanish headline: 'demandado'", "Acme Demandado", "", "sued"),
    ("short Spanish headline: 'jurado'", "Jurado Falla Contra Acme", "", "verdict"),
    ("'La Rana' and 'Señor' do not make it Spanish",
     "La Rana Hawaii, LLC, A Former Licensee of Señor Frog's, to Pay $350,000 to Settle EEOC Suit", "", "settled"),
    # the teaser decides when the headline does not
    ("teaser says 'will pay'", "Acme Makes Changes After Complaints",
     "Acme will pay $50,000 and furnish other relief.", "settled"),
    ("teaser says 'has agreed to'", "Acme Makes Changes After Complaints",
     "Acme has agreed to overhaul its hiring.", "settled"),
    ("teaser says 'filed suit'", "Acme Makes Changes After Complaints",
     "The EEOC filed suit today in federal court.", "sued"),
    ("teaser says 'lawsuit filed'", "Acme Makes Changes After Complaints",
     "Acme broke the law, according to a lawsuit filed today.", "sued"),
    ("teaser says 'agreed to settle'", "Acme Makes Changes After Complaints",
     "Acme agreed to settle the matter.", "settled"),
    ("teaser says '$50,000 settlement'", "Acme Makes Changes After Complaints",
     "The EEOC announced a $50,000 settlement.", "settled"),
    ("teaser says 'reached a settlement'", "Acme Makes Changes After Complaints",
     "Acme and the agency reached a settlement.", "settled"),
    ("teaser says 'EEOC charges'", "Acme Makes Changes After Complaints",
     "Acme broke the law, the EEOC charges.", "sued"),
    ("teaser says 'agreed to pay'", "Acme Makes Changes After Complaints",
     "Acme agreed to pay back wages.", "settled"),
    ("teaser says 'to settle'", "Acme Makes Changes After Complaints",
     "The parties chose to settle.", "settled"),
    ("teaser says 'charged in a lawsuit'", "Acme Makes Changes After Complaints",
     "Acme broke the law, the agency charged in a lawsuit.", "sued"),
    ("only the opening of the teaser counts", "Acme Makes Changes After Complaints",
     LONG_OPENING + "Acme will pay $50,000.", "announcement"),
    # unclear
    ("about a court, but no ruling, suit or settlement wording",
     "EEOC PETITIONS COURT TO BAN GENETIC TESTING OF RAILROAD WORKERS", "", ""),
    ("teaser shows it is about a case but not what happened",
     "Supreme Court Decision is Step Forward for Victims of Discrimination",
     "In a unanimous decision, the U.S. Supreme Court held today that courts may only conduct a \"relatively "
     "bare-bones review\" of the EEOC's conciliation efforts.", ""),
    ("appellate hearing, nothing decided", "Appellate Argument Set in Acme Matter", "", ""),
    ("circuit hearing, nothing decided", "Ninth Circuit to Hear Acme Matter", "", ""),
    ("trial date, nothing decided", "Trial Date Set in Acme Matter", "", ""),
    ("teaser mentions a charge of harassment but not what happened", "Acme Makes Changes After Complaints",
     "A worker brought a charge of sexual harassment last year.", ""),
    ("teaser mentions a jury but not what happened", "Acme Makes Changes After Complaints",
     "A jury will be picked next month.", ""),
    ("an appeal, nothing decided", "EEOC Appeals Dismissal of Acme Matter", "", ""),
    ("a judge, nothing decided", "Judge Assigned to Acme Matter", "", ""),
    ("an investigation, no subpoena", "EEOC Investigation of Acme Continues", "", ""),
    *[(f"teaser mentions '{hint}' but not what happened", "Acme Makes Changes After Complaints", teaser, "")
      for hint, teaser in (
          ("sued", "Acme was sued last year."),
          ("suit", "The suit is pending."),
          ("lawsuit", "The lawsuit is pending."),
          ("settlement", "A settlement conference is set."),
          ("consent decree", "A consent decree is under review."),
          ("conciliation", "Conciliation efforts failed."),
          ("to pay", "Acme refused to pay overtime."),
          ("charge of discrimination", "A worker brought a charge of race discrimination."),
          ("charges of retaliation", "Workers brought charges of retaliation."))],
]


@one_test_per_case(ACTION_CASES)
class ActionTypeTests(SimpleTestCase):
    """Every action type, and which check wins when more than one could apply."""

    def check(self, _why, title, teaser, action):
        """Check one row of the table."""
        self.assertEqual(classify(title, teaser)["action_type"], action)


class NoEmployerActionTests(SimpleTestCase):
    """Announcements and translations carry no employer; translations carry no tags."""

    def test_translation_has_no_tags_and_no_employer(self):
        """A Spanish repeat adds nothing: its English original already has the tags and the name."""
        result = classify("WirelessComm Demandado Por Acoso Sexual y Represalias",
                          "WirelessComm, Inc., un distribuidor, violó la ley federal, according to a sexual "
                          "harassment and retaliation lawsuit.")
        self.assertEqual(result["action_type"], "translation")
        self.assertEqual(result["tags"], [])
        self.assertEqual(result["employer_raw"], "")
        self.assertEqual(result["employer_key"], "")

    def test_announcement_keeps_its_tags(self):
        """Agency news is still tagged by topic."""
        result = classify("EEOC Updates Guidance on Pregnancy Discrimination", "")
        self.assertEqual(result["tags"], ["pregnancy"])
        self.assertEqual(result["employer_raw"], "")

    def test_investigation_keeps_its_employer(self):
        """A subpoena fight is about an employer, so the name stays."""
        result = classify("EEOC Files Subpoena Enforcement Action Against NIKE", "")
        self.assertEqual(result["employer_raw"], "NIKE")

    def test_result_always_has_the_same_five_fields(self):
        """Whatever the text, classify() returns the same keys."""
        for title in ("EEOC Sues Acme for Age Discrimination", "Joint Resolution", ""):
            with self.subTest(title=title):
                self.assertEqual(set(classify(title, "")),
                                 {"tags", "action_type", "amount", "employer_raw", "employer_key"})

    def test_name_and_key_are_cut_to_fit_the_column(self):
        """Both columns are 300 characters wide."""
        result = classify("EEOC Sues " + "Acme Widget " * 40 + "for Retaliation", "")
        self.assertEqual(len(result["employer_raw"]), 300)
        self.assertLessEqual(len(result["employer_key"]), 300)

    def test_empty_text_is_an_announcement_with_nothing_in_it(self):
        """Empty input does not raise and derives nothing."""
        self.assertEqual(classify("", ""), {"tags": [], "action_type": "announcement", "amount": None,
                                            "employer_raw": "", "employer_key": ""})


# Headlines about the agency itself, one per word or opening AGENCY_NEWS knows.
# All must come out as announcements with no employer.
AGENCY_HEADLINES = [
    "Chairwoman Visits Phoenix Office",
    "New Commissioner Joins EEOC",
    "General Counsel Visits Dallas",
    "New Director for Chicago District",
    "Jane Roe Sworn In at EEOC",
    "Jane Roe Confirmed by Senate",
    "Jane Roe Named to Lead Memphis Office",
    "Jane Roe Appointed to Lead Memphis Office",
    "Statement of Jane Roe on Equal Pay Day",
    "Remarks of Jane Roe at Bar Association",
    "Meeting on Workplace Harassment Set for June",
    "Hearing on Wellness Plans Set for June",
    "Annual Performance Report Now Available",
    "New Guidance on Leave for Employers",
    "New Guidelines on Leave for Employers",
    "Final Rule on Wellness Plans Takes Effect",
    "Proposed Rule on Wellness Plans Open",
    "Rulemaking on Wellness Plans Begins",
    "Regulations on Wellness Plans Take Effect",
    "Public Input Wanted on Wellness Plans",
    "Public Comment Period Opens on Wellness Plans",
    "Free Webinar for Small Employers",
    "Free Workshop for Small Employers",
    "Free Training for Small Employers",
    "Agency Marks 50th Anniversary",
    "Media Advisory: Event in Phoenix",
    "News Availability Tuesday in Phoenix",
    "Press Conference Tuesday in Phoenix",
    "Youth Program Comes to Phoenix",
    "Mediation Pilot Comes to Phoenix",
    "New Webpage for Small Employers",
    "New Website for Small Employers",
    "Charge Status Now Available Online",
    "New Publication for Small Employers",
    "New Fact Sheet for Small Employers",
    "Memorandum on Hiring Goes to Agencies",
    "New Strategic Enforcement Priorities",
    "Fiscal Year 2015 Results Posted",
    "Commission to Meet in Phoenix",
    "Phoenix Office Moves Downtown",
    "Phoenix Office Relocates Downtown",
    "Job Bias Charges Rise Again",
    "Private Sector Filings Reach All-Time High",
    *[f"EEOC {verb} New Effort for Small Employers" for verb in (
        "Launches", "Unveils", "Releases", "Names", "Implements", "Provides", "Concludes", "Opens", "Hosts",
        "Holds", "Updates", "Expands", "Celebrates", "Commemorates", "Partners", "Issues", "Publishes", "Approves",
        "Votes", "Seeks", "Announces", "Requests", "Reports", "Proposes", "Appoints", "Joins", "Comments",
        "Disappointed")],
    *[f"EEOC to {verb} New Effort for Small Employers" for verb in (
        "Add", "Hold", "Host", "Launch", "Release", "Issue", "Publish", "Vote", "Announce")],
    "U.S. EEOC Launches New Effort for Small Employers",
]


# Spanish headlines from the 2010-2015 translations, covering every word the
# Spanish check counts. (headline,)
SPANISH_HEADLINES = [
    "WirelessComm Demandado Por Acoso Sexual",
    "EEOC Demanda a Acme Por Discriminación Contra Trabajadores",
    "Acme Pagará $50,000 Para Resolver Demanda de la EEOC",
    "Acme Resuelve Demanda de Discriminación Por Discapacidad",
    "Acme Llega a un Acuerdo Con la EEOC Sobre Represalias",
    "Acme Paga $50,000 en Arreglo de Demanda del EEOC",
    "Oficina De La EEOC En El Paso Nombra A Nueva Directora",
    "EEOC New Orleans Firma Memorando De Entendimiento Con El Consulado Mexicano",
    "EEOC y Acme Firman Acuerdo Para los Trabajadores",
    "Represalia Contra las Empleadas Que Denunciaron Acoso",
    "Jurado Federal Emite Veredicto Contra Acme Por Acoso",
]


# The Spanish check needs three hits, at least one of them a "strong" word.
# Each strong word, with exactly two weak ones beside it:
SPANISH_STRONG_WORDS = ["Por", "Para", "Contra", "Sobre", "Pagar", "Pagará", "Pagara", "Demanda", "Demandado", "Acoso",
                        "Discriminación", "Discriminacion", "Represalia", "Represalias", "Resuelve", "Acuerdo",
                        "Arreglo", "Oficina", "Oficinas", "Discapacidad", "Firma", "Firman"]


# Each weak word, with exactly two strong ones beside it:
SPANISH_WEAK_WORDS = ["del", "de", "los", "las", "el", "la", "en", "con", "un", "una", "que", "y"]


# English headlines with Spanish words in them. None is a translation.
NOT_SPANISH_HEADLINES = [
    "El Pollo Loco to Pay $50,000 to Settle EEOC Suit",
    "EEOC Sues Por Favor Cantina for Retaliation",
    "La Rana Hawaii, LLC, A Former Licensee of Señor Frog's, to Pay $350,000 to Settle EEOC Suit",
    "EEOC Sues Casa de la Raza for Retaliation",
    "EEOC Sues Por Vida de la Gente Clinic for Retaliation",        # "de la" counts once, not twice
    "Mariscos El Puerto and La Catrina Sued by EEOC",
    "EEOC Sues El Paso Del Norte Restaurant for Sexual Harassment",
]


@one_test_per_case([(headline,) for headline in AGENCY_HEADLINES])
class AgencyNewsTests(SimpleTestCase):
    """Every word and opening AGENCY_NEWS knows makes the release an announcement."""

    def check(self, title):
        """Check one headline, with a teaser that would otherwise make it a settlement."""
        result = classify(title, "Acme, Inc. will pay $50,000 to settle a lawsuit.")
        self.assertEqual(result["action_type"], "announcement")
        self.assertEqual(result["employer_raw"], "")
        # Proof the word mattered: the same teaser under a plain headline is a settlement.
        self.assertEqual(classify("Changes Coming Soon", "Acme, Inc. will pay $50,000 to settle a lawsuit.")
                         ["action_type"], "settled")


@one_test_per_case([(headline,) for headline in SPANISH_HEADLINES])
class SpanishTests(SimpleTestCase):
    """Spanish headlines are translations: no tags, no employer."""

    def check(self, title):
        """Check one headline."""
        result = classify(title, "Acme, Inc. violó la ley federal por acoso sexual y represalias.")
        self.assertEqual(result["action_type"], "translation")
        self.assertEqual(result["tags"], [])
        self.assertEqual(result["employer_raw"], "")


@one_test_per_case([(word,) for word in SPANISH_STRONG_WORDS])
class SpanishStrongWordTests(SimpleTestCase):
    """Each strong Spanish word counts: with two weak words it makes a translation."""

    def check(self, word):
        """Check one word."""
        self.assertEqual(classify(f"Empresa Zenith {word} en la Ciudad", "")["action_type"], "translation")
        # Two weak words alone are not enough.
        self.assertNotEqual(classify("Empresa Zenith en la Ciudad", "")["action_type"], "translation")


@one_test_per_case([(word,) for word in SPANISH_WEAK_WORDS])
class SpanishWeakWordTests(SimpleTestCase):
    """Each weak Spanish word counts: with two strong words it makes a translation."""

    def check(self, word):
        """Check one word."""
        self.assertEqual(classify(f"Zenith Demandado Por Acme {word} Otros", "")["action_type"], "translation")
        # Two strong words alone are not enough.
        self.assertNotEqual(classify("Zenith Demandado Por Acme", "")["action_type"], "translation")


@one_test_per_case([(headline,) for headline in NOT_SPANISH_HEADLINES])
class NotSpanishTests(SimpleTestCase):
    """A Spanish name in an English headline does not make it a translation."""

    def check(self, title):
        """Check one headline."""
        result = classify(title, "")
        self.assertNotEqual(result["action_type"], "translation")
        self.assertNotEqual(result["employer_raw"], "")
