# Python Job Postings Crawler

A Claude-powered pipeline that researches companies and scores how well each one fits a configurable set of job-search criteria. It is the first stage of a larger crawler: vet companies first, then pull and analyze job postings only from the companies worth pursuing.

Each company gets one Claude API call. Claude searches the web for current information, then submits its findings through a structured tool call, so every result comes back in the same shape with a short, cited reason behind each score.

The project is a headless Django app: no web server or views, just Django's ORM, migrations, admin, and management commands. The `crawler` app is self-contained so it can later be dropped into the Job App Tracker project, which will provide the GUI for the data generated here.

## How it works

1. `vet_companies.py` loads any companies already vetted from `vetted_companies.jsonl` and skips them (matching is case-insensitive, so "AirBnB" matches a stored "Airbnb").
2. The remaining companies are vetted in parallel (4 at a time) by `analyze_company.py`.
3. For each company, Claude runs a handful of web searches (capped per company), then calls the `submit_company_vetting` tool. The tool's input is the vetting record.
4. Each record is appended to `vetted_companies.jsonl` as soon as it finishes, so a crash or failure partway through a batch loses nothing that already completed.

The JSONL results file is a stand-in while the database models are built (see Roadmap).

A few design choices worth calling out:

- **Structured output through tool use.** The response is constrained to a JSON schema rather than asking the model to "please return JSON."
- **Server-side web search.** Anthropic runs the searches inside the same API call, so there is no agent loop to manage in this code. Scores are based on current information, not the model's training data.
- **Prompt caching.** The vetting prompt is identical on every call, so it is cached, which cuts cost and latency across a batch.
- **Prompts live in Markdown.** Prompts are loaded from `.md` files at runtime instead of being embedded as Python strings, so they stay readable and diff cleanly.
- **The model returns values, not totals.** Claude scores each criterion individually. Weights and the overall fit score belong in code, not in the model's arithmetic (weighted scoring is planned).
- **Small, single-purpose commands.** Each pipeline step will be its own management command, so steps can run independently locally and later as separate AWS Lambda invocations.

## Project layout

| Path | Purpose |
|---|---|
| `manage.py` | Django entry point |
| `config/` | Django project settings; reads configuration from `.env` |
| `crawler/` | The Django app holding all crawler logic |
| `crawler/vet_companies.py` | Batch runner: skips already-vetted companies, vets the rest in parallel, saves results |
| `crawler/analyze_company.py` | Vets a single company; can also be run on its own as a test bench |
| `crawler/prompt_loader.py` | Loads prompt (`.md`) and tool schema (`.json`) files from the `crawler/` folder |
| `crawler/greenhouse.py` | Greenhouse job board API helpers for the job-posting stage |
| `crawler/company_vetting_prompt.example.md` | Genericized sample of the vetting prompt, showing its structure and scoring pattern |
| `crawler/company_vetting_tool_schema.example.json` | Genericized sample of the tool schema that defines each vetting record |
| `pyproject.toml` / `uv.lock` | Dependencies, managed with [uv](https://docs.astral.sh/uv/) |
| `.env.example` | Template for the environment variables the project reads |

### Private files (gitignored)

The real configuration holds personal job-search criteria, so it stays out of version control. The committed `.example` files demonstrate the same architecture with placeholder criteria.

| File | What it holds |
|---|---|
| `.env` | API key, Django secret key, database settings |
| `crawler/company_vetting_prompt.md` | The real vetting prompt, with personal criteria and weights |
| `crawler/company_vetting_tool_schema.json` | The real tool schema; its field names mirror the private criteria |
| `crawler/companies.csv` | The personal list of companies to vet (exchanged with Claude Cowork) |
| `crawler/vetted_companies.jsonl` | Vetting results, one JSON record per line |

## Setup

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), MariaDB, and an Anthropic API key.

Install dependencies and activate the virtual environment:

```bash
uv sync
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
source .venv/bin/activate         # macOS/Linux
```

Create your private files from the examples:

```bash
cp .env.example .env
cp crawler/company_vetting_prompt.example.md crawler/company_vetting_prompt.md
cp crawler/company_vetting_tool_schema.example.json crawler/company_vetting_tool_schema.json
```

Fill in `.env`: your Anthropic API key, a Django `SECRET_KEY`, and the `DB_*` settings. Generate a secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Create the database and run migrations:

```sql
CREATE DATABASE job_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```bash
python manage.py migrate
```

Then edit the prompt to set your own criteria and weights, and update the schema's scoring fields to match.

## Usage

Run everything from the repo root.

Vet a batch of companies:

```bash
python -m crawler.vet_companies
```

Vet a single company without touching the results file (useful for prompt tuning):

```bash
python -m crawler.analyze_company Figma
python -m crawler.analyze_company "Scale AI"
```

## Cost and performance

A typical company takes about 55–60 seconds and a few web searches. Most input tokens are search results, which are cached within each call. Running 4 companies in parallel keeps a batch at roughly one minute per four companies while staying well under API rate limits.

## Roadmap

- Database models (`Company`, `CrawledPosting`) on MariaDB, replacing the JSONL results file; Django admin as the interim viewer
- Management commands, one per pipeline step:
  - `import_companies`: Claude Cowork's CSV → `Company` rows
  - `vet_companies`: vet companies not yet vetted, with `--limit` and `--time-budget` throttles so a run fits inside a Lambda invocation and resumes where it left off
  - `export_companies`: regenerate the CSV for Cowork, including the "already vetted" list
  - `crawl_boards`: pull postings from Greenhouse (and other ATS boards) for vetted companies
  - `email_digest`: email ranked, not-yet-sent postings
- Compute weighted fit scores in code from each record's values
- Plug the `crawler` app into the Job App Tracker project, which provides the GUI; crawled postings get "promoted" into tracked applications
- Run nightly on AWS (EventBridge Scheduler triggering Lambda, container image deployment)
