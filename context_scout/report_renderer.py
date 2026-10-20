"""Render an IntelligenceReport as clean Markdown and HTML."""

from __future__ import annotations

from .models import IntelligenceReport


def render_markdown(report: IntelligenceReport) -> str:
    """Generate a polished Markdown competitive intelligence report."""
    lines: list[str] = []

    lines.append(f"# Competitive Intelligence Report: {report.target_company.name}")
    lines.append("")
    lines.append(f"*Generated at {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')} "
                 f"| {len(report.steps_taken)} research steps "
                 f"| {report.total_credits_used} API credits used*")
    lines.append("")

    # ── Target Company ──────────────────────────────────────
    lines.append("## Target Company")
    lines.append("")
    tc = report.target_company
    lines.append(f"**{tc.name}** — [{tc.domain}](https://{tc.domain})")
    if tc.description:
        lines.append(f"\n{tc.description}")
    lines.append("")

    details = []
    if tc.industry:
        details.append(f"**Industry:** {tc.industry}")
    if tc.employee_count:
        details.append(f"**Employees:** {tc.employee_count}")
    if tc.location:
        details.append(f"**HQ:** {tc.location}")
    if tc.founded_year:
        details.append(f"**Founded:** {tc.founded_year}")
    if details:
        lines.append(" | ".join(details))
        lines.append("")

    # ── Competitors ─────────────────────────────────────────
    if report.competitors:
        lines.append("## Competitive Landscape")
        lines.append("")
        lines.append(f"Found **{len(report.competitors)}** competitors:")
        lines.append("")

        for i, comp in enumerate(report.competitors, 1):
            lines.append(f"### {i}. {comp.name}")
            if comp.domain:
                lines.append(f"[{comp.domain}](https://{comp.domain})")
            if comp.description:
                lines.append(f"\n{comp.description}")
            if comp.similarity_reason:
                lines.append(f"\n*Why a competitor:* {comp.similarity_reason}")

            if comp.profile:
                p = comp.profile
                info_parts = []
                if p.industry:
                    info_parts.append(f"Industry: {p.industry}")
                if p.employee_count:
                    info_parts.append(f"Employees: {p.employee_count}")
                if p.location:
                    info_parts.append(f"HQ: {p.location}")
                if info_parts:
                    lines.append(f"\n{' | '.join(info_parts)}")

            if comp.pricing_data:
                lines.append(f"\n**Pricing:** {_summarize_dict(comp.pricing_data)}")

            if comp.recent_news:
                lines.append("\n**Recent News:**")
                for news_item in comp.recent_news[:3]:
                    if isinstance(news_item, dict):
                        title = news_item.get("title", "")
                        url = news_item.get("url", "")
                        if title:
                            lines.append(f"- [{title}]({url})" if url else f"- {title}")

            lines.append("")

    # ── Market Summary ──────────────────────────────────────
    if report.market_summary:
        lines.append("## Market Summary")
        lines.append("")
        lines.append(report.market_summary)
        lines.append("")

    # ── Competitive Advantages ──────────────────────────────
    if report.competitive_advantages:
        lines.append("## Competitive Advantages")
        lines.append("")
        for adv in report.competitive_advantages:
            lines.append(f"- ✅ {adv}")
        lines.append("")

    # ── Competitive Risks ───────────────────────────────────
    if report.competitive_risks:
        lines.append("## Competitive Risks")
        lines.append("")
        for risk in report.competitive_risks:
            lines.append(f"- ⚠️ {risk}")
        lines.append("")

    # ── Pricing Analysis ────────────────────────────────────
    if report.pricing_analysis:
        lines.append("## Pricing Analysis")
        lines.append("")
        lines.append(report.pricing_analysis)
        lines.append("")

    # ── News Summary ────────────────────────────────────────
    if report.news_summary:
        lines.append("## Recent News & Developments")
        lines.append("")
        lines.append(report.news_summary)
        lines.append("")

    # ── Recommendations ─────────────────────────────────────
    if report.recommendations:
        lines.append("## Recommendations")
        lines.append("")
        for i, rec in enumerate(report.recommendations, 1):
            lines.append(f"{i}. {rec}")
        lines.append("")

    # ── Agent Trace ─────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("<details>")
    lines.append("<summary>🔍 Agent Research Trace (click to expand)</summary>")
    lines.append("")
    for step in report.steps_taken:
        tool_info = ""
        if step.tool_call:
            tool_info = f" → `{step.tool_call.tool.value}({step.tool_call.arguments})`"
        status = "✅" if step.tool_result and step.tool_result.success else "❌" if step.tool_result else "💭"
        lines.append(f"**Step {step.step_number}** {status}{tool_info}")
        lines.append(f"> {step.thought[:200]}")
        lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("---")
    lines.append("*Built with [Context Scout](https://github.com/mumer119131/context-scout) "
                 "— AI-powered competitive intelligence using [Context.dev](https://context.dev)*")

    return "\n".join(lines)


def _summarize_dict(d: dict, max_items: int = 5) -> str:
    """Quick inline summary of a dict."""
    parts = []
    for k, v in list(d.items())[:max_items]:
        parts.append(f"{k}: {v}")
    return ", ".join(parts)
