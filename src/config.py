import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()
@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    search_results_per_query: int = int(os.getenv("SEARCH_RESULTS_PER_QUERY", "10"))
    analyze_limit: int = int(os.getenv("ANALYZE_LIMIT", "50"))
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "15"))
    candidate_profile: str = os.getenv("CANDIDATE_PROFILE", "Final-year software engineering student seeking a 6-month PFE.")
    profile_path: str = os.getenv("PROFILE_PATH", "profile.json")
    outreach_num_ctx: int = int(os.getenv("OUTREACH_NUM_CTX", "8192"))
    outreach_max_attempts: int = int(os.getenv("OUTREACH_MAX_ATTEMPTS", "3"))
    editor: str = os.getenv("EDITOR", "notepad" if os.name == "nt" else "nano")
    gmail_address: str = os.getenv("GMAIL_ADDRESS", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    sender_name: str = os.getenv("SENDER_NAME", "Abderrahmen Jedidi")
    cv_path: str = os.getenv("CV_PATH", "")
    daily_send_limit: int = int(os.getenv("DAILY_SEND_LIMIT", "15"))
    send_delay_min: int = int(os.getenv("SEND_DELAY_MIN", "60"))
    send_delay_max: int = int(os.getenv("SEND_DELAY_MAX", "180"))
    min_outreach_score: int = int(os.getenv("MIN_OUTREACH_SCORE", "50"))
settings = Settings()


def _sanity_check(s):
    problems = []

    if not 0 <= s.min_outreach_score <= 100:
        problems.append(
            f"MIN_OUTREACH_SCORE={s.min_outreach_score} must be between 0 and 100 "
            "(scores are 0-100; this is probably a typo in .env)"
        )
    if s.send_delay_max < s.send_delay_min:
        problems.append(
            f"SEND_DELAY_MAX ({s.send_delay_max}) is smaller than "
            f"SEND_DELAY_MIN ({s.send_delay_min}) in .env"
        )
    if s.daily_send_limit < 1:
        problems.append(f"DAILY_SEND_LIMIT={s.daily_send_limit} must be at least 1")

    for p in problems:
        print(f"⚠ .env problem: {p}")


_sanity_check(settings)