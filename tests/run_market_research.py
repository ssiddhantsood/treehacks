import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai_agents.market_research import run_market_research_agent  # noqa: E402


EXAMPLES = [
    {
        "label": "Gen Z college students (US) buying affordable streetwear",
        "description": "Gen Z college students who buy affordable streetwear",
        "product": "streetwear apparel",
        "region": "United States",
        "goal": "increase conversion on Instagram ads",
        "extraFocus": ["price sensitivity", "sustainability concerns"],
        "language": "English",
    },
    {
        "label": "Millennial parents (UK) choosing family meal kits",
        "description": "Millennial parents with children under 10",
        "product": "family meal kits",
        "region": "United Kingdom",
        "goal": "drive trials via paid social",
        "extraFocus": ["time-saving", "health/nutrition"],
        "language": "English",
    },
    {
        "label": "Remote tech workers (US) shopping for ergonomic chairs",
        "description": "Remote software engineers and product managers",
        "product": "ergonomic office chairs",
        "region": "United States",
        "goal": "increase qualified leads from LinkedIn ads",
        "extraFocus": ["price vs. quality tradeoffs", "B2B reimbursement policies"],
        "language": "English",
    },
]


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _print_result(label: str, result: dict, max_chars: int) -> None:
    print("")
    print(f"=== {label} ===")
    if not result.get("ok"):
        print(f"error: {result.get('error', 'unknown error')}")
        return

    transformations = result.get("transformations") or []
    if transformations:
        print("Transformations:")
        for idx, item in enumerate(transformations, start=1):
            print(f"{idx}. {item}")

    citations = result.get("citations") or []
    if citations:
        print("Citations:")
        for idx, item in enumerate(citations, start=1):
            print(f"{idx}. {item}")

    insights = result.get("insights", "") or ""
    if insights:
        print("Insights:")
        print(_truncate(insights, max_chars))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Perplexity market research agent on sample audiences.")
    parser.add_argument(
        "--limit",
        type=int,
        default=len(EXAMPLES),
        help="Number of examples to run (default: all).",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=2000,
        help="Max characters to print per insight block (0 = no truncation).",
    )
    args = parser.parse_args()

    failures = 0
    for item in EXAMPLES[: max(0, args.limit)]:
        result = run_market_research_agent(
            audience_description=item["description"],
            product=item.get("product"),
            region=item.get("region"),
            goal=item.get("goal"),
            extra_focus=item.get("extraFocus"),
            language=item.get("language"),
        )
        _print_result(item["label"], result, args.max_chars)
        if not result.get("ok"):
            failures += 1

    if failures:
        print("")
        print(f"{failures} example(s) failed. Ensure PERPLEXITY is set in backend/.env.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
