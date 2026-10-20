"""Context.dev API wrapper — exposes each endpoint as a callable tool for the agent."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from context.dev import ContextDev

from .models import CompanyProfile, ToolName, ToolResult

logger = logging.getLogger(__name__)


class ContextTools:
    """Thin wrapper that turns Context.dev SDK calls into structured ToolResults."""

    def __init__(self, api_key: str):
        self.client = ContextDev(api_key=api_key)

    # ── dispatch ────────────────────────────────────────────

    def execute(self, tool: ToolName, arguments: dict) -> ToolResult:
        """Execute any tool by name, routing to the right method."""
        dispatch = {
            ToolName.BRAND_LOOKUP: self._brand_lookup,
            ToolName.BRAND_SEARCH: self._brand_search,
            ToolName.WEB_SCRAPE: self._web_scrape,
            ToolName.WEB_SEARCH: self._web_search,
            ToolName.EXTRACT_COMPETITORS: self._extract_competitors,
            ToolName.EXTRACT_STYLEGUIDE: self._extract_styleguide,
            ToolName.NEWS_SEARCH: self._news_search,
            ToolName.MAP_URLS: self._map_urls,
            ToolName.SCREENSHOT: self._screenshot,
            ToolName.PEOPLE_ENRICH: self._people_enrich,
            ToolName.WEB_ANSWERS: self._web_answers,
        }
        handler = dispatch.get(tool)
        if not handler:
            return ToolResult(tool=tool, success=False, error=f"Unknown tool: {tool}")

        try:
            result = handler(**arguments)
        except Exception as exc:
            logger.exception("Tool %s failed", tool)
            return ToolResult(tool=tool, success=False, error=str(exc))

        if result.success and result.credits_used is None:
            result.credits_used = _credits_consumed(result.data)
        return result

    # ── individual tools ────────────────────────────────────

    def _brand_lookup(self, domain: str, **_: Any) -> ToolResult:
        """Look up detailed brand/company info by domain."""
        resp = self.client.brand.retrieve(domain=domain, type="by_domain")
        data = _dump(resp)
        return ToolResult(tool=ToolName.BRAND_LOOKUP, success=True, data=data)

    def _brand_search(self, query: str, **_: Any) -> ToolResult:
        """Search for brands by name."""
        resp = self.client.brand.search(query=query)
        data = _dump(resp)
        return ToolResult(tool=ToolName.BRAND_SEARCH, success=True, data=data)

    def _web_scrape(self, url: str, **_: Any) -> ToolResult:
        """Scrape a URL and return clean markdown."""
        resp = self.client.web.scrape(url=url, formats={"markdown": True})
        data = _dump(resp)
        return ToolResult(tool=ToolName.WEB_SCRAPE, success=True, data=data)

    def _web_search(self, query: str, num_results: int = 5, **_: Any) -> ToolResult:
        """Web search via Context.dev."""
        resp = self.client.web.search(query=query, num_results=num_results)
        data = _dump(resp)
        return ToolResult(tool=ToolName.WEB_SEARCH, success=True, data=data)

    def _extract_competitors(self, domain: str, num_competitors: int = 5, **_: Any) -> ToolResult:
        """Extract competitors for a company by its domain."""
        resp = self.client.web.extract_competitors(
            domain=domain,
            num_competitors=num_competitors,
        )
        data = _dump(resp)
        return ToolResult(tool=ToolName.EXTRACT_COMPETITORS, success=True, data=data)

    def _extract_styleguide(self, domain: str, **_: Any) -> ToolResult:
        """Extract brand style guide (colors, fonts) from a domain."""
        resp = self.client.web.extract_styleguide(domain=domain)
        data = _dump(resp)
        return ToolResult(tool=ToolName.EXTRACT_STYLEGUIDE, success=True, data=data)

    def _news_search(self, query: str, **_: Any) -> ToolResult:
        """Search recent news about a company or topic.

        Uses natural language search mode.
        """
        # Natural-language searches are ordered by relevance only — the API
        # rejects an explicit sort_by for this search type.
        resp = self.client.news.search(
            search_by={"type": "natural_language", "query": query},
            limit=10,
        )
        data = _dump(resp)
        return ToolResult(tool=ToolName.NEWS_SEARCH, success=True, data=data)

    def _map_urls(self, domain: str, **_: Any) -> ToolResult:
        """Discover all URLs on a website."""
        resp = self.client.web.map_urls(domain=domain, max_links=50)
        data = _dump(resp)
        return ToolResult(tool=ToolName.MAP_URLS, success=True, data=data)

    def _screenshot(self, domain: str, page: Optional[str] = None, **_: Any) -> ToolResult:
        """Take a screenshot of a page."""
        kwargs: dict[str, Any] = {"domain": domain}
        if page:
            kwargs["page"] = page
        resp = self.client.web.screenshot(**kwargs)
        data = _dump(resp)
        return ToolResult(tool=ToolName.SCREENSHOT, success=True, data=data)

    def _people_enrich(self, name: Optional[str] = None, email: Optional[str] = None, **_: Any) -> ToolResult:
        """Enrich a person's data."""
        kwargs: dict[str, Any] = {}
        if name:
            parts = name.split(" ", 1)
            kwargs["name"] = {"first": parts[0], "last": parts[1] if len(parts) > 1 else ""}
        if email:
            kwargs["email"] = email
        resp = self.client.people.enrich(**kwargs)
        data = _dump(resp)
        return ToolResult(tool=ToolName.PEOPLE_ENRICH, success=True, data=data)

    def _web_answers(self, task: str, **_: Any) -> ToolResult:
        """Ask a natural-language question — Context.dev answers using web data."""
        resp = self.client.web.answers(task=task)
        data = _dump(resp)
        return ToolResult(tool=ToolName.WEB_ANSWERS, success=True, data=data)

    # ── helpers ─────────────────────────────────────────────

    def build_company_profile(self, brand_data: dict) -> CompanyProfile:
        """Turn a raw brand API response into a structured CompanyProfile.

        Accepts either the full ``brand.retrieve`` response (data under a
        ``brand`` key) or an already-unwrapped brand object.
        """
        b = brand_data.get("brand") if isinstance(brand_data.get("brand"), dict) else brand_data

        return CompanyProfile(
            name=b.get("title") or b.get("name") or b.get("domain") or "Unknown",
            domain=b.get("domain", ""),
            description=b.get("description") or b.get("slogan"),
            logo_url=_first_logo_url(b.get("logos")),
            industry=_industry_label(b.get("industries")),
            founded_year=b.get("founded_year"),
            employee_count=_employee_count(b.get("employees")),
            location=_location_label(b.get("address")),
            technologies=b.get("technologies", []),
            social_links=_socials_map(b.get("socials")),
            raw_data=b,
        )


def _credits_consumed(data: Any) -> Optional[int]:
    """Pull credits_consumed from a response's key_metadata, if present."""
    if isinstance(data, dict):
        km = data.get("key_metadata")
        if isinstance(km, dict) and km.get("credits_consumed") is not None:
            try:
                return int(km["credits_consumed"])
            except (TypeError, ValueError):
                return None
    return None


def _first_logo_url(logos: Any) -> Optional[str]:
    if isinstance(logos, list):
        for logo in logos:
            if isinstance(logo, dict) and logo.get("url"):
                return logo["url"]
    elif isinstance(logos, dict):
        return logos.get("url") or logos.get("logo_url")
    return None


def _industry_label(industries: Any) -> Optional[str]:
    # Shape: {"eic": [{"industry": "Finance", "subindustry": "Payments..."}]}
    if isinstance(industries, dict):
        eic = industries.get("eic")
        if isinstance(eic, list) and eic:
            first = eic[0]
            if isinstance(first, dict):
                parts = [first.get("industry"), first.get("subindustry")]
                label = " — ".join(p for p in parts if p)
                return label or None
    if isinstance(industries, list) and industries:
        return str(industries[0])
    if isinstance(industries, str):
        return industries
    return None


def _employee_count(employees: Any) -> Optional[str]:
    # Shape: {"exact": 16694, "range": "5001 to 10000"}
    if isinstance(employees, dict):
        if employees.get("range"):
            return str(employees["range"])
        if employees.get("exact") is not None:
            return str(employees["exact"])
    elif employees not in (None, ""):
        return str(employees)
    return None


def _location_label(address: Any) -> Optional[str]:
    if isinstance(address, dict):
        parts = [address.get("city"), address.get("state_province"), address.get("country")]
        label = ", ".join(p for p in parts if p)
        return label or None
    if isinstance(address, str):
        return address
    return None


def _socials_map(socials: Any) -> dict:
    # Shape: [{"type": "x", "url": "https://x.com/stripe"}, ...]
    if isinstance(socials, list):
        return {s["type"]: s["url"] for s in socials if isinstance(s, dict) and s.get("type") and s.get("url")}
    if isinstance(socials, dict):
        return socials
    return {}


def _dump(resp: Any) -> dict:
    """Safely convert an SDK response to a dict."""
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    if isinstance(resp, dict):
        return resp
    try:
        return json.loads(json.dumps(resp, default=str))
    except (TypeError, ValueError):
        return {"raw": str(resp)}
