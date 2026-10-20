"""CLI entry point — run a competitive intelligence report from the terminal."""

from __future__ import annotations

import argparse
import os
import sys
import logging

from dotenv import load_dotenv

from .agent import ResearchAgent
from .models import AgentStep
from .report_renderer import render_markdown


def _on_step(step: AgentStep) -> None:
    """Print each agent step live to the terminal."""
    tool_info = ""
    if step.tool_call:
        tool_info = f" → {step.tool_call.tool.value}"
    status = "✅" if step.tool_result and step.tool_result.success else "❌" if step.tool_result else "💭"
    print(f"\n{status} Step {step.step_number}{tool_info}")
    print(f"   Thought: {step.thought[:150]}")
    if step.observation:
        print(f"   Observation: {step.observation[:150]}")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Context Scout — AI-powered competitive intelligence using Context.dev"
    )
    parser.add_argument("domain", help="Target company domain (e.g., firecrawl.dev)")
    parser.add_argument("--output", "-o", default="report.md", help="Output file path (default: report.md)")
    parser.add_argument("--max-steps", type=int, default=15, help="Max agent reasoning steps (default: 15)")
    parser.add_argument("--llm-provider", default="deepseek", choices=["openai", "anthropic", "deepseek"], help="LLM provider")
    parser.add_argument("--llm-model", default=None, help="LLM model name")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    # API keys from .env
    context_key = os.environ.get("CONTEXT_DEV_API_KEY")
    if not context_key:
        print("❌ Set CONTEXT_DEV_API_KEY in your .env file")
        sys.exit(1)

    if args.llm_provider == "deepseek":
        llm_key = os.environ.get("DEEPSEEK_API_KEY")
        model = args.llm_model or "deepseek-chat"
    elif args.llm_provider == "openai":
        llm_key = os.environ.get("OPENAI_API_KEY")
        model = args.llm_model or "gpt-4o-mini"
    else:
        llm_key = os.environ.get("ANTHROPIC_API_KEY")
        model = args.llm_model or "claude-sonnet-4-20250514"

    if not llm_key:
        env_map = {"deepseek": "DEEPSEEK_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
        print(f"❌ Set {env_map[args.llm_provider]} in your .env file")
        sys.exit(1)

    print(f"🔍 Context Scout — Researching {args.domain}")
    print(f"   LLM: {args.llm_provider}/{model}")
    print(f"   Max steps: {args.max_steps}")
    print("=" * 60)

    agent = ResearchAgent(
        context_api_key=context_key,
        llm_api_key=llm_key,
        llm_provider=args.llm_provider,
        llm_model=model,
        max_steps=args.max_steps,
        on_step=_on_step,
    )

    report = agent.research(args.domain)

    # Render and save
    md = render_markdown(report)
    with open(args.output, "w") as f:
        f.write(md)

    print("\n" + "=" * 60)
    print(f"✅ Report saved to {args.output}")
    print(f"   {len(report.competitors)} competitors found")
    print(f"   {len(report.steps_taken)} research steps taken")
    print(f"   {report.total_credits_used} API credits used")


if __name__ == "__main__":
    main()
