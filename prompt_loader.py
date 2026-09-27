# prompt_loader.py
"""Load prompt (.md) and tool schema (.json) files that live next to this module."""
from functools import lru_cache
from pathlib import Path
from string import Template
import json

# Folder this file lives in, so lookups work no matter where the script is run from.
HERE = Path(__file__).parent


@lru_cache  # Read each prompt from disk once per run, not on every API call.
def load_prompt(name: str) -> str:
    """Return the contents of <name>.md as a string."""
    return (HERE / f"{name}.md").read_text(encoding="utf-8")

def render_prompt(name: str, **vars) -> str:
    """Load <name>.md and fill in any $placeholders from vars.
    Uses Template ($var) instead of .format() so JSON braces in the prompt don't break.
    """
    return Template(load_prompt(name)).safe_substitute(**vars)

def load_tool(name: str) -> dict:
    """Return <name>.json parsed into a dict, ready to pass in the API's tools list."""
    return json.loads((HERE / f"{name}.json").read_text(encoding="utf-8"))