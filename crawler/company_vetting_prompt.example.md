# Company Vetting Subagent (Sample)

This is a genericized reference version of the company-vetting prompt actually used by the pipeline. The real prompt is configured with the specific criteria that matter to its user and is excluded from version control; this sample demonstrates the architecture and scoring pattern without exposing that configuration.

**Purpose:** Given a single company name, research it and return a weighted fit score against a configurable rubric.

**This doc is one API call, one company.** Each invocation is stateless — there is no "session." Reference data (jurisdiction/regulatory lists, industry recognition lists, whatever a given configuration needs) is attached to every call by the orchestrating script, refreshed on its own schedule outside this prompt. This subagent never fetches or verifies that data itself.

**No condition here stops research partway through.** A company that fails badly on some criterion still gets a fully documented, low score on that point — not an early exit. This keeps every score auditable: you can always see *why* a company scored low, not just that it did.

**Weights are tiered by actual stakes to the person configuring this, not normalized to a round number.** Ceiling is whatever the configured weights sum to — since the harness selects by rank across a batch rather than comparing to a fixed threshold, the exact ceiling has zero functional effect. Never bend weights to chase a round number.

**Every scored value is one of the specific, listed tiers — never interpolate between them or invent an in-between number.** If evidence sits ambiguously between two tiers, pick the lower one.

---

## Compute Budget

Target: process a large batch of companies without excessive token spend, by not re-fetching what's either static reference data or already available elsewhere in the pipeline.

- **Provided as input, never fetched by this subagent:** any static reference lists the configuration depends on (e.g. regulatory-risk data, industry recognition/certification lists).
- **Already in hand:** if an earlier pipeline stage already collected raw source material (postings, listings, filings), read from that rather than re-fetching it.
- **Per company, budget a small, fixed number of searches/fetches** — a primary source page (covers several fields in one pull) plus one consolidated search for anything time-sensitive (funding, layoffs, legal history). If a field isn't found within that budget, mark it `[UNKNOWN]` and move on rather than searching further.

---

## Step 1: Research

Every field is a short, self-contained phrase — readable on sight, no coded enums. If a field can't be found, mark it `[UNKNOWN]` explicitly — never leave it blank, never default to neutral or positive without a stated reason.

**[COMPANY SNAPSHOT]** — example fields (a real configuration lists its own):
- **Synopsis (3–6 sentences):** what the company actually does, its product, the problem it solves, and what kind of day-to-day work that implies.
- **Reference links:** company site, review-site profile, professional-network profile — link only, never a scraped rating (ratings drift; links let a later process re-resolve the current value).
- **Location/jurisdiction:** feeds any jurisdiction-risk or commute-fit scoring.
- **Size, funding/stability signal, hiring activity** (open roles, recent layoffs — note the *scale* of any layoff, not just that one occurred).
- Whatever criteria a specific configuration cares about — the pattern is the same regardless of the specific list: state what's found, cite where it came from, and never assume a fact that wasn't actually found.

---

## Step 2: Weighted Scoring

**Weight tiers (illustrative — a real configuration sets its own):**
- **3** (critical — the biggest determinants of fit)
- **2** (meaningful, but not existential)
- **1** (minor)
- **0.5** (soft positioning signals)

| # | Point (example) | Wt | 1.0 | Partial | 0.0 | `[UNKNOWN]` default |
|---|---|---|---|---|---|---|
| 1 | Location/logistics fit | 3 | Fully remote / no constraint | **0.8 / 0.6 / 0.4** graduated partial tiers based on configured preference | Fails the configured constraint entirely | 0.0 — usually findable; treat unresolved conservatively |
| 2 | Career-path flexibility | 2 | Explicit supporting program/language found | **0.5** general supportive language, no formal program | No evidence found | 0.0 — costless to state if true, so silence is informative |
| 3 | Culture/inclusion signal | 3 | Strong evidence from an independent, costly-to-obtain recognition source (e.g. a third-party certification/ranking) plus a specific stated policy | **0.5** no information found either way — genuinely neutral, since obtaining that recognition requires active participation many companies never pursue | Documented negative evidence | **0.5 — neutral, not a penalty** (see note below) |
| 4 | Jurisdiction/regulatory risk | 3 | No meaningful risk at the specific location (check the specific city/office when regional variance exists, not just a blanket regional rating) | **0.2** elevated but below the hard-exclusion threshold | Meets the hard-exclusion threshold for the configured criterion | 0.0 — location is usually public |
| 5 | Engineering/tooling culture alignment | 0.5 | Deep, *cited* evidence (a specific post, named tool, or testimonial) | **0.5** passing mention, source cited | No mention, or no source beyond company identity/industry | 0.0 — a company's product/industry is never itself evidence about its internal practices |
| 6 | Compliance/credential requirement | 3 | Not required, or already held | — | Required, not held | **1.0 — no mention found is itself evidence of no requirement**, since a real requirement is almost always stated prominently |
| 7 | Hiring health | 3 | Strong positive evidence of genuine, active hiring | **0.5** uncertain, no red flags | Red flags present (ghost-posting patterns, or a significant recent reduction in force while still posting roles) | 0.5 — uncertain default |
| 8 | Inclusive hiring practice | 2 | Confirmed via an independent recognition source AND no negative language found | **0.7 / 0.3** graduated partial tiers | Negative evidence found | 0.0 — matches whatever base rate the configuration's own research has shown |
| 9 | Interview methodology | 2 | Confirmed practical/real-world evaluation | **0.5** mixed or undocumented | Confirmed to rely on a method the configuration disfavors | **0.5 — neutral; often undocumented, especially for smaller companies** |
| 10 | Skill/stack transferability | 2 | Mainstream, general-purpose skillset used for general-purpose work | **0.5** unfamiliar-but-not-locked-in, or a mainstream skillset used for deeply specialized work that isn't really an easy on-ramp | A skillset/ecosystem historically associated with requiring long specific tenure | 0.5 — neutral if simply not found |
| 11 | Historical outcome with this company | 1 | No unfavorable history on record | **graduated** partial tiers by count | Meets the configured "too many" threshold | Treat "no record found" as the best tier — this isn't really unknown, it's an absence of a negative record |
| 12 | Credential/pedigree gatekeeping | 0.5 | No concrete gatekeeping evidence — pass/fail. **Measures specifically credential-based gatekeeping, not general hiring difficulty.** A company can be extremely selective on merit alone without this applying. | — | Concrete pedigree-specific evidence found | 1.0 — no signal defaults to pass |
| 13 | Growth/mentorship culture | 0.5 | Documented formal program | **0.5** general culture language, no formal program | No evidence found | 0.0 — costless to state if true |
| 14 | Public values alignment | 3 | Documented public stance consistent with the configured values, taken under real pressure/controversy | **0.5** general/passive support, or no test case has arisen — neutral, most companies are never tested | Documented capitulation/silence during an active controversy where peers spoke up | **0.5 — neutral**, same reasoning as row 3 |

**Note on neutral-default rows:** most rows default to 0.0 on silence, because stating a supportive policy is usually costless if true — so silence is informative. A few rows (culture/inclusion signal, interview methodology, public values alignment) default to neutral 0.5 instead, because the *evidence itself* (independent certification, documented interview process, a real test-of-values event) requires something costly or rare to exist at all — silence there means "unmeasured," not "absent." Get this distinction right per point; it materially changes what a score means.

**Note on separating passive vs. active signal:** where a configuration cares about both routine policy compliance and active public stances taken under real pressure, keep these as separate scored points rather than folding them into one ceiling — the latter is a rarer, more revealing signal and deserves its own weight.

`fit_score` = Σ(weight × value) across all configured points. The ceiling is whatever the configured weights sum to.

---

## Step 3: Record Output

**Invocation mechanism:** called via the Anthropic API using **tool use** (forced function-calling), not a freeform prompt asking for JSON — the response is mechanically constrained to the defined schema, not merely instructed to follow it.

**The model never outputs `weight` or `fit_score`.** Weights are fixed and known to the calling script; the script computes `fit_score` itself, in code, every time. This removes an entire class of arithmetic error from the pipeline.

```json
{
  "company": "",
  "checked_on": "YYYY-MM-DD",
  "synopsis": "",
  "links": { "company_url": "", "review_site_url": "" },

  "scoring": {
    "point_1": { "value": 0.0, "reason": "" },
    "point_2": { "value": 0.0, "reason": "" }
  }
}
```

### Worked example (placeholder company)

```json
{
  "company": "Example Corp",
  "checked_on": "2026-09-27",
  "synopsis": "A mid-size B2B SaaS company selling inventory-management software to regional retailers.",
  "scoring": {
    "location_fit":      { "value": 1.0, "reason": "Fully remote postings, no RTO mandate found" },
    "hiring_health":      { "value": 0.5, "reason": "Open roles present but no recent funding/growth signal found; uncertain default" }
  }
}
```
Harness computes `fit_score` from this against its own configured weights table.
