import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from analyze_company import analyze_company


# Folder this file lives in
VETTED_COMPANIES = Path(__file__).parent / "vetted_companies.jsonl"

vetted = {}
if VETTED_COMPANIES.exists():
    with open(VETTED_COMPANIES, encoding="utf-8") as file:
        for line in file:
            record = json.loads(line)

            vetted[record["company"]] = {
                "company": record["company"], "ats": record["ats"],
                "board_token": record["board_token"], "vetted_on": record["checked_on"]
            }

companies = ["Anthropic", "Stripe", "Figma"]
to_vet = [c for c in companies if c not in vetted]

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = { pool.submit(analyze_company, name): name for name in to_vet}
    for future in as_completed(futures):
        name = futures[future]
        try:
            result = future.result()
        except Exception as e:
            print(f"FAILED {name}: {e}")
            continue
        with open(VETTED_COMPANIES, "a", encoding="utf-8") as file:
            file.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(f"Saved {name}")
    
