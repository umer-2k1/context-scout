"""CLI for Context Digest.

Seed a baseline, then re-run to get a delta brief:

    # Run 1 — seed a baseline as of 45 days ago
    python -m context_digest.cli --competitors coda.io,airtable.com,slite.com \\
        --state digest_state.json --as-of-days-ago 45

    # Run 2 — what's new since then (real news timeline)
    python -m context_digest.cli --competitors coda.io,airtable.com,slite.com \\
        --state digest_state.json -o digest.md
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from .digest import DigestEngine
from . import state as state_mod


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(description="Context Digest — competitor delta brief on Context.dev")
    p.add_argument("--competitors", required=True, help="Comma-separated competitor domains")
    p.add_argument("--state", default="digest_state.json", help="State file path")
    p.add_argument("--as-of-days-ago", type=int, default=0,
                   help="Treat 'now' as N days ago (used to seed a baseline in the past for the demo)")
    p.add_argument("--output", "-o", default=None, help="Write the digest to this file too")
    p.add_argument("--llm-model", default="deepseek-chat")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(message)s")

    ctx_key = os.environ.get("CONTEXT_DEV_API_KEY")
    llm_key = os.environ.get("DEEPSEEK_API_KEY")
    if not ctx_key or not llm_key:
        print("Set CONTEXT_DEV_API_KEY and DEEPSEEK_API_KEY in your .env")
        sys.exit(1)

    competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
    as_of = datetime.now(timezone.utc) - timedelta(days=args.as_of_days_ago)

    state = state_mod.load(args.state)
    mode = "delta" if state_mod.is_seeded(state) else "seed"
    print(f"Context Digest — {mode} run | {len(competitors)} competitors | as-of {as_of.date()}")
    print("=" * 60)

    engine = DigestEngine(context_api_key=ctx_key, llm_api_key=llm_key, llm_model=args.llm_model)
    md, new_state = engine.run(competitors, state, as_of)
    state_mod.save(args.state, new_state)

    print("\n" + md + "\n")
    print("=" * 60)
    print(f"State saved to {args.state}")
    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
        print(f"Digest written to {args.output}")


if __name__ == "__main__":
    main()
