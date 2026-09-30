"""python manage.py vet_new_companies:
collect new companies, merge with the DB, vet a throttled batch.

Common commands:
python manage.py vet_new_companies
python manage.py vet_new_companies --limit 3
python manage.py vet_new_companies --help

Caveat: command-line names currently always fail vetting, since they carry no
ats/board_token and vet_companies rejects companies missing either. Use --csv.
"""
import csv
from pathlib import Path
from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from crawler.vet_companies import vet_companies
from crawler.models import Company

# Job boards/aggregators or unknowns: no crawlable company board, so don't vet.
IGNORED_ATS = {"linkedin", "indeed", "unknown", "dice", "phenom", "custom / in house"}

# Cowork's headers -> our field names. Change here if the export's headers change.
CSV_COLUMNS = {"Company Name": "name", "ATS Name": "ats", "ATS board name": "board_token"}

def read_csv(csv_path: Path) -> list[dict]:
    """Read Cowork's CSV into [{name, ats, board_token}].
 
    Skips rows with no name, no board token, or an ignored ATS, so every
    returned row is crawlable. Duplicate names are not removed here; the
    unique name column catches them at save time.
 
    Raises:
        CommandError: file missing, or a required column is absent.
    """
    if not csv_path.exists():
        raise CommandError(f"CSV not found: {csv_path}")

    # utf-8-sig strips the BOM Excel adds when saving "CSV UTF-8".
    # newline="" lets the csv module handle quoted fields containing line breaks.
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise CommandError(f"{csv_path} is missing columns: {', '.join(missing)}")
        rows = []
        for row in reader:
            name = row["Company Name"].strip()
            if not name:
                continue
            ats = row["ATS Name"].strip()
            board_token = row["ATS board name"].strip()

            # A blank board also covers blank-ATS rows; neither can be crawled.
            if not board_token or ats.casefold() in IGNORED_ATS:
                continue
            rows.append({
                "name": name, "ats": ats, "board_token": board_token
            })
        return rows

class Command(BaseCommand):
    """Pick which companies to vet (input, skip recently vetted, throttle), then hand off.
 
    Selection only: the actual vetting and DB writes happen in vet_companies.
    """
    help = "Collect new companies, merge with the DB, and vet a throttled batch."

    def add_arguments(self, parser):
        """Define CLI flags. Throttle defaults come from settings (.env), so flags override per run."""
        # Either names or --csv, not both; enforced in handle(). Not an argparse
        # mutually exclusive group: nargs="*" positionals misbehave inside one.
        parser.add_argument(
            "names",
            nargs="*",
            default=[],
            help='Company names to vet, e.g. Stripe "Scale AI"',
        )
        parser.add_argument(
            "--csv",
            type=Path,
            help="Cowork CSV: Company Name, ATS Name, ATS board name",
        )
        # %(default)s is argparse's placeholder; --help fills in the actual value.
        parser.add_argument("--workers", type=int,
                            default=settings.VETTING_MAX_WORKERS,
            help="Concurrent vetting calls (default: %(default)s)")
        parser.add_argument("--max-companies", type=int,
                            default=settings.VETTING_MAX_COMPANIES,
            help="Max companies vetted per run (default: %(default)s)")
        parser.add_argument("--revet-after-days", type=int,
                            default=settings.VETTING_REVET_AFTER_DAYS,
                    help="Minimum days before an already-vetted company can be re-vetted "
                    "(default: %(default)s)")

    def handle(self, *args, **options):
        """Build the input list, drop recently vetted companies, cap the batch, and vet it."""
        names, csv_path = options["names"], options["csv"]
        
        if names and csv_path:
            raise CommandError("Use either company n ames or --csv, not both.")
        if csv_path:
            company_list = read_csv(csv_path)
        elif names:
            # No board info from the command line; see the module docstring caveat.
            company_list = [{"name": n.strip(), "ats": None, "board_token": None} for n in names]
        else:
            raise CommandError('Give company  names (e.g. Stripe "Scale AI") or --csv PATH.')

        # Vetted after the cutoff = checked fewer than N days ago, so skip for now.
        # Never-vetted companies aren't in this set, so they land in to_process automatically.
        cutoff = timezone.localdate() - timedelta(days=options["revet_after_days"])
        recently_vetted = {
            name.casefold()
            for name in Company.objects.filter(vetted_on__gt=cutoff).values_list("name", flat=True)
        }

        # casefold on both sides: this comparison runs in Python, not under the DB's
        # case-insensitive collation, so "AirBnB" must be matched to "Airbnb" by hand.
        to_skip = [n for n in company_list if n["name"].casefold() in recently_vetted]
        to_process = [n for n in company_list if n["name"].casefold() not in recently_vetted]

        # Throttle: keeps a run inside the Lambda time limit. The rest wait for the next run.
        to_process = to_process[: options["max_companies"]]

        print("Vet New Companies -")
        print(f"Max Companies to Vet: { options["max_companies"]}")
        print(f"Re-Vet Companies after Days: { options["revet_after_days"]}")
        
        if to_skip:
            print("Skipping these companies: " + ', '.join(c["name"] for c in to_skip))
        
        if to_process:
            print("Processing these companies: " + ', '.join(c["name"] for c in to_process))
            vet_companies(to_process, max_workers=options["workers"])
