"""Digest engine — turns collected signals into a delta brief.

Run 1 (no state): seed a baseline — record current page hashes and mark
existing news as already-seen, as of a chosen point in time.
Run 2+ (state exists): report only what is NEW since the last run — new news
items and changed pages — fused and ranked into one brief.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from openai import OpenAI

from context_scout.tools import ContextTools
from .collector import Collector, _parse_dt
from . import state as state_mod

logger = logging.getLogger(__name__)

SYNTH_SYSTEM = """\
You are a competitive-intelligence analyst writing a short digest for a busy \
operator. You are given, per competitor, the NEW things since the last digest: \
off-site news items (with dates) and on-site page changes. Produce concise \
Markdown:

1. A top section "## Most significant moves" — a ranked bullet list (max 6) of \
the items that matter most across ALL competitors, each with one clause on WHY \
it matters. Rank funding > major product launch > pricing change > exec/hiring \
> minor. Cite the competitor name.
2. A "## By competitor" section — one short subsection per competitor that had \
anything new, bullets for news (with date) and page changes. Skip competitors \
with nothing new.

Be specific and brief. Do not invent anything not in the input. If an item is \
routine noise, you may omit it."""


class DigestEngine:
    def __init__(self, context_api_key: str, llm_api_key: str, llm_model: str = "deepseek-chat"):
        self.collector = Collector(ContextTools(api_key=context_api_key))
        self.llm = OpenAI(api_key=llm_api_key, base_url="https://api.deepseek.com")
        self.llm_model = llm_model

    def run(self, competitors: list[str], state: dict, as_of: datetime) -> tuple[str, dict]:
        seeded = state_mod.is_seeded(state)
        last_run = _parse_dt(state.get("last_run_at")) if seeded else None
        seen_ids = set(state.get("seen_news_ids") or [])
        page_hashes: dict = dict(state.get("page_hashes") or {})
        meta: dict = dict(state.get("competitors") or {})

        per_comp: dict[str, dict] = {}
        new_seen: set[str] = set(seen_ids)

        for domain in competitors:
            info = meta.get(domain) or {}
            name = info.get("name") or self.collector.resolve_name(domain)
            pages = info.get("pages") or self.collector.discover_pages(domain)
            meta[domain] = {"name": name, "pages": pages}

            # off-site: news newer than last run, not already seen
            news = self.collector.recent_news(name, since=last_run, limit=20)
            fresh_news = []
            for it in news:
                nid = it.get("id")
                if not seeded:
                    # seed: mark as already-known only the items dated on/before
                    # the seed point, so genuinely newer items surface next run
                    dt = _parse_dt(it.get("published_at"))
                    if nid and dt and dt <= as_of:
                        new_seen.add(nid)
                    continue
                if nid and nid in seen_ids:
                    continue
                fresh_news.append(it)
                if nid:
                    new_seen.add(nid)

            # on-site: hash each tracked page, compare to stored
            page_changes = []
            for url in pages:
                h = self.collector.page_snapshot(url)
                if h is None:
                    continue
                old = page_hashes.get(url)
                if seeded and old and old != h:
                    page_changes.append({"url": url})
                page_hashes[url] = h

            per_comp[domain] = {"name": name, "news": fresh_news, "page_changes": page_changes}

        new_state = {
            "competitors": meta,
            "seen_news_ids": sorted(new_seen),
            "page_hashes": page_hashes,
            "last_run_at": as_of.isoformat(),
        }

        if not seeded:
            md = self._render_seed(competitors, meta, as_of)
        else:
            md = self._render_delta(per_comp, last_run, as_of)
        return md, new_state

    # -- rendering --

    def _render_seed(self, competitors: list[str], meta: dict, as_of: datetime) -> str:
        lines = [f"# Competitor Digest — baseline established",
                 f"\n*Seeded as of {as_of.date()} — tracking {len(competitors)} competitors. "
                 f"Re-run later to see what's new.*\n", "## Tracking"]
        for d in competitors:
            m = meta.get(d, {})
            lines.append(f"- **{m.get('name', d)}** ({d}) — pages: " +
                         ", ".join(m.get("pages", [])) or d)
        return "\n".join(lines)

    def _render_delta(self, per_comp: dict, last_run: Optional[datetime], as_of: datetime) -> str:
        total_news = sum(len(c["news"]) for c in per_comp.values())
        total_pages = sum(len(c["page_changes"]) for c in per_comp.values())
        header = (f"# Competitor Digest — what's new\n\n"
                  f"*Changes since {last_run.date() if last_run else '?'} "
                  f"(as of {as_of.date()}) — {total_news} news item(s), "
                  f"{total_pages} page change(s) across {len(per_comp)} competitors.*\n")

        if total_news == 0 and total_pages == 0:
            return header + "\nNothing new this period.\n"

        payload = {d: c for d, c in per_comp.items() if c["news"] or c["page_changes"]}
        try:
            resp = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": SYNTH_SYSTEM},
                    {"role": "user", "content": "Window: since %s.\n\nSignals:\n%s" % (
                        last_run.date() if last_run else "?",
                        json.dumps(payload, default=str, indent=1))},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            body = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.exception("synthesis failed")
            body = self._render_raw(payload)
        return header + "\n" + body

    def _render_raw(self, payload: dict) -> str:
        lines = ["## By competitor (raw — synthesis unavailable)"]
        for d, c in payload.items():
            lines.append(f"\n### {c['name']}")
            for n in c["news"]:
                lines.append(f"- [{n['published_at']}] {n['title']} ({n['url']})")
            for p in c["page_changes"]:
                lines.append(f"- page changed: {p['url']}")
        return "\n".join(lines)
