"""ReAct agent engine — the core reasoning loop that drives competitive research."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any, Callable, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from .models import (
    AgentState,
    AgentStep,
    CompetitorInfo,
    IntelligenceReport,
    ToolCall,
    ToolName,
)
from .tools import ContextTools

logger = logging.getLogger(__name__)

# ── System prompt for the research agent ───────────────────

SYSTEM_PROMPT = """\
You are Context Scout, an expert competitive intelligence analyst.

You have access to the following tools powered by Context.dev:

1. **brand_lookup** — Get detailed company info by domain.
   Arguments: {"domain": "example.com"}

2. **brand_search** — Search for companies by name.
   Arguments: {"query": "company name"}

3. **web_scrape** — Scrape a URL for clean markdown content.
   Arguments: {"url": "https://..."}

4. **web_search** — Search the web for information.
   Arguments: {"query": "search terms", "num_results": 5}

5. **extract_competitors** — Find competitors from a company's domain.
   Arguments: {"domain": "example.com", "num_competitors": 5}

6. **extract_styleguide** — Extract brand style (colors, fonts) from a domain.
   Arguments: {"domain": "example.com"}

7. **news_search** — Search recent news about a company or topic.
   Arguments: {"query": "company name news"}

8. **map_urls** — Discover all pages on a website.
   Arguments: {"domain": "example.com"}

9. **screenshot** — Capture a visual screenshot of a site.
   Arguments: {"domain": "example.com"}

10. **web_answers** — Ask a natural-language question answered from web data.
    Arguments: {"task": "the question in natural language"}

## Your Process

Given a target company domain, you will:
1. Look up the target company's brand data
2. Find their competitors using extract_competitors and web_search
3. For each top competitor (max 5):
   - Look up their brand data
   - Scrape their pricing/product page
   - Search for recent news
4. Synthesize findings into a competitive intelligence report

## Response Format

At each step, respond with EXACTLY this JSON structure:
```json
{
  "thought": "Your reasoning about what to do next",
  "tool": "tool_name or null if done",
  "arguments": {"arg": "value"},
  "observation_needed": true
}
```

When you have gathered enough data, respond with:
```json
{
  "thought": "I have enough data. Generating report.",
  "tool": null,
  "done": true,
  "report": {
    "market_summary": "...",
    "competitive_advantages": ["..."],
    "competitive_risks": ["..."],
    "pricing_analysis": "...",
    "news_summary": "...",
    "recommendations": ["..."]
  }
}
```

Be strategic with your tool usage. Don't waste calls — plan ahead.
"""


class ResearchAgent:
    """Agentic loop: Think → Act → Observe → Repeat until done."""

    def __init__(
        self,
        context_api_key: str,
        llm_api_key: str,
        llm_provider: str = "openai",
        llm_model: str = "gpt-4o-mini",
        max_steps: int = 15,
        on_step: Optional[Callable[[AgentStep], None]] = None,
    ):
        self.tools = ContextTools(api_key=context_api_key)
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.max_steps = max_steps
        self.on_step = on_step  # callback for UI streaming

        # LLM client
        if llm_provider in ("openai", "deepseek"):
            base_url = None
            if llm_provider == "deepseek":
                base_url = "https://api.deepseek.com"
            self.llm = OpenAI(api_key=llm_api_key, base_url=base_url)
            self.llm_provider = "openai"  # DeepSeek uses OpenAI-compatible API
        elif llm_provider == "anthropic":
            try:
                import anthropic
                self.llm = anthropic.Anthropic(api_key=llm_api_key)
            except ImportError:
                raise ImportError("pip install anthropic")
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    def research(self, target_domain: str) -> IntelligenceReport:
        """Run the full research loop for a target company."""
        state = AgentState(target_domain=target_domain, max_steps=self.max_steps)
        state.status = "researching"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Research the competitive landscape for: {target_domain}\n\n"
                    f"Start by looking up the company's brand data, then find their "
                    f"competitors, and build a comprehensive competitive intelligence report."
                ),
            },
        ]

        for step_num in range(1, self.max_steps + 1):
            logger.info("Step %d/%d", step_num, self.max_steps)

            # 1. Think — ask LLM what to do next
            llm_response = self._call_llm(messages)
            parsed = self._parse_agent_response(llm_response)

            step = AgentStep(
                step_number=step_num,
                thought=parsed.get("thought", ""),
            )

            # 2. Check if agent says it's done
            if parsed.get("done") or parsed.get("tool") is None:
                step.observation = "Agent completed research."
                state.steps.append(step)
                if self.on_step:
                    self.on_step(step)

                report_data = parsed.get("report", {})
                return self._build_report(state, report_data)

            # 3. Act — execute the tool
            tool_name_str = parsed["tool"]
            arguments = parsed.get("arguments", {})

            try:
                tool_enum = ToolName(tool_name_str)
            except ValueError:
                step.observation = f"Unknown tool: {tool_name_str}. Use a valid tool name."
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": f"Error: {step.observation}"})
                state.steps.append(step)
                if self.on_step:
                    self.on_step(step)
                continue

            step.tool_call = ToolCall(
                tool=tool_enum,
                arguments=arguments,
                reasoning=parsed.get("thought", ""),
            )

            tool_result = self.tools.execute(tool_enum, arguments)
            step.tool_result = tool_result

            if tool_result.success:
                # 4. Observe — process the result
                result_summary = self._summarize_result(tool_result)
                step.observation = result_summary

                # Update state with gathered data
                self._update_state(state, tool_enum, tool_result)

                messages.append({"role": "assistant", "content": llm_response})
                messages.append({
                    "role": "user",
                    "content": f"Tool result for {tool_name_str}:\n{result_summary}\n\nContinue your research. What's the next step?",
                })
            else:
                step.observation = f"Tool failed: {tool_result.error}"
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({
                    "role": "user",
                    "content": f"Tool {tool_name_str} failed: {tool_result.error}\n\nTry a different approach.",
                })

            state.steps.append(step)
            if self.on_step:
                self.on_step(step)

        # Hit max steps — generate report with what we have
        state.status = "completed"
        return self._build_report(state, {})

    # ── LLM calls ──────────────────────────────────────────

    def _call_llm(self, messages: list[dict]) -> str:
        """Call the LLM and return the raw text response."""
        if self.llm_provider == "openai":
            resp = self.llm.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                temperature=0.2,
                max_tokens=2000,
            )
            return resp.choices[0].message.content or ""

        elif self.llm_provider == "anthropic":
            system = ""
            conv_messages = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    conv_messages.append(m)
            resp = self.llm.messages.create(
                model=self.llm_model,
                system=system,
                messages=conv_messages,
                temperature=0.2,
                max_tokens=2000,
            )
            return resp.content[0].text

        return ""

    def _parse_agent_response(self, response: str) -> dict:
        """Extract the JSON action from the LLM's response."""
        # Try to find JSON in the response
        text = response.strip()

        # Handle markdown code blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        # Try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in the text
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start : i + 1])
                        except json.JSONDecodeError:
                            break

        # Fallback — treat as thought-only
        return {"thought": response, "tool": None, "done": True, "report": {}}

    # ── State management ───────────────────────────────────

    def _update_state(self, state: AgentState, tool: ToolName, result):
        """Incorporate tool results into the running agent state."""
        data = result.data

        if tool == ToolName.BRAND_LOOKUP:
            if not state.target_company:
                state.target_company = self.tools.build_company_profile(data)
            else:
                # It's a competitor brand lookup
                profile = self.tools.build_company_profile(data)
                for comp in state.competitors_found:
                    if comp.domain and comp.domain in data.get("domain", ""):
                        comp.profile = profile
                        break

        elif tool == ToolName.EXTRACT_COMPETITORS:
            competitors = data.get("competitors", data.get("results", []))
            if isinstance(competitors, list):
                for c in competitors[:5]:
                    if isinstance(c, dict):
                        info = CompetitorInfo(
                            name=c.get("name", "Unknown"),
                            domain=c.get("domain", c.get("url", "")),
                            description=c.get("description", ""),
                            similarity_reason=c.get("reason", ""),
                        )
                        state.competitors_found.append(info)

        elif tool == ToolName.NEWS_SEARCH:
            # Store news data keyed by query
            state.gathered_data.setdefault("news", []).append(data)

        elif tool == ToolName.WEB_SCRAPE:
            state.gathered_data.setdefault("scraped_pages", []).append(data)

        if result.credits_used:
            state.total_credits += result.credits_used

    def _summarize_result(self, result) -> str:
        """Create a concise summary of tool results for the LLM context window."""
        data = result.data
        summary = json.dumps(data, default=str)

        # Truncate very long results to keep context manageable
        if len(summary) > 4000:
            summary = summary[:4000] + "\n... [truncated — data continues]"

        return summary

    def _build_report(self, state: AgentState, report_data: dict) -> IntelligenceReport:
        """Assemble the final IntelligenceReport from state + LLM synthesis."""
        from .models import CompanyProfile

        target = state.target_company or CompanyProfile(
            name=state.target_domain,
            domain=state.target_domain,
        )

        return IntelligenceReport(
            target_company=target,
            competitors=state.competitors_found,
            market_summary=report_data.get("market_summary", ""),
            competitive_advantages=report_data.get("competitive_advantages", []),
            competitive_risks=report_data.get("competitive_risks", []),
            pricing_analysis=report_data.get("pricing_analysis", ""),
            news_summary=report_data.get("news_summary", ""),
            recommendations=report_data.get("recommendations", []),
            generated_at=datetime.utcnow(),
            steps_taken=state.steps,
            total_credits_used=state.total_credits,
        )
