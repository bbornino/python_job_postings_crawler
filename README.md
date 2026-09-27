# Python Job Postings Crawler

A Claude-powered pipeline that researches companies and scores how well each one fits a configurable set of job-search criteria. It is the first stage of a larger crawler: vet companies first, then pull and analyze job postings only from the companies worth pursuing.

Each company gets one Claude API call. Claude searches the web for current information, then submits its findings through a structured tool call, so every result comes back in the same shape with a short, cited reason behind each score.

## How it works

1. `vet_companies.py` loads any companies already vetted from `vetted_companies.jsonl` and skips them.
2. The remaining companies are vetted in parallel (4 at a time) by `analyze_company.py`.
3. For each company, Claude runs a handful of web searches (capped per company), then calls the `submit_company_vetting` tool. The tool's input is the vetting record.
4. Each record is appended to `vetted_companies.jsonl` as soon as it finishes, so a crash or failure partway through a batch loses nothing that already completed.

A few design choices worth calling out:

- **Structured output through tool use.** The response is constrained to a JSON schema rather than asking the model to "please return JSON."
- **Server-side web search.** Anthropic runs the searches inside the same API call, so there is no agent loop to manage in this code. Scores are based on current information, not the model's training data.
- **Prompt caching.** The vetting prompt is identical on every call, so it is cached, which cuts cost and latency across a batch.
- **Prompts live in Markdown.** Prompts are loaded from `.md` files at runtime instead of being embedded as Python strings, so they stay readable and diff cleanly.
- **The model returns values, not totals.** Claude scores each criterion individually. Weights and the overall fit score belong in code, not in the model's arithmetic (weighted scoring is planned).

## Files

| File | Purpose |
|---|---|
| `vet_companies.py` | Batch runner: skips already-vetted companies, vets the rest in parallel, saves results |
| `analyze_company.py` | Vets a single company; can also be run on its own as a test bench |
| `prompt_loader.py` | Loads prompt (`.md`) and tool schema (`.json`) files from the project folder |
| `greenhouse.py` | Greenhouse job board API helpers for the job-posting stage |
| `company_vetting_prompt.example.md` | Genericized sample of the vetting prompt, showing its structure and scoring pattern |
| `company_vetting_tool_schema.example.json` | Genericized sample of the tool schema that defines each vetting record |
| `.env.example` | Template for the environment variables the scripts read |
| `requirements.txt` | Python dependencies |

### Private files (gitignored)

The real configuration holds personal job-search criteria, so it stays out of version control. The committed `.example` files demonstrate the same architecture with placeholder criteria.

| File | What it holds |
|---|---|
| `.env` | API key and model settings |
| `company_vetting_prompt.md` | The real vetting prompt, with personal criteria and weights |
| `company_vetting_tool_schema.json` | The real tool schema; its field names mirror the private criteria |
| `companies.csv` | The personal list of companies to vet |
| `vetted_companies.jsonl` | Vetting results, one JSON record per line |

## Setup

Requires Python 3.12+ and an Anthropic API key.

```bash
python -m pip install -r requirements.txt
```

Create your private files from the examples:

```bash
cp .env.example .env
cp company_vetting_prompt.example.md company_vetting_prompt.md
cp company_vetting_tool_schema.example.json company_vetting_tool_schema.json
```

Add your API key to `.env`. Then edit the prompt to set your own criteria and weights, and update the schema's scoring fields to match.

## Usage

Vet a batch of companies:

```bash
python vet_companies.py
```

Vet a single company without touching the results file (useful for prompt tuning):

```bash
python analyze_company.py Figma
python analyze_company.py "Scale AI"
```

## Cost and performance

A typical company takes about 55–60 seconds and a few web searches. Most input tokens are search results, which are cached within each call. Running 4 companies in parallel keeps a batch at roughly one minute per four companies while staying well under API rate limits.

## Roadmap

- Read the company list from `companies.csv` instead of the hardcoded list
- Compute weighted fit scores in code from each record's values
- Job-posting stage: pull postings from Greenhouse for companies that pass vetting, then analyze each posting
- Move results from JSONL into a database with a web front end
- Run nightly on AWS (EventBridge Scheduler triggering Lambda)
