"""Streamlit UI for Context Scout — minimal but functional."""

import os
from dotenv import load_dotenv
load_dotenv()
import streamlit as st
from context_scout.agent import ResearchAgent
from context_scout.models import AgentStep
from context_scout.report_renderer import render_markdown

st.set_page_config(
    page_title="Context Scout",
    page_icon="🔍",
    layout="wide",
)

# ── Sidebar: Configuration ─────────────────────────────────
with st.sidebar:
    st.title("🔍 Context Scout")
    st.caption("AI-powered competitive intelligence using [Context.dev](https://context.dev)")

    context_key = st.text_input(
        "Context.dev API Key",
        value=os.environ.get("CONTEXT_DEV_API_KEY", ""),
        type="password",
    )

    llm_provider = st.selectbox("LLM Provider", ["deepseek", "openai", "anthropic"])

    if llm_provider == "deepseek":
        llm_key = st.text_input(
            "DeepSeek API Key",
            value=os.environ.get("DEEPSEEK_API_KEY", ""),
            type="password",
        )
        default_model = "deepseek-chat"
    elif llm_provider == "openai":
        llm_key = st.text_input(
            "OpenAI API Key",
            value=os.environ.get("OPENAI_API_KEY", ""),
            type="password",
        )
        default_model = "gpt-4o-mini"
    else:
        llm_key = st.text_input(
            "Anthropic API Key",
            value=os.environ.get("ANTHROPIC_API_KEY", ""),
            type="password",
        )
        default_model = "claude-sonnet-4-20250514"

    llm_model = st.text_input("Model", value=default_model)
    max_steps = st.slider("Max Research Steps", 5, 25, 15)

    st.divider()
    st.markdown(
        "**How it works:** Context Scout uses an AI agent (ReAct loop) "
        "that autonomously decides which Context.dev endpoints to call "
        "to build a competitive intelligence report."
    )
    st.markdown(
        "**Endpoints used:** brand lookup, competitor extraction, "
        "web scrape, web search, news search, style guide extraction, "
        "web answers, and more."
    )

# ── Main area ───────────────────────────────────────────────
st.header("Competitive Intelligence Report")
st.markdown(
    "⚡ Powered by **[Context.dev](https://context.dev)** — the agent uses "
    "Context.dev's API as its realtime web-perception layer."
)

domain = st.text_input(
    "Enter a company domain to research",
    placeholder="e.g., firecrawl.dev, stripe.com, linear.app",
)

col1, col2 = st.columns([1, 4])
with col1:
    run_button = st.button("🚀 Research", type="primary", use_container_width=True)

if run_button:
    if not context_key:
        st.error("Please enter your Context.dev API key in the sidebar.")
    elif not llm_key:
        st.error(f"Please enter your {llm_provider.title()} API key in the sidebar.")
    elif not domain:
        st.error("Please enter a company domain to research.")
    else:
        # ── Run the agent ───────────────────────────────────
        progress_container = st.container()
        steps_expander = progress_container.expander("🔄 Agent Research Steps (live)", expanded=True)
        step_placeholder = steps_expander.empty()

        steps_log: list[str] = []

        def on_step(step: AgentStep) -> None:
            tool_info = ""
            if step.tool_call:
                tool_info = f" → `{step.tool_call.tool.value}`"
            status = "✅" if step.tool_result and step.tool_result.success else "❌" if step.tool_result else "💭"
            line = f"{status} **Step {step.step_number}**{tool_info}: {step.thought[:120]}"
            steps_log.append(line)
            step_placeholder.markdown("\n\n".join(steps_log))

        with st.spinner("Agent is researching... this may take 1-3 minutes."):
            try:
                agent = ResearchAgent(
                    context_api_key=context_key,
                    llm_api_key=llm_key,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    max_steps=max_steps,
                    on_step=on_step,
                )
                report = agent.research(domain)
            except Exception as e:
                st.error(f"Agent failed: {e}")
                st.stop()

        # ── Display results ─────────────────────────────────
        st.success(
            f"Research complete! {len(report.competitors)} competitors found "
            f"in {len(report.steps_taken)} steps."
        )

        # Report tabs
        tab_report, tab_raw, tab_trace = st.tabs(["📊 Report", "📄 Markdown", "🔍 Agent Trace"])

        with tab_report:
            md = render_markdown(report)
            st.markdown(md, unsafe_allow_html=True)

        with tab_raw:
            md = render_markdown(report)
            st.code(md, language="markdown")
            st.download_button(
                "📥 Download Report",
                data=md,
                file_name=f"context_scout_{domain.replace('.', '_')}.md",
                mime="text/markdown",
            )

        with tab_trace:
            st.subheader("Agent Decision Trace")
            for step in report.steps_taken:
                with st.expander(
                    f"Step {step.step_number}: {step.thought[:80]}",
                    expanded=False,
                ):
                    st.markdown(f"**Thought:** {step.thought}")
                    if step.tool_call:
                        st.markdown(f"**Tool:** `{step.tool_call.tool.value}`")
                        st.json(step.tool_call.arguments)
                    if step.tool_result:
                        status = "✅ Success" if step.tool_result.success else f"❌ Failed: {step.tool_result.error}"
                        st.markdown(f"**Result:** {status}")
                    if step.observation:
                        st.markdown(f"**Observation:** {step.observation[:500]}")

# ── Footer ──────────────────────────────────────────────────
st.divider()
st.caption(
    "Built with [Context.dev](https://context.dev) | "
    "[GitHub](https://github.com/umer-2k1/context-scout)"
)
