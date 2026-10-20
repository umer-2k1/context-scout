# 🔍 Context Scout

**AI-powered competitive intelligence agent built on [Context.dev](https://context.dev)**

Context Scout is an autonomous research agent that uses Context.dev's API as its web perception layer. Give it any company domain, and it will autonomously research competitors, pricing, news, brand data, and design systems — then synthesize everything into a structured intelligence report.

## What Makes This Different

Most competitive intelligence tools are **pipelines** — they run the same API calls in the same order every time. Context Scout is an **agent**. It uses a ReAct (Reason + Act) loop where an LLM decides:

- **Which** Context.dev endpoint to call next
- **Why** that endpoint matters at this step
- **When** it has gathered enough data to synthesize

This means the research adapts to what it finds. If competitor extraction reveals 3 players, it digs into all 3. If a company has no pricing page, it searches the web instead. The agent thinks, not just executes.

## Context.dev Endpoints Used

| Endpoint | Purpose |
|----------|---------|
| `brand.retrieve` | Company profile, logo, industry, employee count |
| `web.extract_competitors` | Discover competitors from a domain |
| `web.scrape` | Clean markdown extraction from any URL |
| `web.search` | Web search for supplementary data |
| `news.search` | Recent news and press coverage |
| `web.extract_styleguide` | Brand colors, fonts, design tokens |
| `web.answers` | Natural-language Q&A about any web page |
| `web.screenshot` | Visual capture of competitor pages |
| `web.map_urls` | Sitemap discovery |

## Architecture

```
User Input (domain)
      ↓
┌─────────────────────────┐
│   ReAct Agent Loop      │
│                         │
│  1. THINK  → LLM reasons│
│  2. ACT   → Context.dev │
│  3. OBSERVE → Parse data │
│  4. Repeat until done    │
└─────────────────────────┘
      ↓
Structured Report (Markdown)
```

## Quick Start

```bash
# Clone
git clone https://github.com/umer-2k1/context-scout.git
cd context-scout

# Install
pip install -r requirements.txt

# Set API keys
export CONTEXT_DEV_API_KEY="ctxt_secret_..."
export OPENAI_API_KEY="sk-..."  # or ANTHROPIC_API_KEY

# CLI
python -m context_scout.cli firecrawl.dev -o report.md

# Web UI
streamlit run app.py
```

## Usage

### CLI

```bash
# Basic usage
python -m context_scout.cli stripe.com

# With Anthropic instead of OpenAI
python -m context_scout.cli linear.app --llm-provider anthropic --llm-model claude-sonnet-4-20250514

# More research depth
python -m context_scout.cli notion.so --max-steps 20 -o notion_report.md
```

### Streamlit UI

```bash
streamlit run app.py
```

The UI shows the agent's reasoning in real-time — you can watch it think, pick tools, and build the report step by step.

## Example Output

A report includes:
- **Target Company Profile** — enriched brand data
- **Competitive Landscape** — discovered competitors with profiles
- **Pricing Analysis** — scraped and compared pricing pages
- **Recent News** — latest developments for each player
- **Competitive Advantages & Risks** — synthesized insights
- **Recommendations** — strategic suggestions
- **Agent Trace** — full decision log showing the agent's reasoning

## Tech Stack

- **Python 3.10+**
- **Context.dev SDK** — web perception layer (scrape, search, brand, news, competitors)
- **OpenAI / Anthropic** — reasoning engine (ReAct agent loop)
- **Pydantic** — structured data models
- **Streamlit** — minimal web UI

## License

MIT
