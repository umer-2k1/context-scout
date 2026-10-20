"""Pydantic models for structured data throughout the agent pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ToolName(str, Enum):
    """Available Context.dev tools the agent can invoke."""

    BRAND_LOOKUP = "brand_lookup"
    BRAND_SEARCH = "brand_search"
    WEB_SCRAPE = "web_scrape"
    WEB_SEARCH = "web_search"
    EXTRACT_COMPETITORS = "extract_competitors"
    EXTRACT_STYLEGUIDE = "extract_styleguide"
    NEWS_SEARCH = "news_search"
    MAP_URLS = "map_urls"
    SCREENSHOT = "screenshot"
    PEOPLE_ENRICH = "people_enrich"
    WEB_ANSWERS = "web_answers"


class ToolCall(BaseModel):
    """A single tool invocation decided by the agent."""

    tool: ToolName
    arguments: dict = Field(default_factory=dict)
    reasoning: str = Field(description="Why the agent chose this tool at this step")


class ToolResult(BaseModel):
    """Result of executing a tool call."""

    tool: ToolName
    success: bool
    data: dict = Field(default_factory=dict)
    error: Optional[str] = None
    credits_used: Optional[int] = None


class AgentStep(BaseModel):
    """One complete step in the agent's reasoning loop."""

    step_number: int
    thought: str
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[ToolResult] = None
    observation: str = ""


class CompanyProfile(BaseModel):
    """Enriched company profile from brand data."""

    name: str
    domain: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
    industry: Optional[str] = None
    founded_year: Optional[int] = None
    employee_count: Optional[str] = None
    location: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    social_links: dict = Field(default_factory=dict)
    raw_data: dict = Field(default_factory=dict)


class CompetitorInfo(BaseModel):
    """Information about a single competitor."""

    name: str
    domain: Optional[str] = None
    description: Optional[str] = None
    similarity_reason: Optional[str] = None
    profile: Optional[CompanyProfile] = None
    pricing_data: Optional[dict] = None
    recent_news: list[dict] = Field(default_factory=list)
    styleguide: Optional[dict] = None


class IntelligenceReport(BaseModel):
    """The final competitive intelligence report."""

    target_company: CompanyProfile
    competitors: list[CompetitorInfo] = Field(default_factory=list)
    market_summary: str = ""
    competitive_advantages: list[str] = Field(default_factory=list)
    competitive_risks: list[str] = Field(default_factory=list)
    pricing_analysis: str = ""
    news_summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    steps_taken: list[AgentStep] = Field(default_factory=list)
    total_credits_used: int = 0


class AgentState(BaseModel):
    """Current state of the agent's research process."""

    target_domain: str
    target_company: Optional[CompanyProfile] = None
    competitors_found: list[CompetitorInfo] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    gathered_data: dict = Field(default_factory=dict)
    total_credits: int = 0
    max_steps: int = 15
    status: str = "initializing"
