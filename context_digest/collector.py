"""Signal collection — reuses context_scout.tools for Context.dev access.

Two signal sources per competitor:
  * off-site  → news.search (entity by name, newest; date-filtered client-side
                because the API's filter_by.date currently returns nothing)
  * on-site   → scrape tracked pages and hash them (local snapshot+diff; the
                production path would swap in the monitors API for webhooks)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from context_scout.tools import ContextTools, _dump  # reuse the SDK wrapper

logger = logging.getLogger(__name__)

# page paths worth watching, in priority order
_TRACK_PATTERNS = ("pricing", "changelog", "release", "whats-new", "what-s-new", "blog", "news")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class Collector:
    def __init__(self, tools: ContextTools, max_pages_per_competitor: int = 2):
        self.tools = tools
        self.client = tools.client
        self.max_pages = max_pages_per_competitor

    # -- setup --

    def resolve_name(self, domain: str) -> str:
        try:
            b = _dump(self.client.brand.retrieve(domain=domain, type="by_domain")).get("brand", {})
            return b.get("title") or domain
        except Exception:
            return domain

    def discover_pages(self, domain: str) -> list[str]:
        """Pick a couple of high-signal pages (pricing / changelog / blog)."""
        try:
            data = _dump(self.client.web.map_urls(domain=domain, max_links=100))
        except Exception as exc:
            logger.warning("map_urls failed for %s: %s", domain, exc)
            return [f"https://{domain}"]
        urls = data.get("urls") or data.get("links") or []
        urls = [u.get("url") if isinstance(u, dict) else u for u in urls]
        urls = [u for u in urls if isinstance(u, str)]
        picked: list[str] = []
        for pat in _TRACK_PATTERNS:
            for u in urls:
                if pat in u.lower() and u not in picked:
                    picked.append(u)
                    break
            if len(picked) >= self.max_pages:
                break
        return picked or [f"https://{domain}"]

    # -- signals --

    def page_snapshot(self, url: str) -> Optional[str]:
        """Return a content hash for a page, or None if it couldn't be read."""
        try:
            data = _dump(self.client.web.scrape(url=url, formats={"markdown": True}))
            md = data.get("markdown")
            if isinstance(md, dict):            # shape: {"data": "<markdown>", ...}
                md = md.get("data") or md.get("markdown") or ""
            md = md or ""
            return _hash(md) if md else None
        except Exception as exc:
            logger.warning("scrape failed for %s: %s", url, exc)
            return None

    def recent_news(self, name: str, since: Optional[datetime], limit: int = 20) -> list[dict]:
        """News for a competitor, newest first, filtered to items after `since`."""
        try:
            data = _dump(self.client.news.search(
                search_by={"type": "entity", "entity": {"type": "name", "name": name}},
                sort_by={"type": "newest"},
                limit=limit,
            ))
        except Exception as exc:
            logger.warning("news.search failed for %s: %s", name, exc)
            return []
        items = data.get("data") or []
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            dt = _parse_dt(it.get("published_at"))
            if since and dt and dt <= since:
                continue
            out.append({
                "id": it.get("id"),
                "title": it.get("title"),
                "url": it.get("url"),
                "published_at": str(it.get("published_at"))[:10],
                "description": (it.get("description") or "")[:300],
            })
        return out
