# analyze_company.py
"""Vet a single company with Claude: web-search it, then return a filled-in scoring form."""
import logging
import sys
import time
import os
from dotenv import load_dotenv


import anthropic
from crawler.prompt_loader import load_prompt, load_tool
logger = logging.getLogger(__name__)

# os.getenv doesn't read .env on its own; this loads it into the environment first.
load_dotenv()
_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    raise ValueError("ANTHROPIC_API_KEY is not set")

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
THINKING_MODEL = os.getenv("THINKING_MODEL", "claude-opus-4-7")
THINKING_BUDGET = int(os.getenv("THINKING_BUDGET", "8000"))

client = anthropic.Anthropic(api_key=_api_key)

def _print_usage(usage: anthropic.types.Usage) -> None:
    """Print token usage and web search count to stdout."""
    print(
        f"\n--- token usage ---\n"
        f"input:       {usage.input_tokens}\n"
        f"output:      {usage.output_tokens}\n"
        f"cache read:  {usage.cache_read_input_tokens or 0}\n"
        f"cache write: {usage.cache_creation_input_tokens or 0}\n"
        # server_tool_use is None when Claude didn't search at all.
        f"tool use:    {usage.server_tool_use.web_search_requests if usage.server_tool_use else 0}\n"
    )

def analyze_company(company_name: str) -> dict:
    """Research and score one company.
 
    Claude web-searches the company, then calls the submit_company_vetting
    tool; that tool call's input is the scoring record.
 
    Args:
        company_name: Company to vet, e.g. "Stripe".
 
    Returns:
        The vetting record as a dict, shaped by company_vetting_tool_schema.json.
 
    Raises:
        ValueError: Claude finished without submitting the vetting form.
    """
    start = time.perf_counter()

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        # System prompt is identical on every call, so cache it.
        system=[{
            "type": "text",
            "text": load_prompt("company_vetting_prompt"),
            "cache_control": {"type": "ephemeral"},
        }],
        # web_search runs on Anthropic's side; max_uses caps search cost per company.
        tools=[
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 10},
            load_tool("company_vetting_tool_schema")],
        # "auto" (not forced) so Claude can search before submitting the form.
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": f"Vet: {company_name}"}]
    )

    elapsed = time.perf_counter() - start
    print(f"{company_name} Run Time: {elapsed:.1f}s")
    logger.info(
                "Tokens — input: %d, output: %d, cache_read: %d, cache_write: %d",
                response.usage.input_tokens,
                response.usage.output_tokens,
                response.usage.cache_read_input_tokens or 0,
                response.usage.cache_creation_input_tokens or 0,
            )
    _print_usage(response.usage)

    # Response mixes text, search, and tool blocks; find the form submission wherever it is.
    block= next((b for b in response.content if b.type == "tool_use"), None)
    if block is None:
        raise ValueError(f"No vetting submitted for {company_name} (stop_reason: {response.stop_reason})")
    return block.input

if __name__ == "__main__":
    # Only runs when this file is executed directly, not when vet_companies.py imports it.
    # Test bench for vetting one company without touching vetted_companies.jsonl.
    # Usage: python analyze_company.py Figma   (defaults to Anthropic if no name given)
    #        python analyze_company.py "Scale AI"   (multi-word names need quotes)

    # Windows console defaults to cp1252, which can't print characters like →.
    sys.stdout.reconfigure(encoding="utf-8")

    # sys.argv[0] is the script name; argv[1] is the first word typed after it.
    result = analyze_company(sys.argv[1] if len(sys.argv) > 1 else "Anthropic")
    print(result)
