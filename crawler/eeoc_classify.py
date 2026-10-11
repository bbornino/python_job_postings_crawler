"""
crawler/eeoc_classify.py

Reads the text of one EEOC press release and decides what it is: the action
type, the employer, the tags and the dollar amount.

classify(title, teaser) is the entry point. Everything else here is the
patterns it uses and their helpers. Nothing in this file touches the network,
the database or Django, so it can be imported and tested anywhere.
"""

import re
import unicodedata
from html import unescape


# tag -> pattern, matched against title + teaser, case-insensitive.
# The keys must be values of Tag in the model; see the comment there for how
# to read them (plain tag = accused of it, pro_ tag = targeted for supporting it).
# Acronyms are wrapped in (?-i:...) so they stay case-sensitive ("ADA", not "Ada").
TAG_PATTERNS = {
    # \bage, not a bare "age": "wage discrimination" was being tagged as age.
    "age": r"\bage[- ](?:discriminat|bias|harass|based|suit|lawsuit|claims?|charges?)|ageis[mt]|(?-i:\bADEA\b)"
           r"|older (?:workers?|employees?|applicants?|agents?|staff|individuals|women|men)"
           r"|over the age of 40|age 40 (?:and|or) (?:over|older)"
           r"|(?:due to|concerning|regarding) (?:(?:his|her|their|the \w+[’']s) )?age\b"
           # age as one item in a list: "Race, Sex, National Origin and Age", "gender and age"
           r"|(?:sex|race|gender|origin|disability|religion|color),? (?:and |or )?age\b"
           r"|younger \w+ who|(?:because of|based on|basis of) (?:(?:his|her|their) )?age\b"
           r"|\bage(?:,| and| or| &)[^.]{0,30}?(?:discriminat|harass|bias|retaliat)",   # "Age and Sex Discrimination"
    "trans": r"transgender|gender identity",
    "lgbtq": r"sexual orientation|(?-i:\bLGBT)|\bgay\b|lesbian",
    # The EEOC acting against trans inclusion (e.g. "single-sex spaces" cases),
    # so the employer named is usually the supportive one. Worth a human read.
    "pro_trans": r"single-sex|biological(?:ly)? (?:sex|men|women|males?|females?)"
                 r"|gender ideology|intimate spaces|sex-rejecting",
    # Same idea as pro_trans: the EEOC going after an employer's diversity
    # program. A sex or race tag on the same row is not a red flag.
    "pro_dei": r"(?-i:\bDEI\b)|diversity,? equity|diversity (?:program|initiative|polic)",
    # "sex discrimination", not "sexual harassment" (that's the harassment tag).
    "sex": r"sex(?:-based)? (?:\w+ )?discriminat|\bsex[- ](?:bias|based)|gender(?:-based)? (?:\w+ )?(?:discriminat|bias)"
           r"|based on sex|because of (?:her|their) sex|refus\w+ to hire (?:women|females?)"
           r"|against (?:women|female)|paying (?:a )?(?:women|female \w+) less"
           r"|(?:hire|hiring(?: of)?) (?:females?|males?|women|(?:fe)?male applicants)\b|gender-based"
           r"|jobs to (?:\w+ ){0,4}women"
           # sex as one item in a list of bases: "based on age (over 40), sex and race"
           r"|(?:age|race|color|religion|origin|disability)(?: \([^)]*\))?,? (?:and |or )?sex\b"
           r"|\bsex,? (?:and |or )?(?:age|race|color|religion|national origin|disability)\b"
           r"|\bsex(?:,| and| or| &|/)[^.]{0,30}?(?:discriminat|harass|bias)",   # "Race, Sex, and National Origin Discrimination"
    # Read-before-trusting tags: most hits are accommodation cases that don't
    # matter here; the ones that do are forced religion at work.
    "religion": r"religio|muslim|antisemit|\bsikhs?\b|hijab|sabbath",
    # A named group counts only next to "against" / "harassment of": a release that
    # merely mentions a Latina employee in a sexual harassment case is not this.
    "national_origin": r"national origin|anti-immigrant|ethnic harass|non-hispanic|9/11 backlash"
                       r"|paying (?:hispanic|latino) (?:workers|employees) less"
                       r"|(?:against|harass\w*(?: of)?|segregated) (?:[\w-]+,? ){0,3}?"
                       r"(?:hispanics?|latin[oa]s?|arabs?|filipinos?|haitians?)\b",
    # Red flag: employer favored visa holders over U.S. workers.
    "visa_preference": r"H-1B|visa[- ](?:based|holders?|workers?|status)"
                       r"|against (?:U\.S\.|American|domestic) workers"
                       r"|(?:favor|prefer)\w* (?:foreign|visa)",
    "race": r"\brace[- /](?:discriminat|harass|bias|based)|racial(?:ly)? (?:discriminat|harass|bias|slurs?|hostil)"
            r"|(?:because of|based on) (?:his|her|their) race|on the basis of race|african[- ]americans?"
            r"|against (?:black|non-white)|black (?:job )?(?:workers?|employees?|applicants?|candidates?)"
            r"|\bminorities\b"
            # race as one item in a list of bases
            r"|(?:age|sex|gender|color|religion|origin|disability)(?: \([^)]*\))?,? (?:and |or )?race\b"
            r"|\brace,? (?:and |or )?(?:age|sex|gender|color|religion|national origin|disability)\b"
            r"|\brace(?:,| and| or| &|/)[^.]{0,30}?(?:discriminat|harass|bias)",   # "Race and National Origin Harassment"
    "pregnancy": r"pregnan|(?-i:\bPWFA\b)|breast pump|nursing mother|lactat|maternity leave",
    "retaliation": r"retaliat",
    "harassment": r"harass",
    "hostile_env": r"hostile work environment",
    # Deliberately not a bare "disabilit": that matched employers described as
    # "a nonprofit providing disability support services" in non-disability cases.
    # Also no "reasonable accommodation", which pregnancy and religion cases use.
    "disability": r"disabilit\w* (?:\w+ )?(?:dis\w*iminat|bias|harass|lawsuit|suit|charge|case|claim|accommodat)"
                  r"|(?-i:\bADA\b)|Americans with Disabilities Act|discapacidad"
                  r"|disabled (?:workers?|employees?|applicants?)"
                  r"|(?:employee|applicant|worker)s? with (?:an? )?(?:\w+ )?disabilit"
                  r"|because of (?:(?:his|her|their|a|an) )?(?:\w+ )?disabilit"
                  r"|\bdeaf\b|\bblind\b|hearing[- ]impair|(?-i:\bHIV\b|\bPTSD\b)"
                  r"|bipolar|epilep|diabet|\bcancer\b|wheelchair|autis[mt]|amput"
                  r"|medical (?:conditions?|information|inquir\w+|leave polic)"
                  r"|disability(?:,| and| or| &)[^.]{0,30}?discriminat"
                  r"|disabilit\w* (?:investigation|finding)|(?:for|charge of) disability\b"
                  r"|(?:due to|treat) (?:(?:his|her|their) )?disabilit|\bimpairments?\b|paraplegi|quadriplegi|tourette"
                  r"|fitness[- ]for[- ]duty|medical (?:exams?|examinations?|releases?)|on medical leave"
                  r"|leave for (?:\w+ ){0,3}surgery|crutches"
                  # disability as one item in a list of bases
                  r"|(?:age|sex|gender|race|color|religion|origin)(?: \([^)]*\))?,? (?:and |or )?disability\b",
    # Asking applicants or staff for family medical history (the GINA law).
    "genetic_info": r"genetic[- ](?:information|non-?discrimination|discrimination|testing|bias)|family medical history|medical history of \w+[’'] family|(?-i:\bGINA\b)",
    "equal_pay": r"equal pay|unequal pay|(?:pay|wage) (?:discriminat|bias|dispar)"
                 r"|(?:sex|gender)-based (?:pay|wage)|(?:paying|paid) (?:a )?(?:women|her|female \w+) less",
}
TAG_REGEXES = {tag: re.compile(p, re.IGNORECASE) for tag, p in TAG_PATTERNS.items()}

# Teaser sentences that describe the law in general, not this case, and so
# must not produce tags:
#   "Title VII ... prohibits employment discrimination on the basis of sex,
#    race, color, national origin and religion."
#   "... under Title VII, the ADA, the ADEA or the Genetic Information
#    Nondiscrimination Act."
# A sentence is dropped when it has a "prohibits"-type verb plus three or more
# protected classes, or when it names three or more statutes. One class or one
# statute is left alone: "which prohibits discrimination based on sex" is
# usually a true statement about the case.
LAW_VERB = re.compile(r"\b(?:prohibit\w*|forbid\w*|makes it (?:illegal|unlawful))\b", re.IGNORECASE)
PROTECTED_CLASS = re.compile(r"\b(?:race|color|religion|sex|national origin|age|disabilit\w+|genetic information"
                             r"|pregnancy|gender identity|sexual orientation)\b", re.IGNORECASE)
# One pattern per law, so a law's name and its acronym count once:
# "the Americans with Disabilities Act (ADA)" is one statute, not two.
STATUTES = [re.compile(p) for p in (
    r"Title VII",
    r"Americans [Ww]ith Disabilities Act|\bADA\b",
    r"Age Discrimination in Employment Act|\bADEA\b",
    r"Genetic Information Non-?[Dd]iscrimination Act|\bGINA\b",
    r"Equal Pay Act|\bEPA\b",
    r"Pregnant Workers Fairness Act|\bPWFA\b",
    r"Rehabilitation Act",
)]


def without_law_boilerplate(teaser: str) -> str:
    """The teaser minus sentences that only describe what the laws cover."""
    kept = []
    for sentence in re.split(r"(?<=[.!?]) +", teaser):
        classes = {m.lower() for m in PROTECTED_CLASS.findall(sentence)}
        statutes = sum(1 for law in STATUTES if law.search(sentence))
        if (LAW_VERB.search(sentence) and len(classes) >= 3) or statutes >= 3:
            continue
        kept.append(sentence)
    return " ".join(kept)

# Checked in order, first match wins. A headline that opens "EEOC Sues" is
# always a suit, whatever else it mentions. The general "sued" is last because
# settlement titles often mention the suit too ("... to Settle EEOC Age Suit").
# Word boundaries matter here: a bare "sued" matched "Issued", and a bare
# "charges" matched annual statistics releases.
ACTION_PATTERNS = [
    ("sued", r"^EEOC Sues\b"),
    ("verdict", r"verdict|\bjury\b|judgment|(?:court|judge) (?:rules|orders|finds|awards|affirms|reaffirms|upholds|imposes)"
                r"|(?:grants|enters) (?:\w+ ){0,3}injunction"
                r"|court issues (?:\w+ ){0,3}(?:ruling|decision)|favorable ruling"
                r"|\bliable\b|EEOC (?:wins|prevails|scores)\b|\bvictory\b|\bawarded \$|\bjurado\b"
                # a court sending the case to trial is a ruling, even when the headline also says "suit"
                r"|to (?:proceed to|face) trial"),
    ("settled", r"to pay|will pay|must pay|\bpays?\b \$|\bsettle|resolv|resolution of \d"
                r"|recover|consent decree|conciliates?\b|to conciliate|conciliation agreement"
                r"|EEOC obtains (?:\w+ ){0,3}\$|reach(?:es)? (?:\S+ ){0,4}(?:agreement|resolution|accord)\b"
                r"|enters? into (?:\w+ ){0,2}(?:agreement|settlement)|agrees? to (?:clarify|revise|change|adopt)"
                r"|\bcosts? .*\$[\d,]"       # "RACIAL HARASSMENT AND RETALIATION COSTS X $21,000"
                r"|agrees? to provide|claims process|in cooperation with (?:the )?EEOC|\bpagar|\bresuelve\b|\bacuerdo\b|\barreglo\b"),
    # Any other headline that mentions a suit is about a case still in court
    # ("EEOC Disability Suit Against X to Proceed"), which counts as sued.
    ("sued", r"\bsues?\b|\bsued\b|\b(?:law)?suits?\b|\bcase against\b|\bdemanda"
             r"|EEOC (?:charges|alleges|claims|challenges|accuses)\b|\bcharged (?:with|by)\b|, EEOC (?:says|said|charged)\b"),
]
ACTION_REGEXES = [(name, re.compile(p, re.IGNORECASE)) for name, p in ACTION_PATTERNS]
CASE_TYPES = {"sued", "settled", "verdict"}     # action types that have an employer
NO_EMPLOYER_TYPES = {"announcement", "translation"}     # action types that never have one
# Spanish-language releases (2010-2015) repeat an English release already in the
# table, so counting them would count the case twice. A headline is Spanish when
# it has two or more of these words and at least one is from the first group.
SPANISH_STRONG = re.compile(r"\b(?:por|para|contra|sobre|pagar[áa]?|demanda\w*|acoso|discriminaci[oó]n"
                            r"|represalias?|resuelve|acuerdo|arreglo|oficinas?|discapacidad|firman?)\b", re.IGNORECASE)
SPANISH_WEAK = re.compile(r"\b(?:de la|del|de|los|las|el|la|en|con|una?|que|y)\b", re.IGNORECASE)
# A headline that matched no action pattern is agency news ("EEOC Launches
# Youth@Work Initiative"), unless the headline or the start of the teaser has
# one of these words. Those releases are about an employer but the headline is
# not a plain suit, settlement or verdict (a subpoena, an injunction, an
# appeal), so the action type stays blank and the row waits for a human look.
TITLE_CASE_HINT = re.compile(r"subpoena|injunction|\btrial\b|\bappeals?\b|\bappellate\b|\bcourt\b|\bjudge\b"
                             r"|\bcircuit\b|\binvestigat", re.IGNORECASE)
TEASER_CASE_HINT = re.compile(r"\b(?:law)?suit\b|\bsued\b|settle|consent decree|conciliat|\bjury\b|to pay|will pay"
                              r"|agreed to resolve|charges? of (?:\w+ ){0,4}(?:discrimination|harassment|retaliation)",
                              re.IGNORECASE)
# Headlines about the agency itself: people, meetings, publications. These are
# announcements even when the teaser mentions settlements or lawsuits in passing
# ("... Confirmed by United States Senate for a Second Term").
AGENCY_NEWS = re.compile(
    r"\b(?:Chair(?:man|woman)?|Commissioners?|General Counsel|Director|Sworn|Confirmed|Named|Appointed"
    r"|Statement|Remarks|Meeting|Hearing|Reports?|Guidance|Guidelines|(?:Final|Proposed) (?:\w+ )?Rules?|Rulemaking|Regulations?|Public (?:Input|Comment)"
    r"|Webinar|Workshop|Training|Anniversary|Media Advisory|News Availability|Press Conference|Program|Pilot"
    r"|Webpage|Website|Online|Publication|Fact Sheet|Memorandum|Strategic|Fiscal Year)\b"
    # The EEOC doing something administrative: "EEOC Launches E-File for Attorneys".
    r"|^Commission\b|Office (?:Moves|Relocates)\b|Bias Charges|All-Time High"
    r"|^(?:U\.S\. )?EEOC (?:Launches|Unveils|Releases|Names|Implements|Provides|Concludes|Opens|Hosts|Holds"
    r"|Updates|Expands|Celebrates|Commemorates|Partners|Issues|Publishes|Approves|Votes|Seeks|Announces"
    r"|Requests|Reports|Proposes|Appoints|Joins|Comments|Disappointed"
    r"|to (?:Add|Hold|Host|Launch|Release|Issue|Publish|Vote|Announce))\b", re.IGNORECASE)
# Subpoena fights happen during an investigation, before any suit, so they get
# their own action type. A headline like "Court Orders X to Comply with EEOC
# Subpoenas" would otherwise read as a verdict.
INVESTIGATION = re.compile(r"subpoena|EEOC investigating", re.IGNORECASE)
# A court acting in a case, in wording ACTION_PATTERNS does not catch ("Court
# Denies Key Menards Motion ...", "... to Proceed to Trial"). It counts as a
# verdict, which here means "a court ruled": injunctions, appeals and contempt
# included. Checked only after agency news has been ruled out, so "EEOC Chair
# Comments on Supreme Court Rulings" stays an announcement.
COURT_RULING = re.compile(
    r"\b(?:courts?|judges?|circuit|justices?)\b.*\b(?:rejects?|allows?|agrees?|holds?|denies|denial|reverses?"
    r"|bars?|refuses?|slaps?|limits?|backs?|overturns?|speaks?|enforces?|approves?|orders?|rules?)\b"
    r"|injunction|\bcontempt\b|to (?:proceed to|face) trial|\bsanctions?\b|must turn over|\bordered to\b",
    re.IGNORECASE)
# When the headline settles nothing, the start of the teaser often does.
TEASER_ACTIONS = [(name, re.compile(p, re.IGNORECASE)) for name, p in (
    ("settled", r"will pay|agreed to (?:pay|resolve|settle)|has agreed to|\bsettle\b|\$[\d,.]+ settlement"
                r"|(?:reached|entered into) an? (?:\w+ )?(?:settlement|conciliation)"),
    ("sued", r"filed suit|charged in a (?:law)?suit|(?:law)?suit (?:it )?filed|EEOC charges\b"),
)]
# Agreements with an employer that are not about a case: the EEOC's mediation
# partnerships and outreach deals. "... Enter Mediation Partnership to Resolve
# Workplace Disputes" would otherwise read as a settlement against the company.
NOT_A_CASE = re.compile(r"mediation partnership|agreement to mediate|outreach agreement|partner to resolve"
                        r"|enter into (?:\w+ ){0,2}mediation agreement"
                        r"|memorandum of understanding|(?:national|historic) (?:\w+ )?partnership", re.IGNORECASE)
TEASER_HINT_CHARS = 400     # only the opening counts; later text is boilerplate

# EEOC headlines are formulaic. These cover the common shapes; anything else
# leaves the employer blank rather than guessing.
EMPLOYER_PATTERNS = [
    # Ends at a joining word, or at the end when the headline is only the name
    # ("EEOC Sues Standard Register Company"). (?!to\b) skips "EEOC Sues to Redress ...".
    r"^EEOC Sue[sd] (?P<name>(?!to\b).+?)(?:,? (?:for|over|on|in|under|after|alleging|citing|to)\b|$)",
    # "WAL-MART TV AD TELLS THE STORY OF ... CLAIM AGAINST THE RETAIL GIANT": the name
    # opens the headline, and "Against" is followed only by a description of it.
    r"^(?P<name>.+?)(?: Agrees to Air)? TV Ad\b",
    r"^(?P<name>.+?) Violates\b",    # "WAL-MART VIOLATES DISABILITIES ACT AGAIN; ... AGAINST RETAIL GIANT"
    # The employer is the subject and the victim follows "Against": must come
    # before the "Against X" pattern, which would otherwise store the victim.
    #   "Triborough Bridge & Tunnel Authority Discriminated Against Pregnant Female Officers ..."
    r"^(?P<name>.+?) (?:Discriminated|Retaliated) Against\b",
    #   "... EEOC Claim That Chrysler Retaliated Against Employees"
    r"\bThat (?P<name>.+?)(?:[’']s? \w+ \w+)? (?:Retaliated|Discriminated|Violated|Created|Did Not|Must)\b",
    # "Court Denies Key Menards Motion ...", "Supreme Court Denies FedEx Bid ...", "Denying United Parcel Service's Appeal"
    r"\bDen(?:ies|ying) (?:Key )?(?P<name>[^’']+?)(?:[’']s?)? (?:Petition|Bid|Motion|Appeal|Request)\b",
    r"\bEnds (?P<name>.+?) Bid\b",
    # "Judge Slaps Wal-Mart With Major Sanctions", "Court of Appeals Rules Target Must Face Trial"
    r"\b(?:Slaps|Rules) (?P<name>.+?) (?:With|Must)\b",
    # "... Subpoena in Investigation of Union Pacific", "EEOC Investigating FedEx on Charges ..."
    r"\bInvestigation of (?P<name>.+)$",
    r"^EEOC Investigating (?P<name>.+?) on\b",
    # "Aerotek Required by Federal Appeals Court to Comply ...", "Patterson UTI Drilling must Comply ..."
    r"^(?P<name>.+?)(?:,? Ordered)? (?:Required by|Must Comply|to Face Trial)\b",
    # "Henry's Turkey Service, Heirs Must Turn over ..."
    r"^(?P<name>.+?), Heirs Must\b",
    # "RACIAL HARASSMENT AND RETALIATION COSTS R.S. BRASWELL / BOBCAT OF MONROE $21,000"
    r"\bCosts? (?P<name>.+?) \$",
    # "In Agreement with EEOC, Groupon to Establish Educational Fund ..."
    r"^In (?:Agreement|Settlement) with (?:the )?EEOC, (?P<name>.+?) (?:to|will|agrees)\b",
    # "RELIEF FOR AFGHAN, MUSLIM WORKERS HARASSED AT SOLANO COUNTY CAR DEALER CHAIN"
    r"\bHarassed at (?P<name>.+)$",
    # "EEOC, Quietflex Manufacturing Company, L.P., and Others Announce Final Approval of Settlement ..."
    r"^EEOC, (?P<name>.+?),? and Others\b",
    # "Hyatt to Provide $100,000 in Pay and Benefits to Settle ...", "... Trust to Revise Apprentice Selection Process ..."
    r"^(?P<name>.+?)(?:,? (?:Ordered|Agrees|Agreed|Required))? to (?:Provide|Revise|Establish|Implement|Change|Adopt|Offer|Rehire|Reinstate)\b",
    # "EEOC Charges Dunkin' Donuts Franchisee With Sexual Harassment, Retaliation Against Teens"
    r"^EEOC Charges (?P<name>.+?) With\b",
    # "National Waste Removal Firm Admits Discrimination, Settles With EEOC For $95,000"
    r"^(?P<name>.+?) Admits\b",
    # Before the generic "X to Pay" shape, which would keep "Court Orders" in the name.
    r"^(?:Federal |Appeals )?(?:Court|Judge|Jury) Orders (?P<name>.+?) to\b",   # "... to Pay", "... to Comply"
    r"^(?P<name>.+?)(?: Is)? Sued\b",     # "X Sued by EEOC for ...", and the older "X SUED FOR ..."
    r"^(?:U\.S\. )?EEOC and (?P<name>.+?),? (?:Agree|Settle|Resolve|Reach|Enter|Conciliate|Announce|Sign)\b",
    r"^(?P<name>.+?),?(?: Voluntarily)? "
    r"(?:to Pay|Will Pay|Must Pay|Pays?(?= \$)|Pays|(?:Agrees?|Ordered|Required|Consents) to|Settles?|to Settle"
    r"|Resolves?|Charged With)\b",
    # "Court Holds Sherwood Food Distributors in Contempt ...", "Cannon & Wendt Held in Contempt ..."
    r"^(?:Federal |Appeals )?(?:Court|Judge) (?:Holds|Finds) (?P<name>.+?) (?:in Contempt|Liable|Guilty)\b",
    r"^(?P<name>.+?) (?:Held|Found) in Contempt\b",
    # "EEOC Obtains Judgment Ordering Ceviche House to Pay $130,691 ..."
    r"\b(?:Ordering|Requiring|Preventing|Barring|Prohibiting) (?P<name>.+?) (?:to|from)\b",
    # "EEOC Obtains $2.75 Million from WRS Compass for Victims of ..."
    r"\bObtains (?:\w+ ){0,3}\$[\d,.]+(?: Million)? from (?P<name>.+?)(?: (?:for|in|to|over)\b|,|$)",
    # "EEOC Releases UPS from Future Consent Decree Reporting Obligations"
    r"^EEOC Releases (?P<name>.+?) from\b",
    # Case-name headlines: "EEOC v. Activision Blizzard Claims Process is Open"
    r"\bEEOC vs?\.? (?:the )?(?P<name>.+?)(?: (?:Claims Process|Settlement|Lawsuit|Case|Trial"
    r"|Disability|Age|Sex|Race|Harassment|Discrimination|to|in|for)\b|,|$)",
    # Notices looking for more claimants in a case already filed:
    # "Job Seekers Not Hired by Radiant Services in Gardena May Have Suffered Discrimination"
    r"\b(?:Applied to|Not Hired by) (?P<name>.+?)(?: in [A-Z][\w.]+)? May Have\b",
    # "... Enforcement Action Against the City and County of X"
    r"\bAgainst (?:the )?(?P<name>.+?)(?: (?:for|over|in|to|following|after|reinforces|affirmed|ends|moves|tops|settles|requiring|on|that|can)\b|,|$)",
    # "EEOC Settles Age Suit With Commonwealth of Massachusetts"
    r"\b(?:Suit|Lawsuit|Case|Charges?|Settlement|Agreement|Decree) With (?:the )?(?P<name>.+?)"
    r"(?: (?:for|over|in|to|will)\b|,|$)",
    # "Furniture Retailer Rooms to Go Adopts Revised ... Procedures In Cooperation With The EEOC"
    r"^(?P<name>.+?) (?:Adopts|Revises|Changes|Agrees to (?:Revise|Change|Adopt))\b",
    # "... In Suit Charging Equal Pay Act Violation By Pizza Restaurant"
    r"\bViolations? by (?P<name>.+?)(?: (?:for|in|to|against)\b|,|$)",
    # "EEOC Lawsuit Challenges Sexual Harassment at Davis Typewriter Company"
    r"^EEOC (?:Lawsuit |Suit )?Challenges .+? at (?P<name>.+)$",
    # "Barenbrug USA Reaches Agreement with EEOC"
    r"^(?P<name>.+?),? (?:Reach(?:es)?|Enters?(?: Into)?|Signs?) (?:\S+ ){0,4}"
    r"(?:Agreement|Settlement|Resolution|Accord|Decree)\b",
    # "EEOC OBTAINS $127,500 SETTLEMENT FROM ATLANTIC CHEVROLET / CADILLAC FOR RACE HARASSMENT"
    r"\bSettlement From (?P<name>.+?)(?: (?:for|in|over)\b|,|$)",
    # "COURT APPROVES $1.2 MILLION SETTLEMENT BETWEEN EEOC AND MCKESSON FOR RACE DISCRIMINATION"
    r"\bBetween (?:the )?EEOC and (?P<name>.+?)(?: (?:for|in|over|to)\b|,|$)",
    # "Jury Finds Parker Drilling Liable ...", "Abercrombie & Fitch Liable for Religious Discrimination ..."
    r"^(?:Federal )?Jury (?:Finds|Says|Rules) (?P<name>.+?) (?:Liable|Must|Guilty|Violated|Discriminated)\b",
    r"^(?P<name>.+?) (?:Liable|Hit With)\b",
    # "... LAWSUIT FOR $7.1 MILLION WITH THOMSON CONSUMER ELECTRONICS AND LOCAL UNION"
    r"\$[\d,.]+(?: Million)? With (?P<name>.+?)(?: (?:for|in|over|to)\b|,|$)",
    # "St. Alexius Medical Center's Failure to Accommodate ... Draws EEOC Disability Suit"
    r"^(?P<name>.+?)[’']s? (?:Failure|Refusal|Rehire Policy|Firing|Treatment)\b",
    # "EEOC Wins Jury Verdict of $458,000 for Two Older Workers Fired by AZ Metro Distributors"
    r"\b(?:Fired|Terminated|Laid Off|Rejected|Underpaid) by (?P<name>.+?)"
    r"(?: (?:for|in|because|after|over|to)\b|,|$)",
    # "North Dakota Employer Harassed Worker Because of His Sexual Orientation, EEOC Charges"
    # The lookahead skips passives about the victim ("Muslim Pilot Fired Due to Religion ...").
    r"^(?P<name>.+?)(?: Unlawfully| Illegally)? (?:Harassed|Fired(?! (?:Due|Because|For|After|By)\b)|Failed|Refused|Discriminated|Retaliated|Denied|Paid|Subjected"
    r"|Violated|Forced|Terminated|Rejected|Demoted|Punished|Allowed|Permitted|Tolerated|Ignored)\b"
    r".*,? EEOC (?:Charges|Charged|Says|Said|Alleges|Claims)\b",
    # Last, so it only fires when nothing above matched. The "EEOC and X ..."
    # headline with the employer first: "MedStar Good Samaritan Hospital and EEOC Reach ..."
    r"^(?P<name>.+?),? and (?:the )?(?:U\.S\. )?EEOC (?:Agree|Settle|Resolve|Reach|Enter|Conciliate|Announce|Sign)\b",
]
EMPLOYER_REGEXES = [re.compile(p, re.IGNORECASE) for p in EMPLOYER_PATTERNS]

# A headline "name" ending in one of these may be a description standing in
# for the real employer ("Georgia Car Dealership", "Two Employers"). On its own
# that proves nothing ("Georgia Power Company" is real), so classify() also
# requires the description to be echoed in lower case in the teaser.
GENERIC_NAME = re.compile(
    r"\b(?:Compan(?:y|ies)|Hospital|Center|Agency|Firm|Chain|Provider|Restaurant|Diner|Retailer|Dealer|Dealership"
    r"|Manufacturer|Contractor|Franchisee?|Franchisor|Operator|Owner|Facility|Employer|Business(?:es)?"
    r"|Store|Hotel|Resort|Farm|Grower|Plant|Club|Nightclub|Bar|School|District|Home|Practice|Clinic"
    r"|Venue|Shop|Market|Supplier|Distributor|Wholesaler|Recruiter|Non-?Profit|Organization|Subsidiary"
    r"|Affiliate|Giant|Maker|Processor|Cleaners?|Lodge)s?$",
    re.IGNORECASE)
# Openings that are never part of a name: counts and vague sizes.
GENERIC_START = re.compile(
    r"^(?:\d+|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Several|Multiple|Major|National|Nationwide"
    r"|Local|Large|Largest|Former|Owners?|Operators?) ", re.IGNORECASE)
# Teaser openings that aren't an employer: the EEOC itself, "Today, ...", a date,
# or a phrase cut off at a dangling word ("The San Francisco District of").
NOT_A_NAME = re.compile(
    r"EEOC|Equal Employment|^Commission\b|Justice Department|^Federal Agenc|^(?:Federal )?(?:Court|Judge|Jury)\b"
    r"|\bJudge\b|^On \w+\.? \d|^On \w+day\b"
    r"|^(?:Today|Yesterday|Over|Under|In|On|At|As|Since|During|After|Following|This|For|The|A|An|Whereas"
    r"|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Several)$"
    r"|\b(?:of|for|in|to|by|at|and|the|with)$"
    # the people a case is about, not who it is against
    r"|(?i:\b(?:Employees?|Mineworkers?|Applicants?|Victims?|Women|Individuals|Farm ?Workers|Job Seekers|Pilot|Manager|Teens)$)"
    r"|^(?:Overturning|Rejecting|Citing|By|Upon|Agency)\b"
    # a dollar figure, a bare topic, or a sentence about someone being fired
    r"|^\$|(?i:^(?:Harassment|Discrimination|Retaliation|Bias)$)|(?i:\bFired\b)")
# Extra rejections for names taken from the teaser only. A headline can name a
# court or a district as the employer ("EEOC Sues Allegheny County Court"); the
# teaser's opening words mentioning one are usually just the sentence's subject.
TEASER_NOT_A_NAME = re.compile(
    r"\bCourt\b|Supreme|Commission|\bChair(?:man|woman)?\b|Counsel\b|White House|\bDistrict$"
    r"|Experts|Employees|Workers|Applicants"
    r"|^(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Several|Some|Many)\b", re.IGNORECASE)
# Words allowed in lower case inside a real name ("Bank of America", "dba").
# Any other lower-case word means a sentence leaked in ("has been chosen as").
NAME_SMALL_WORDS = {"of", "and", "the", "for", "at", "in", "on", "by", "de", "la", "del", "y", "dba", "d/b/a"}

# The teaser's first sentence names the employer even when the headline doesn't:
#   "LOUISVILLE, Ky. — Jaco Enterprises, L.L.C., a transportation company ..."
#   "The City of O'Fallon, Illinois, which provides ..."
# Optional dateline, then the name, ending at whichever comes first: a legal
# suffix (", Inc."), a describing clause (", a ...", ", which ...") or a verb.
TEASER_EMPLOYER = re.compile(
    r"^(?:.{2,40}?\s(?:—|–|--|-)\s)?"       # dateline: "LOUISVILLE, Ky. — ", "DENVER - "
    r"(?P<name>[A-Z].{1,80}?)"
    r"(?:,? (?:Inc\.?|L\.?L\.?C\.?|Corp\.?|Co\.|Ltd\.?|L\.?P\.?)(?=[,\s])"
    # "the" does not end the name after a joining word: "Bank of the West", "Joe & the Juice"
    r"|,? (?:an?|(?<!\bof )(?<!\bin )(?<!\band )(?<!& )the|which|one of|operators?|owners?|franchis(?:ors?|ees?)|doing business as|d/b/a)\b"
    r"| (?:violated|agreed|will pay|has agreed|reached|unlawfully|discriminated|fired|refused)\b)"
)

# When the first sentence only describes the employer ("A Louisiana restaurant
# admitted ..."), the name often opens a later sentence: "Bourne's House, LLC,
# doing business as ...". Only a name followed by a legal suffix is trusted here,
# since later sentences also start with people, places and agencies. Two words
# minimum: a lone word before "Inc." is usually the tail of a longer name.
LATER_EMPLOYER = re.compile(
    r"(?<=[.!?”\"] )(?P<name>[A-Z][\w’'&\-]*(?: [\w’'&\-]+){1,6}?),? "
    r"(?:Inc\.?|L\.?L\.?C\.?|Corp\.?|Co\.|Ltd\.?|L\.?P\.?)(?=[,\s])")

# "Carmel restaurants owned and operated by JCFB, Inc. agreed to pay ...": the
# sentence opens with a description and names the company after "owned by".
# The name is the run of capitalised words that follows.
OWNED_BY = re.compile(
    r"\b(?:owned|operated|run|managed)(?: and \w+)? by (?P<name>[A-Z][\w’'&.\-]*(?: [A-Z&][\w’'&.\-]*){0,5})")

# "The EEOC had charged Wood River, Neb.-based Heritage Bank with paying ...":
# the name follows "charged", after an optional "<place>-based".
CHARGED = re.compile(
    r"\b(?:EEOC|agency|Commission)(?: had| has)? (?:charged|sued) (?:that )?(?:[A-Z][\w .,]{1,30}?-based )?"
    r"(?P<name>[A-Z][\w’'&.\-]*(?: [A-Z&][\w’'&.\-]*){0,5}) (?:with|for|violated|discriminated|fired|failed)\b")
# "... in a case the EEOC filed against Hobson Bearing International, Inc., of ..."
FILED_AGAINST = re.compile(
    r"\bfiled (?:\w+ ){0,3}against (?:the )?(?P<name>[A-Z][\w’'&.\-]*(?: [A-Z&][\w’'&.\-]*){0,5})")

# "$1.55 Million", "$2 billion", "$100K" (the K only when it touches the number)
AMOUNT = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)(?:\s*(million|billion)|(k)\b)?", re.IGNORECASE)
NAME_NOISE = {"inc", "incorporated", "llc", "corp", "corporation", "co",
              "company", "ltd", "lp", "llp", "the"}


def employer_key(name: str) -> str:
    """Collapse name variants to one key: 'Wal-Mart Stores, Inc.' -> 'walmart stores'."""
    # "&" reads as "and". A slash separates two names ("Olive Garden/GMRI") and
    # becomes a space, except in "d/b/a", which stays one word.
    # Accented letters lose the accent, not the letter: "Señor Frog's" -> "senor frogs".
    name = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    name = name.lower().replace("d/b/a", "dba").replace("&", " and ").replace("/", " ")
    words = re.sub(r"[^a-z0-9 ]", "", name).split()
    return " ".join(w for w in words if w not in NAME_NOISE)


def parse_amount(title: str) -> int | None:
    """First dollar figure in the title, in whole dollars: '$1.55 Million' -> 1550000, '$100K' -> 100000."""
    match = AMOUNT.search(title)
    if not match:
        return None
    unit = (match.group(2) or match.group(3) or "").lower()
    scale = {"k": 1_000, "million": 1_000_000, "billion": 1_000_000_000}.get(unit, 1)
    return int(float(match.group(1).replace(",", "")) * scale)


def clean_teaser_name(name: str) -> str:
    """Turn the teaser's opening words into an employer name, or "" if they aren't one.

    The teaser regex returns whatever precedes the first verb, which is often
    more than the name. Three shapes are handled:
      "Dallas-based Tenet Healthcare"            -> "Tenet Healthcare"
      "Multinational retailer Walmart"           -> "Walmart"   (describing lead-in)
      "Atlantic Property Corp and its affiliate" -> "Atlantic Property Corp"
    """
    words = name.split()
    # Cut through a location lead-in: "Las Vegas, Nev.-headquartered Golden ..."
    for i in range(len(words) - 1, -1, -1):
        if re.search(r"-(?:based|area|headquartered),?$", words[i], re.IGNORECASE):
            words = words[i + 1:]
            break
    # Ordinary lower-case words mark where the name stops or starts.
    lows = [i for i, w in enumerate(words) if w[0].islower() and w not in NAME_SMALL_WORDS]
    if lows and lows[0] >= 2:
        words = words[:lows[0]]             # name first, then a sentence: keep the name
    elif lows:
        words = words[lows[-1] + 1:]        # description first: the name is what follows
        if words and words[0] in NAME_SMALL_WORDS:
            words = []                      # "... restaurants in Mich": a leftover, not a name
    while words and words[-1].strip(",") in NAME_SMALL_WORDS:
        words.pop()                         # no dangling "and" / "of"
    name = " ".join(words).strip(" ,(")
    if not name or NOT_A_NAME.search(name) or TEASER_NOT_A_NAME.search(name):
        return ""
    return name


# "Frozen Food Giant Schwan's", "Trucking Company YRC", "National Staffing Agency
# BaronHR": a describing lead-in, then the real name. The lead-in ends in one of
# these nouns and the name must start with a capital or a quote mark.
LEAD_IN = re.compile(
    r"^(?:(?![Aa]nd\b|AND\b)[\w.,-]+ ){0,4}?(?:Giant|Company|Provider|Agency|Retailer|Lender|Contractor|Maker|Chain|Firm|Processor"
    r"|Manufacturer|Distributor|Franchisee|Operator|Grower|Dealer|Dealership|Subcontractor) "
    r"(?P<rest>[A-Z‘“'\"].+)$")
NOT_A_REST = re.compile(r"^(?:Inc|LLC|L\.L\.C|Corp|Co|Ltd|LP|Of|And|In|For|To|At|D/B/A|Sued|Settles?|Pays?|Will|Agrees?|Admits|That|Who|Which)\b",
                        re.IGNORECASE)


def without_lead_in(name: str, teaser: str) -> str:
    """Drop a describing lead-in from a headline name: 'Pancake Chain IHOP' -> 'IHOP'.

    Left alone when the teaser repeats the whole thing, because then it is the
    real name: 'Coca-Cola Bottling Company United, Inc.'
    """
    m = LEAD_IN.match(name)
    if (m and name not in teaser and not NOT_A_REST.match(m.group("rest"))
            and not GENERIC_NAME.search(m.group("rest"))):
        return m.group("rest").strip(" '‘’“”\"")
    return name


def looks_generic(name: str, teaser: str) -> bool | None:
    """Is a headline 'name' ending in a generic noun a description, not a name?

    True  = description: "HOUSTON RESTAURANT" where the teaser says "a Houston
            restaurant", or a count like "Two Employers".
    False = real name: the teaser repeats it with capitals ("JPMorgan Chase Bank").
    None  = can't tell from the text ("Georgia Power Company", never repeated).
    """
    found = re.search(re.escape(name), teaser, re.IGNORECASE)
    if found:
        return found.group(0).split()[-1][0].islower()
    return True if GENERIC_START.match(name) else None


# Marks a headline that names more than one employer: "Cardinal Health and
# AppleOne", "Olive Garden/GMRI Inc.". Checked against what the headline name
# has besides the teaser's name.
SECOND_NAME = re.compile(r"(?:^|\s)(?:and|&)\s|/", re.IGNORECASE)
CP1252_QUOTES = {0x91: "'", 0x92: "'", 0x93: '"', 0x94: '"', 0x96: "-", 0x97: "-"}


def classify(title: str, teaser: str) -> dict:
    """Everything derived from the text: tags, action type, amount, employer."""
    # Decode leftovers like "&#39;" and collapse doubled spaces first: some
    # headlines have both, and the patterns expect plain single-spaced text.
    title, teaser = " ".join(unescape(title).split()), " ".join(unescape(teaser).split())
    # Old archive copies use Windows-1252 control codes for curly quotes.
    title, teaser = title.translate(CP1252_QUOTES), teaser.translate(CP1252_QUOTES)
    title = re.sub(r"\bEECO\b", "EEOC", title)      # the EEOC has misspelled itself in a headline
    text = f"{title} {without_law_boilerplate(teaser)}"     # tags only; the headline is never trimmed
    tags = [tag for tag, regex in TAG_REGEXES.items() if regex.search(text)]
    action = next((name for name, regex in ACTION_REGEXES if regex.search(title)), "")
    strong = len(SPANISH_STRONG.findall(title))
    if strong and strong + len(SPANISH_WEAK.findall(title)) >= 3:
        action, tags = "translation", []    # a repeat of an English release: no tags, no employer
    elif NOT_A_CASE.search(title):
        action = "announcement"
    elif INVESTIGATION.search(title):
        action = "investigation"
    if not action and not AGENCY_NEWS.search(title):
        if COURT_RULING.search(title):
            action = "verdict"
        else:   # nothing in the headline: let the opening of the teaser decide, if it can
            action = next((name for name, regex in TEASER_ACTIONS if regex.search(teaser[:TEASER_HINT_CHARS])), "")
    if not action and (AGENCY_NEWS.search(title) or not (
            TITLE_CASE_HINT.search(title) or TEASER_CASE_HINT.search(teaser[:TEASER_HINT_CHARS]))):
        action = "announcement"
    # First headline pattern that yields a usable name. A non-name ("EEOC" from
    # "EEOC Settles Suit Against X") is skipped so a later pattern can find X.
    employer = ""
    for regex in EMPLOYER_REGEXES:
        m = regex.search(title)
        if m and not NOT_A_NAME.search(m.group("name").strip()):
            employer = without_lead_in(m.group("name").strip(), teaser)
            break
    # The teaser's first sentence usually leads with the employer's legal name.
    m = TEASER_EMPLOYER.search(teaser)
    raw_teaser_name = m.group("name").strip(" ,") if m else ""
    unnamed = raw_teaser_name.startswith(("A ", "An "))     # "A large healthcare provider ..."
    teaser_name = "" if unnamed else clean_teaser_name(raw_teaser_name)

    description = ""        # the headline's stand-in for a name, kept as a last resort
    if employer:
        # The headline name wins, because it carries the brand people know
        # ("Design Cuisine") where the teaser leads with the legal entity
        # ("National Food Enterprises"). Two exceptions. The first is a headline
        # name that is the teaser's name plus extra words, unless the extra is
        # a second employer, which must not be dropped.
        if (teaser_name and teaser_name in employer and employer not in teaser
                and not SECOND_NAME.search(employer.replace(teaser_name, "", 1))):
            employer = teaser_name      # "International Logistics Company Exel" -> "Exel"
        elif GENERIC_NAME.search(employer):
            generic = looks_generic(employer, teaser)
            if generic is False:
                pass                    # confirmed real name, keep it
            elif teaser_name:
                employer = teaser_name  # "Warehouse Logistics Company" -> "Birchstone Management"
            elif generic:
                # A description ("Kansas School District"), not a name. Set it
                # aside and keep looking for the real name below.
                description, employer = employer, ""
    elif action not in NO_EMPLOYER_TYPES:
        # No name in the headline. The teaser's opening words are only trusted
        # for releases about a case; agency news has no employer.
        employer = teaser_name
    if not employer and action not in NO_EMPLOYER_TYPES:
        # Still nothing: a company named after "owned by", "filed against" or "the EEOC charged",
        # else a legally-named company opening a later sentence.
        m = (OWNED_BY.search(teaser) or FILED_AGAINST.search(teaser) or CHARGED.search(teaser)
             or LATER_EMPLOYER.search(teaser))
        if m:
            # The name can run to the end of its sentence: drop that full stop,
            # but not the one in "L.L.C." or "U.S.".
            employer = clean_teaser_name(re.sub(r"(?<=[a-z])\.$", "", m.group("name")))
    if not employer and not description and unnamed and action not in NO_EMPLOYER_TYPES:
        # The headline gave nothing and the teaser opens "A Steamboat Springs,
        # Colo., restaurant has agreed ...": use those words, minus the "A".
        words = raw_teaser_name.split(" ", 1)[1]
        # Only when they end in a business noun ("... restaurant", "... manufacturer"):
        # other "A ..." openings are about a judge or a jury, not an employer.
        if len(words.split()) <= 8 and GENERIC_NAME.search(words):
            description = words
    if not employer:
        # No real name anywhere in the stored text, so use the headline's
        # description. It is vague, but it says the release names nobody and
        # keeps the row out of the "no employer name" review list.
        employer = description
    if action in NO_EMPLOYER_TYPES:
        employer = ""       # whatever the patterns picked up, it is not an employer
    return {
        "tags": tags,       # a real list, stored as JSON: ["age", "retaliation"]
        "action_type": action,
        "amount": parse_amount(title),
        "employer_raw": employer[:300],
        "employer_key": employer_key(employer)[:300],
    }
