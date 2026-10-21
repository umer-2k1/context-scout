"""CLI for the Competitor Positioning Radar.

    # Run 1 — capture a baseline of how each competitor positions itself
    python -m context_digest.radar --competitors firecrawl.dev,exa.ai,coda.io \\
        --state radar_state.json

    # Run 2 (later) — report positioning shifts since the baseline
    python -m context_digest.radar --competitors firecrawl.dev,exa.ai,coda.io \\
        --state radar_state.json -o radar.md
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from .positioning import PositioningRadar
from . import state as state_mod


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Competitor Positioning Radar on Context.dev")
    p.add_argument("--competitors", required=True, help="Comma-separated competitor domains")
    p.add_argument("--state", default="radar_state.json")
    p.add_argument("--output", "-o", default=None)
    p.add_argument("--llm-model", default="deepseek-chat")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    ctx_key = os.environ.get("CONTEXT_DEV_API_KEY")
    llm_key = os.environ.get("DEEPSEEK_API_KEY")
    if not ctx_key or not llm_key:
        print("Set CONTEXT_DEV_API_KEY and DEEPSEEK_API_KEY in your .env")
        sys.exit(1)

    domains = [d.strip() for d in args.competitors.split(",") if d.strip()]
    state = state_mod.load(args.state)
    mode = "delta" if state.get("snapshots") else "baseline"
    print(f"Positioning Radar — {mode} run | {len(domains)} competitors")
    print("=" * 60)

    radar = PositioningRadar(context_api_key=ctx_key, llm_api_key=llm_key, llm_model=args.llm_model)
    md, new_state = radar.run(domains, state)
    state_mod.save(args.state, new_state)

    print("\n" + md + "\n")
    print("=" * 60)
    print(f"State saved to {args.state}")
    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
        print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
