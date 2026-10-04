from .config import settings
from .db import get_unanalyzed, save_analysis
from .llm import ask_qwen
from .research import research_company


def analyze():
    rows = get_unanalyzed(settings.analyze_limit)

    if not rows:
        print("Nothing to analyze.")
        return

    for row in rows:
        print(f"\n🧠 {row['name']}")

        fetched = row["fetched_text"] or ""

        if not fetched:
            try:
                fetched = research_company(
                    row["id"],
                    row["website"],
                )
            except Exception as e:
                print(f"   ⚠ research failed: {e}")
                fetched = ""

        if not fetched:
            print("   ⚠ no company evidence available — skipping")
            continue

        try:
            company = {
                **dict(row),
                "fetched_text": fetched,
            }

            result = ask_qwen(company)

            save_analysis(
                row["id"],
                result.model_dump(),
            )

            print(
                f"   → {result.score}/100 | "
                f"{result.priority} | "
                f"{result.pfe_potential}"
            )

        except Exception as e:
            print(f"   ❌ Qwen failed: {e}")