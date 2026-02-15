from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

PERPLEXITY_BASE_URL = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY") or os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
PERPLEXITY_MAX_TOKENS = int(os.getenv("PERPLEXITY_MAX_TOKENS", "700"))

client = OpenAI(api_key=PERPLEXITY_API_KEY or "", base_url=PERPLEXITY_BASE_URL)

SYSTEM_PROMPT = (
    "You are a market research analyst for ad optimization. Use the transformations as "
    "sub-questions, but only keep insights that are clearly relevant to ad performance. "
    "Be concise. Focus on common themes, pain points, motivations, and ad creative "
    "preferences grounded in real research or credible sources. If evidence is weak or "
    "mixed, say so. Avoid generic marketing fluff."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "market_research",
            "description": (
                "Research what influences a demographic group and their ad preferences "
                "using Perplexity Sonar."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "audienceDescription": {
                        "type": "string",
                        "description": "Description of the audience or demographic group.",
                    },
                    "product": {
                        "type": "string",
                        "description": "Product or category context (optional).",
                    },
                    "region": {
                        "type": "string",
                        "description": "Geographic focus (optional).",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Goal of the research (optional).",
                    },
                    "extraFocus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra topics or angles to emphasize.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Response language (optional).",
                    },
                },
                "required": ["audienceDescription"],
            },
        },
    }
]


def _normalize_list(value: Iterable[str] | str | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, Iterable):
        cleaned = []
        for item in value:
            text = str(item or "").strip()
            if text:
                cleaned.append(text)
        return cleaned
    return []


def _scope_suffix(product: str | None, region: str | None) -> str:
    scope = ""
    if product:
        scope += f" for {product}"
    if region:
        scope += f" in {region}"
    return scope


def _build_transformations(
    audience_description: str,
    product: str | None = None,
    region: str | None = None,
    goal: str | None = None,
    extra_focus: Iterable[str] | str | None = None,
) -> list[str]:
    scope = _scope_suffix(product, region)
    transformations = [
        f"What are the top purchase drivers and decision criteria for {audience_description}{scope}?",
        f"What ad creative styles, tones, and messaging resonate most with {audience_description}{scope}?",
        f"What common pain points, needs, or unmet demands does {audience_description} have{scope}?",
        f"What objections or barriers prevent {audience_description} from converting{scope}?",
        f"Which channels/platforms are most effective to reach {audience_description}{scope}?",
        f"How price-sensitive is {audience_description}{scope}, and what promotions or incentives work best?",
        f"What content formats or ad lengths perform best for {audience_description}{scope}?",
        f"Which competitor brands are popular with {audience_description}{scope}, and why?",
        f"What social, cultural, or lifestyle values influence {audience_description} decisions{scope}?",
    ]

    if goal:
        transformations.append(
            f"Given the goal '{goal}', what messaging or call-to-action is most likely to work "
            f"for {audience_description}{scope}?"
        )

    extras = _normalize_list(extra_focus)
    for item in extras:
        transformations.append(f"Investigate: {item} for {audience_description}{scope}.")

    return transformations


def _extract_citations(raw: dict) -> list[str]:
    citations = raw.get("citations")
    if isinstance(citations, list):
        return citations
    for choice in raw.get("choices", []) or []:
        message = choice.get("message") or {}
        found = message.get("citations")
        if isinstance(found, list):
            return found
    return []


def run_market_research_agent(
    audience_description: str,
    product: str | None = None,
    region: str | None = None,
    goal: str | None = None,
    extra_focus: Iterable[str] | str | None = None,
    language: str | None = None,
) -> dict:
    if not PERPLEXITY_API_KEY:
        return {"ok": False, "error": "Missing PERPLEXITY API key in environment."}

    audience = (audience_description or "").strip()
    if not audience:
        return {"ok": False, "error": "audienceDescription is required."}

    transformations = _build_transformations(
        audience_description=audience,
        product=product,
        region=region,
        goal=goal,
        extra_focus=extra_focus,
    )

    language_note = f"Respond in {language}." if language else "Respond in English."

    user_prompt = (
        f"Audience description: {audience}\n"
        f"Product/Category: {product or 'Not specified'}\n"
        f"Region: {region or 'Not specified'}\n"
        f"Goal: {goal or 'Not specified'}\n"
        f"{language_note}\n"
        "Use the transformations below as sub-questions and answer them briefly. "
        "Then provide a consolidated summary optimized for ad adjustments with:\n"
        "- Common themes (3-6 bullets)\n"
        "- Ad creative preferences (style, tone, proof points)\n"
        "- Top pain points/barriers\n"
        "- Recommended angles or testable hypotheses (3-5 bullets)\n"
        "Keep the full response under ~350 words. If a point isn't supported by evidence, "
        "label it as a hypothesis. Include citations when possible.\n\n"
        "Transformations:\n"
        + "\n".join([f"{idx + 1}. {item}" for idx, item in enumerate(transformations)])
    )

    response = client.chat.completions.create(
        model=PERPLEXITY_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        max_tokens=PERPLEXITY_MAX_TOKENS,
    )

    message = response.choices[0].message
    raw = response.model_dump()
    citations = _extract_citations(raw)

    return {
        "ok": True,
        "audience": audience,
        "product": product,
        "region": region,
        "goal": goal,
        "transformations": transformations,
        "insights": message.content or "",
        "citations": citations,
        "model": PERPLEXITY_MODEL,
    }
