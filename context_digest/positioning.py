"""Competitor Positioning Radar.

Tracks how a competitor positions itself over time — brand title/slogan,
homepage tagline, and pricing tiers — and reports *field-level* shifts
("tagline changed", "tier renamed", "price +$4"). This needs memory of the
prior positioning, so it is something the stateless `answers` endpoint
cannot do. Reuses context_digest.collector for Context.dev access.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from openai import OpenAI

from context_scout.tools import ContextTools, _dump
from .collector import Collector

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
Extract how this company positions itself, from the page text provided. Return
STRICT JSON only, no prose:
{"tagline": "<the main homepage headline / value proposition, one line>",
 "rename_notice": "<any banner announcing a rebrand/rename/acquisition, e.g. 'X is now Y'; null if none>",
 "pricing_tiers": [{"name": "<tier name>", "price": "<price as shown, e.g. $10/mo or Custom>"}]}
If pricing is not present, use an empty list. Do not invent tiers, prices, or a rename notice."""


class PositioningRadar:
    def __init__(self, context_api_key: str, llm_api_key: str, llm_model: str = "deepseek-chat"):
        self.collector = Collector(ContextTools(api_key=context_api_key))
        self.client = self.collector.client
        self.llm = OpenAI(api_key=llm_api_key, base_url="https://api.deepseek.com")
        self.llm_model = llm_model

    # -- capture one positioning snapshot --

    def snapshot(self, domain: str) -> dict:
        b = _dump(self.client.brand.retrieve(domain=domain, type="by_domain")).get("brand", {})
        title = b.get("title") or domain
        slogan = b.get("slogan")

        home_md = self._scrape_md(f"https://{domain}")
        pricing_url = self._find_pricing(domain)
        pricing_md = self._scrape_md(pricing_url) if pricing_url else ""

        extracted = self._extract(home_md, pricing_md)
        return {
            "title": title,
            "slogan": slogan,
            "tagline": extracted.get("tagline"),
            "rename_notice": extracted.get("rename_notice"),
            "pricing_tiers": extracted.get("pricing_tiers", []),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def _scrape_md(self, url: str) -> str:
        try:
            md = _dump(self.client.web.scrape(url=url, formats={"markdown": True})).get("markdown")
            if isinstance(md, dict):
                md = md.get("data") or ""
            return str(md or "")[:8000]
        except Exception as exc:
            logger.warning("scrape failed %s: %s", url, exc)
            return ""

    def _find_pricing(self, domain: str) -> Optional[str]:
        for url in self.collector.discover_pages(domain):
            if "pricing" in url.lower():
                return url
        return f"https://{domain}/pricing"

    def _extract(self, home_md: str, pricing_md: str) -> dict:
        if not home_md and not pricing_md:
            return {"tagline": None, "pricing_tiers": []}
        try:
            resp = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": _EXTRACT_SYSTEM},
                    {"role": "user", "content": f"HOMEPAGE:\n{home_md[:5000]}\n\nPRICING:\n{pricing_md[:3000]}"},
                ],
                temperature=0,
                max_tokens=600,
            )
            return _loose_json(resp.choices[0].message.content or "")
        except Exception:
            logger.exception("positioning extraction failed")
            return {"tagline": None, "pricing_tiers": []}

    # -- diff two snapshots into human-readable changes --
    #
    # Two layers guard against the LLM extractor's non-determinism:
    #   1. candidate_diff() normalizes values (case/whitespace/price) so cosmetic
    #      rewording never registers as a change.
    #   2. confirm() asks the LLM to drop any surviving candidate that is just the
    #      same thing worded differently — biased to suppress false positives.

    @staticmethod
    def candidate_diff(old: dict, new: dict) -> list[str]:
        changes: list[str] = []
        for field, label in [("title", "Name"), ("slogan", "Slogan"), ("tagline", "Tagline")]:
            o, n = old.get(field) or "", new.get(field) or ""
            if n and _norm_text(o) != _norm_text(n):
                changes.append(f"{label} changed:\n    was: {o.strip() or '—'}\n    now: {n.strip()}")
        o_rn, n_rn = old.get("rename_notice") or "", new.get("rename_notice") or ""
        if n_rn.strip() and _norm_text(o_rn) != _norm_text(n_rn):
            changes.append(f"🔴 Rebrand/rename detected: {n_rn.strip()}")

        # pricing: match tiers by normalized name, compare normalized price
        op = {_norm_text(t.get("name")): (t.get("name"), _norm_price(t.get("price")))
              for t in (old.get("pricing_tiers") or []) if isinstance(t, dict)}
        np = {_norm_text(t.get("name")): (t.get("name"), _norm_price(t.get("price")))
              for t in (new.get("pricing_tiers") or []) if isinstance(t, dict)}
        for k, (name, price) in np.items():
            if k not in op:
                changes.append(f"New pricing tier: {name}")
            elif op[k][1] != price:
                changes.append(f"Price change — {name}: {op[k][1]} → {price}")
        for k, (name, _) in op.items():
            if k not in np:
                changes.append(f"Pricing tier removed: {name}")
        return changes

    def confirm(self, old: dict, new: dict, candidates: list[str]) -> list[str]:
        """Keep only candidates the LLM judges MATERIAL (not rewording)."""
        if not candidates:
            return []
        numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates))
        sys = ("You verify competitive-positioning changes. Given OLD and NEW positioning "
               "and candidate changes, return STRICT JSON {\"material\": [<indices>]} listing "
               "only indices that are REAL changes. A tier renamed with the same price, or the "
               "same message reworded/reformatted, is NOT material. A genuine rebrand/rename, a "
               "real price change, or a real new/removed tier IS material.")
        usr = (f"OLD:\n{json.dumps({k: old.get(k) for k in ('title','slogan','tagline','rename_notice','pricing_tiers')}, default=str)}\n\n"
               f"NEW:\n{json.dumps({k: new.get(k) for k in ('title','slogan','tagline','rename_notice','pricing_tiers')}, default=str)}\n\n"
               f"CANDIDATES:\n{numbered}")
        try:
            resp = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": usr}],
                temperature=0, max_tokens=200,
            )
            parsed = _loose_json(resp.choices[0].message.content or "")
            if "material" not in parsed:
                return candidates  # couldn't parse a verdict → keep candidates
            idx = parsed.get("material") or []
            keep = {int(i) for i in idx if str(i).isdigit() or isinstance(i, int)}
            return [c for i, c in enumerate(candidates) if i in keep]
        except Exception:
            logger.exception("confirmation pass failed; keeping candidates")
            return candidates  # fail open: better a rare noise item than a missed real change

    # -- run over a competitor set --

    def run(self, domains: list[str], state: dict) -> tuple[str, dict]:
        prior = state.get("snapshots") or {}
        seeded = bool(prior)
        new_snaps: dict = {}
        report: list[tuple[str, list[str]]] = []

        for d in domains:
            snap = self.snapshot(d)
            new_snaps[d] = snap
            if seeded and d in prior:
                candidates = self.candidate_diff(prior[d], snap)
                report.append((snap["title"], self.confirm(prior[d], snap, candidates)))

        new_state = {"snapshots": new_snaps, "last_run_at": datetime.now(timezone.utc).isoformat()}
        md = self._render(report, domains, new_snaps) if seeded else self._render_seed(new_snaps)
        return md, new_state

    def _render_seed(self, snaps: dict) -> str:
        lines = ["# Positioning Radar — baseline captured\n"]
        for d, s in snaps.items():
            tiers = ", ".join(f"{t.get('name')} {t.get('price')}" for t in s.get("pricing_tiers", []) if isinstance(t, dict))
            lines.append(f"- **{s['title']}** ({d}) — tagline: _{s.get('tagline') or '—'}_" +
                         (f" | tiers: {tiers}" if tiers else ""))
        lines.append("\n*Re-run later to detect positioning shifts.*")
        return "\n".join(lines)

    def _render(self, report, domains, snaps) -> str:
        changed = [(name, ch) for name, ch in report if ch]
        lines = ["# Positioning Radar — what shifted\n"]
        if not changed:
            lines.append("No positioning changes detected across the tracked set this run.")
        else:
            lines.append(f"**{len(changed)} competitor(s) repositioned:**\n")
            for name, ch in changed:
                lines.append(f"## {name}")
                for c in ch:
                    lines.append(f"- {c}")
                lines.append("")
        unchanged = [snaps[d]["title"] for (name, ch) in report for d in domains if snaps[d]["title"] == name and not ch]
        if unchanged:
            lines.append(f"_No change: {', '.join(sorted(set(unchanged)))}_")
        return "\n".join(lines)


def _norm_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().strip()).rstrip(".!")


def _norm_price(s: Optional[str]) -> str:
    s = (s or "").lower().replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if m:
        return "free" if float(m.group(0)) == 0 else m.group(0)
    if "free" in s:
        return "free"
    if "pay as you go" in s or "payg" in s:
        return "payg"
    if "custom" in s or "contact" in s:
        return "custom"
    return _norm_text(s)


def _loose_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1].replace("json", "", 1).strip() if "```json" in text else text.split("```")[1].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                pass
    return {"tagline": None, "pricing_tiers": []}
