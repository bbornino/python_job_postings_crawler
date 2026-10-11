"""
crawler/tests/test_eeoc_regressions.py

Real EEOC releases that crawler.eeoc_classify once got wrong, with the answer
it must keep giving.
No database and no network. Run this file alone with

    python manage.py test crawler.tests.test_eeoc_regressions

or every EEOC test with

    python manage.py test crawler.tests

When a miss is fixed, add the release to CASES: the headline, enough of the
teaser to decide it, and only the fields that case is about.
"""
from django.test import SimpleTestCase

from crawler.eeoc_classify import classify
from crawler.tests.eeoc_testing import one_test_per_case


# Real releases the rules once got wrong, with the answer they must keep giving.
# "why" says what the case guards against. "expect" lists only the fields that
# matter for it, so an unrelated rule change does not break the test.
CASES = [
    {
        "why": 'the EEOC misspelling its own name',
        "title": 'EECO Sues 40 Steak & Seafood for Pregnancy Discrimination',
        "teaser": ('40 Steak & Seafood, a Bismarck, N.D., restaurant, violated federal law by firing a '
                   'server because she was pregnant, the U.S. Equal Employment Opportunity Commission (EEOC)'
                   ' charged in a lawsuit filed y'),
        "expect": {"employer_raw": '40 Steak & Seafood', "action_type": 'sued'},
    },
    {
        "why": 'headline that ends at the name',
        "title": 'EEOC Sues Bigfoot Energy Services and Iron Mountain Energy',
        "teaser": ('NEW ORLEANS – Oil field service companies Bigfoot Energy Services and Iron Mountain '
                   'Energy Services, operating as a single employer, violated federal law by failing to '
                   'prevent widespread sexual and ra'),
        "expect": {"employer_raw": 'Bigfoot Energy Services and Iron Mountain Energy'},
    },
    {
        "why": 'subpoena order is an investigation, not a verdict',
        "title": 'Federal Court Orders Vallarta Food Enterprises to Comply with EEOC Subpoenas',
        "teaser": ('LOS ANGELES – The U.S. Equal Employment Opportunity Commission (EEOC) announced today '
                   'that a federal court ordered Vallarta Food Enterprises, Inc., and related companies, a '
                   'supermarket chain with approximately 80 locations in Central and Southern California, to'
                   ' fully comply with subpoenas the agency issued in September 2024 relating to '
                   'Commissioner-initiated charges. Specifically, the charge alleged that Vallarta '
                   'Supermarkets failed or refused to recruit, hire, or promote individuals based on their '
                   'race (white, black, and/or Asian)'),
        "expect": {"employer_raw": 'Vallarta Food Enterprises', "action_type": 'investigation', "tags": ['race']},
    },
    {
        "why": 'subpoena filing',
        "title": 'EEOC Files Subpoena Enforcement Action Against NIKE',
        "teaser": ('ST. LOUIS – The U.S. Equal Employment Opportunity Commission (EEOC) announced today that'
                   ' the federal agency filed an action in federal court to compel NIKE, Inc. to produce '
                   'information related to alle'),
        "expect": {"employer_raw": 'NIKE', "action_type": 'investigation'},
    },
    {
        "why": 'describing lead-in stripped from the name',
        "title": 'EEOC Files Subpoena Enforcement Action Against Financial Services Giant Northwestern '
                 'Mutual Over Allegations of DEI-Related Discrimination',
        "teaser": ('MILWAUKEE – The U.S. Equal Employment Opportunity (EEOC) filed an action in federal '
                   'court today to compel Milwaukee-based financial services provider Northwestern Mutual to'
                   ' produce information about t'),
        "expect": {"employer_raw": 'Northwestern Mutual', "action_type": 'investigation'},
    },
    {
        "why": 'agency news stays an announcement even when the teaser mentions settlements',
        "title": 'EEOC Acting Chair Andrea Lucas Confirmed by United States Senate for a Second Term',
        "teaser": ('“I am honored to be confirmed by the Senate to serve a second term at the EEOC,” said '
                   'EEOC Acting Chair Andrea Lucas. “I look forward to continuing the historic progress this'
                   ' agency has made since the'),
        "expect": {"employer_raw": '', "action_type": 'announcement'},
    },
    {
        "why": 'EEOC doing something administrative',
        "title": 'EEOC Launches E-File for Attorneys',
        "teaser": ('WASHINGTON -- The U.S. Equal Employment Opportunity Commission (EEOC) announced today '
                   'the launch of E-File for Attorneys , an application which allows attorneys to submit '
                   'charges of discrimination ele'),
        "expect": {"action_type": 'announcement'},
    },
    {
        "why": 'agency news wins over court wording',
        "title": 'Statement from EEOC Chair Charlotte A. Burrows on Supreme Court Ruling on College '
                 'Affirmative Action Programs',
        "teaser": ('The following is a statement from U.S. EEOC Chair Charlotte A. Burrows, in response to '
                   'today’s Supreme Court decision in Students for Fair Admissions, Inc. v. President & '
                   'Fellows of Harvard College an'),
        "expect": {"action_type": 'announcement'},
    },
    {
        "why": 'a mediation partnership is not a settlement against the company',
        "title": 'EEOC AND INTEL ENTER MEDIATION PARTNERSHIP TO RESOLVE WORKPLACE DISPUTES',
        "teaser": ("EEOC's 72nd National Mediation Agreement and First with Silicon Valley High-Tech Company"
                   ' SANTA CLARA, Calif. - The U.S. Equal Employment Opportunity Commission (EEOC) and Intel'
                   " Corporation, the world'"),
        "expect": {"employer_raw": '', "action_type": 'announcement'},
    },
    {
        "why": 'case-name headline',
        "title": 'EEOC v. Activision Blizzard Claims Process is Open',
        "teaser": ('LOS ANGELES – On March 30, 2022, a federal court approved the settlement of a sexual '
                   'harassment lawsuit brought by the U.S. Equal Employment Opportunity Commission (“EEOC”) '
                   'against Activision Blizzard'),
        "expect": {"employer_raw": 'Activision Blizzard', "action_type": 'settled'},
    },
    {
        "why": 'name opens a later teaser sentence',
        "title": 'Restaurant Admits to Pregnancy Discrimination and Pays $30,000 to Resolve EEOC Lawsuit',
        "teaser": ('NEW ORLEANS – A Louisiana restaurant admitted that it violated federal law when it fired'
                   ' and then later refused to rehire a worker because she was pregnant as part of federal '
                   'court resolution with the U.S. Equal Employment Opportunity Commission, the EEOC '
                   'announced today. Bourne’s House, LLC, doing '),
        "expect": {"employer_raw": 'Bourne’s House', "action_type": 'settled', "amount": 30000},
    },
    {
        "why": "name after 'owned and operated by'",
        "title": 'Carmel Restaurants to Pay $175,000 to Settle Sexual Harassment Lawsuit',
        "teaser": ('Carmel restaurants owned and operated by JCFB, Inc. agreed to pay $175,000 to settle a '
                   'federal sexual harassment lawsuit filed on behalf of male and female kitchen staff, the '
                   'U.S. Equal Employment Opp'),
        "expect": {"employer_raw": 'JCFB'},
    },
    {
        "why": 'contempt headline',
        "title": 'Court Holds Sherwood Food Distributors in Contempt for Violation of EEOC Consent Decree '
                 'in Class Sex Discrimination Case',
        "teaser": ('CLEVELAND – A federal judge has entered an opinion and order finding Detroit-'
                   'head\xadquartered Sherwood Food Distributors, LLC in contempt of court for failing to pay '
                   'its payroll tax liability in violati'),
        "expect": {"employer_raw": 'Sherwood Food Distributors'},
    },
    {
        "why": "'Ordering X to Pay'",
        "title": 'EEOC Obtains Judgment Ordering Ceviche House to Pay $130,691 for Sexual Harassment',
        "teaser": ('SAN JUAN, PUERTO RICO – A federal court has ordered a San Juan restaurant to pay '
                   '$130,691 in a sexual harassment and retaliation discrimination lawsuit filed by the U.S.'
                   ' Equal Employment Opportunity C'),
        "expect": {"employer_raw": 'Ceviche House', "action_type": 'verdict', "amount": 130691},
    },
    {
        "why": "'EEOC and X Agree'",
        "title": 'EEOC and Hennepin Healthcare System Agree to Settle Class Discrimination Investigation',
        "teaser": ('MINNEAPOLIS – The U.S. Equal Employment Opportunity Commission (EEOC) today announced it'
                   ' has reached a settlement with Hennepin Healthcare System, Inc. (HHS), a healthcare '
                   'provider within Hennepin Cou'),
        "expect": {"employer_raw": 'Hennepin Healthcare System', "action_type": 'settled'},
    },
    {
        "why": "'X and EEOC Reach'",
        "title": 'Medstar Good Samaritan Hospital and EEOC Reach $195,000 Agreement to Conciliate EEOC '
                 'Disability Discrimination Charge',
        "teaser": ('The U.S. Equal Employment Opportunity Commission (EEOC) and MedStar Good Samaritan '
                   'Hospital (MGSH) announced today the successful conciliation and settlement of a charge '
                   'filed with the agency under th'),
        "expect": {"employer_raw": 'Medstar Good Samaritan Hospital', "action_type": 'settled'},
    },
    {
        "why": "'EEOC Releases X from'",
        "title": 'EEOC Releases UPS from Future Consent Decree Reporting Obligations',
        "teaser": ('CHICAGO – The U.S. Equal Employment Opportunity Commission (EEOC) has, with court '
                   'approval, released United Parcel Services, Inc. (UPS) from its remaining obligations '
                   'under a consent decree that in 20'),
        "expect": {"employer_raw": 'UPS'},
    },
    {
        "why": "'Fired by X', and an age verdict",
        "title": 'EEOC Wins Jury Verdict of $458,000 for Two Older Workers Fired by AZ Metro',
        "teaser": ('A nine-member jury sitting in Brooklyn has returned a verdict for the U.S. Equal '
                   'Employment Opportunity Commission (EEOC) on two claims of age discrimination against AZ '
                   'Metro Distributors, LLC, the fe'),
        "expect": {"employer_raw": 'AZ Metro', "action_type": 'verdict', "tags": ['age'], "amount": 458000},
    },
    {
        "why": "'X Reaches Agreement with EEOC'",
        "title": 'Barenbrug USA Reaches Agreement with EEOC',
        "teaser": ('The U.S. Equal Employment Opportunity Commission (EEOC) and Oregon-headquartered grass '
                   'seed company Barenbrug USA have reached a voluntary conciliation agreement to resolve '
                   'allegations of discriminati'),
        "expect": {"employer_raw": 'Barenbrug USA', "action_type": 'settled'},
    },
    {
        "why": 'a description is kept when no name exists',
        "title": 'EEOC Sues Kansas School District For Paying Female Principal Less Than Male Principals',
        "teaser": ('A Kansas school district violated federal law by paying women and men unequally for jobs'
                   ' with the same required skill, effort, and responsibility, the U.S. Equal Employment '
                   'Opportunity Commission (EEO'),
        "expect": {"employer_raw": 'Kansas School District', "tags": ['sex', 'equal_pay']},
    },
    {
        "why": "name after 'the EEOC had charged'",
        "title": 'Federal Court Enters Judgment in Favor Of EEOC In Suit Charging Equal Pay Act Violation',
        "teaser": ('A Nebraska bank will pay $30,598 to a woman whom it unlawfully paid less than a man, '
                   'pursuant to a federal court judgment in a pay discrimination lawsuit filed by the U.S. '
                   'Equal Employment Opportunity Commission (EEOC), the federal agency announced today. The '
                   'EEOC had charged Wood River, Neb.-based Heritage Bank with paying a female employee '
                   'lower wages because of her sex. The judgment and order a'),
        "expect": {"employer_raw": 'Heritage Bank', "action_type": 'verdict'},
    },
    {
        "why": "'X Harassed ..., EEOC Charges'",
        "title": 'North Dakota Employer Harassed Worker Because of His Sexual Orientation, EEOC Charges',
        "teaser": ('The U.S. Equal Employment Opportunity Commission (EEOC) announced today that it has '
                   'filed its first North Dakota case charging that an employer subjected a male employee to'
                   ' sexual harassment because o'),
        "expect": {"employer_raw": 'North Dakota Employer', "action_type": 'sued', "tags": ['lgbtq', 'harassment']},
    },
    {
        "why": "'on the basis of age'",
        "title": 'Bank of Albuquerque Discriminated on the Basis of Age and Sex, EEOC Alleges in Lawsuit',
        "teaser": ('BOK Financial Corporation, doing business as the Bank of Albuquerque, unlawfully '
                   'discharged managers Elizabeth Morantes and Yolanda Fernandez because they were women '
                   'over 40 years of age, the U.S. Equ'),
        "expect": {"employer_raw": 'Bank of Albuquerque', "tags": ['age', 'sex']},
    },
    {
        "why": "tags from a list: 'based on age (over 40), sex and race'",
        "title": 'Aerotek to Pay $3.525 Million to Conciliate  EEOC Systemic Investigations',
        "teaser": ('CHICAGO – Aerotek, a national temporary placement agency, has agreed to pay $3.525 '
                   'million to resolve federal systemic investigations relating to the hiring and placement '
                   'of individuals assigned to work at Aerotek’s clients, the U.S. Equal Employment '
                   'Opportunity Commission (EEOC) announced today. According to the EEOC, Aerotek failed to '
                   'recruit and denied assignments/placements and/or hiring to individuals based on age '
                   '(over 40), sex and race. Such alleged conduct violates Title VII of the Civil'),
        "expect": {"employer_raw": 'Aerotek', "tags": ['age', 'sex', 'race'], "amount": 3525000},
    },
    {
        "why": "age mentioned as 'the candidate's age'",
        "title": 'EEOC Sues Software People, Inc. for Retaliation',
        "teaser": ('NEW YORK – Software People, an IT support staffing agency based in Long Island, New York'
                   ' that contracts with local and state governmental agencies throughout the country, '
                   'violated federal law when it refused to refer an otherwise qualified candidate for a '
                   'position after he objected to a recruiter’s inquiry concerning the candidate’s age, the '
                   'U.S. Equal Employment Opportunity Commission (EEOC) char'),
        "expect": {"tags": ['age', 'retaliation']},
    },
    {
        "why": "teaser's opening description as a last resort",
        "title": 'EEOC Conciliates Discriminatory Wage Theft Case',
        "teaser": ('A Steamboat Springs, Colo., restaurant has agreed to pay $50,000 to resolve race and '
                   'national origin discrimination charges, including charges of wage theft, by the U.S. '
                   'Equal Employment Opportunity C'),
        "expect": {"employer_raw": 'Steamboat Springs, Colo., restaurant', "action_type": 'settled'},
    },
    {
        "why": 'Spanish release is a translation',
        "title": 'Oficina De La EEOC En El Paso Firma Acuerdo Con El Consulado Mexicano',
        "teaser": ('La Oficina de El Paso de la Comisión Para la Igualdad de Oportunidades en el Empleo de '
                   'los EE.UU. (EEOC), firmó un Memorando de Entendimiento con el Consulado General de '
                   'México en El Paso hoy. El acue'),
        "expect": {"employer_raw": '', "action_type": 'translation', "tags": []},
    },
    {
        "why": "'Jury Finds X Liable'",
        "title": 'Jury Finds Parker Drilling Liable in EEOC Disability Discrimination Suit',
        "teaser": ('A federal judge ordered that $245,619be paid to an Alaskan oil rig worker today in a '
                   'disability discrimination lawsuit filed by the U.S. Equal Employment Opportunity '
                   'Commission (EEOC), the federal age'),
        "expect": {"employer_raw": 'Parker Drilling', "action_type": 'verdict'},
    },
    {
        "why": 'genetic information tag',
        "title": 'EEOC Sues Dana Sealing Manufacturing for Illegally Acquiring Genetic Information',
        "teaser": ('DANVILLE, Ky. — Dana Sealing Manufacturing, LLC, a manufacturer of automotive parts, '
                   'violated federal law when it collected the medical history of applicants’ family members'
                   ' during the pre-employment '),
        "expect": {"employer_raw": 'Dana Sealing Manufacturing', "tags": ['genetic_info']},
    },
    {
        "why": "tags from 'based on race and sex'",
        "title": 'Target Corporation to Pay $2.8 Million to Resolve EEOC Discrimination Finding',
        "teaser": ('Target Corporation, which is headquartered in Minneapolis, has agreed to pay $2.8 '
                   "million to resolve a Commissioner's charge of discrimination which was investigated in "
                   'the Minneapolis Area Office of the U.S. Equal Employment Opportunity Commission (EEOC). '
                   'Based on the investigation, EEOC found reasonable cause to believe that three employment'
                   ' assessments formerly used by Target disproportionately screened out applicants for '
                   'exempt-level professional positions based on race and sex. The tests we'),
        "expect": {"employer_raw": 'Target Corporation', "tags": ['sex', 'race']},
    },
    {
        "why": 'law-boilerplate sentence adds no tags',
        "title": 'Justice Department Files Pregnancy Discrimination Lawsuit against the Chicago Board of '
                 'Education',
        "teaser": ('The Justice Department today announced the filing of a lawsuit against the Chicago Board'
                   ' of Education, alleging that the board discriminated against pregnant teachers at '
                   'Scammon Elementary School by subjecting them to adverse personnel actions, including '
                   'termination in some instances, after they announced their pregnancies. According to the '
                   'complaint, these adverse personnel actions were in violation of Title VII of the Civil '
                   'Rights Act of 1964. Title VII is a federal statute that prohibits employment '
                   'discrimination on the basis of sex, race, color, national origin and religion. The '
                   'statute explicitly prohibits employers from discriminating against female employees due '
                   'to pregnancy, childbirth or related medical conditions.'),
        "expect": {"tags": ['sex', 'pregnancy', 'disability']},
    },
    {
        "why": "court procedure counts as a verdict; name after 'Denies'",
        "title": 'Court Denies Key Menards Motion in EEOC Pregnancy Discrimination Case',
        "teaser": ('Chief Judge David R. Herndon of the Southern District of Illinois issued an order on '
                   'January 22 denying the motion of the hardware store chain Menards for summary judgment '
                   'in a sex / pregnancy discrim'),
        "expect": {"employer_raw": 'Menards', "action_type": 'verdict'},
    },
    {
        "why": 'teaser decides the action type when the headline cannot',
        "title": 'EEOC Defends Women’s Rights to Single-Sex Spaces at Work in Illinois',
        "teaser": ('ST. LOUIS — The City of O’Fallon, Illinois, which provides a variety of municipal '
                   'services to its nearly 35,000 residents in St. Clair County, agreed to resolve a charge '
                   'of sex discrimination and retaliation with the U.S. Equal Employment Opportunity '
                   'Commission (EEOC), the federal agency announced today. The EEOC’s investigation of the '
                   'charge found reasonable cause to believe that the city subjected an employee to '
                   'harassment when it failed to provide a sex-designated locker room'),
        "expect": {"employer_raw": 'The City of O’Fallon, Illinois', "action_type": 'settled', "tags": ['pro_trans', 'sex', 'retaliation', 'harassment']},
    },
    {
        "why": "the employer, not the victim after 'Against'",
        "title": 'Jury in EEOC Suit Finds that RockAuto Discriminated Against Applicant Because of His Age',
        "teaser": ('MADISON, Wis. – A jury has determined that RockAuto, a Madison, Wis.-headquartered '
                   'internet-based auto parts seller, violated federal law when it failed to hire a '
                   'qualified job applicant because of hi'),
        "expect": {"employer_raw": 'RockAuto', "action_type": 'verdict', "tags": ['age']},
    },
    {
        "why": "the employer, not the victim after 'Against'",
        "title": 'Triborough Bridge & Tunnel Authority Discriminated Against Pregnant Female Officers, '
                 'U.S. EEOC & U.S. DOJ Found',
        "teaser": ('Triborough Bridge and Tunnel Authority (TBTA), the law enforcement division of the TBTA '
                   'Operating Force, will pay $206,500 and furnish other relief to resolve charges of '
                   'pregnancy discrimination broug'),
        "expect": {"employer_raw": 'Triborough Bridge & Tunnel Authority'},
    },
    {
        "why": "'Claim That X Retaliated Against Employees'",
        "title": 'Federal Court Refuses To Toss Out EEOC Claim That Chrysler Retaliated Against Employees',
        "teaser": ("Automobile giant Chrysler Group, LLC's effort to have an U.S. Equal Employment "
                   'Opportunity Commission (EEOC) claim of unlawful retaliation thrown out of court has '
                   'failed, the agency announced today. T'),
        "expect": {"employer_raw": 'Chrysler', "action_type": 'verdict'},
    },
    {
        "why": 'describing lead-in stripped',
        "title": 'Pancake Chain IHOP to Pay $700,000 to Settle Sexual Harassment and Retaliation Lawsuit',
        "teaser": ('Chain of Franchises Subjected Employees to Sexual Harassment and Retaliation, Federal '
                   'Agency Charges LAS VEGAS - Several franchisees of the popular IHOP restaurant chain in '
                   'Nevada and New York will pa'),
        "expect": {"employer_raw": 'IHOP'},
    },
    {
        "why": 'a lead-in is kept when it is part of the real name',
        "title": 'EEOC Sues Coca-Cola Bottling Company United for Disability Discrimination',
        "teaser": ('NEW ORLEANS – Coca-Cola Bottling Company United, Inc. (CCBCU), the third-largest bottler'
                   ' and distributor of Coca-Cola products in the United States and headquartered in '
                   'Birmingham, Alabama, violated f'),
        "expect": {"employer_raw": 'Coca-Cola Bottling Company United'},
    },
    {
        "why": "a name ending in 'In' is still a name",
        "title": 'Sonic Drive-In Sued by EEOC for Sexual Harassment',
        "teaser": ('DALLAS — At least three teen female carhops were subjected to sex harassment by SDI of '
                   'Mineola, LLC, doing business as Sonic Drive-In, the U.S. Equal Employment Opportunity '
                   'Commission (EEOC) charged i'),
        "expect": {"employer_raw": 'Sonic Drive-In'},
    },
    {
        "why": "name opens the headline; 'Against' has only a description",
        "title": "WAL-MART TV AD TELLS THE STORY OF TWO DEAF MEN'S EMPLOYMENT DISCRIMINATION CLAIM AGAINST"
                 ' THE RETAIL GIANT',
        "teaser": ('TUCSON and PHOENIX - Beginning this week, and for the next two weeks, ABC, CBS and NBC '
                   'affiliates in Arizona will air a 60-second commercial in Phoenix and Tucson featuring '
                   'two young men who are deaf telling about their experience filing a lawsuit against Wal-'
                   'Mart Stores, Inc., pursuant to the Ameri'),
        "expect": {"employer_raw": 'WAL-MART'},
    },
]


@one_test_per_case([(case["why"], case["title"], case["teaser"], case["expect"]) for case in CASES])
class RegressionTests(SimpleTestCase):
    """Each real release in CASES still comes out the way it was fixed to."""

    def check(self, _why, title, teaser, expect):
        """Check one row of the table."""
        result = classify(title, teaser)
        for field, expected in expect.items():
            self.assertEqual(result[field], expected, f"{field} is wrong")
