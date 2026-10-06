# analyze_company.py
"""Vet a single company with Claude: web-search it, then return a filled-in scoring form."""
import logging
import sys

from crawler.claude_api import DEFAULT_MODEL, VETTING_MAX_TOKENS, run_with_pause
from crawler.prompts.prompt_loader import load_prompt, load_tool

logger = logging.getLogger(__name__)

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
    

    response = run_with_pause(
        label=f"Vetting {company_name}",
        purpose="vet_company",
        model=DEFAULT_MODEL,
        max_tokens=VETTING_MAX_TOKENS,
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

    # A cut-off response can still contain a form, but it may be incomplete.
    if response.stop_reason == "max_tokens":
        logger.warning("%s: output hit max_tokens=%d; vetting record may be cut off.",
                       company_name, VETTING_MAX_TOKENS)

    # Response mixes text, search, and tool blocks; find the form submission wherever it is.
    block= next((b for b in response.content if b.type == "tool_use"), None)
    if block is None:
        # Already paid for, so log what came back before raising.
        logger.error("%s: no vetting form submitted (stop_reason=%s, block types=%s)",
                     company_name, response.stop_reason, [b.type for b in response.content])
        raise ValueError(
            f"No vetting submitted for {company_name} (stop_reason: {response.stop_reason})")
    
    logger.info("%s: vetting form received (%d fields)", company_name, len(block.input))
    logger.debug("%s: vetting record: %s", company_name, block.input)
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
