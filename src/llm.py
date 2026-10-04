import json
import re

import requests
from pydantic import BaseModel, Field, field_validator

from .config import settings

ALLOWED_DOMAINS = {
    "Cloud",
    "DevOps",
    "AI",
    "Machine Learning",
    "Software Engineering",
    "Backend",
}


class CompanyEvidence(BaseModel):
    domains: list[str] = Field(default_factory=list)
    tech_company: bool = False
    remote_evidence: bool = False
    internship_evidence: bool = False
    student_program_evidence: bool = False
    reasoning: str = ""


class CompanyAnalysis(BaseModel):
    score: int = Field(ge=0, le=100)
    priority: str
    domains: list[str] = Field(default_factory=list)
    remote_compatible: bool = False
    pfe_potential: str = "unknown"
    reasoning: str = ""
    evidence: CompanyEvidence | None = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value):
        value = value.upper()
        return value if value in {"HIGH", "MEDIUM", "LOW"} else "LOW"

    @field_validator("pfe_potential")
    @classmethod
    def validate_pfe(cls, value):
        value = value.lower()
        return value if value in {"high", "medium", "unknown"} else "unknown"


# ---------------------------------------------------------
# TEXT EXTRACTION
# ---------------------------------------------------------

EVIDENCE_KEYWORDS = [
    "company",
    "agency",
    "software",
    "technology",
    "technical",
    "developers",
    "engineers",
    "engineering",
    "product",
    "products",
    "services",
    "solutions",
    "platform",
    "saas",
    "cloud",
    "devops",
    "docker",
    "kubernetes",
    "artificial intelligence",
    "machine learning",
    "cybersecurity",
    "backend",
    "frontend",
    "web development",
    "mobile development",
    "careers",
    "jobs",
    "hiring",
    "remote",
    "internship",
]


def build_relevant_evidence(text: str, max_chars: int = 7000) -> str:
    if not text:
        return ""

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    blocks = re.split(r"\n\s*\n", text)

    selected = []
    seen = set()

    for block in blocks:
        block = block.strip()

        if not block:
            continue

        lower = block.lower()

        if any(keyword in lower for keyword in EVIDENCE_KEYWORDS):
            signature = re.sub(r"\s+", " ", lower[:500])

            if signature not in seen:
                selected.append(block)
                seen.add(signature)

    if not selected:
        return text[:4000]

    return "\n\n".join(selected)[:max_chars]


# ---------------------------------------------------------
# SIMPLE DOMAIN EXTRACTION
# ---------------------------------------------------------

DOMAIN_PATTERNS = {
    "Cloud": [
        r"\baws\b",
        r"amazon web services",
        r"\bazure\b",
        r"google cloud",
        r"\bgcp\b",
        r"cloud computing",
        r"cloud infrastructure",
        r"cloud solutions?",
        r"cloud services?",
    ],
    "DevOps": [
        r"\bdevops\b",
        r"docker",
        r"kubernetes",
        r"ci/cd",
        r"continuous integration",
        r"continuous deployment",
        r"terraform",
        r"jenkins",
        r"ansible",
    ],
    "AI": [
        r"artificial intelligence",
        r"\bai[- ]powered\b",
        r"\bai solutions?\b",
        r"generative ai",
        r"\bllm\b",
        r"large language model",
        r"computer vision",
        r"natural language processing",
    ],
    "Machine Learning": [
        r"machine learning",
        r"deep learning",
        r"\bpytorch\b",
        r"\btensorflow\b",
        r"neural networks?",
    ],
    "Software Engineering": [
        r"software development",
        r"software engineering",
        r"custom software",
        r"web development",
        r"mobile development",
        r"application development",
        r"software products?",
        r"\breact\b",
        r"\bnode\.js\b",
        r"\bpython\b",
        r"\bjava\b",
        r"\btypescript\b",
    ],
    "Backend": [
        r"\bbackend\b",
        r"\bback-end\b",
        r"server-side",
        r"microservices",
        r"rest apis?",
        r"\bgraphql\b",
        r"api development",
    ],
}


def detect_domains(text: str) -> list[str]:
    if not text:
        return []

    text = text.lower()
    domains = []

    for domain, patterns in DOMAIN_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                domains.append(domain)
                break

    return domains


# ---------------------------------------------------------
# STRICT TECH COMPANY CHECK
# ---------------------------------------------------------

def detect_tech_company(text: str) -> bool:
    if not text:
        return False

    text = text.lower()

    strong_patterns = [
        r"software development",
        r"software engineering",
        r"software agency",
        r"custom software",
        r"software solutions",
        r"saas platform",
        r"saas company",
        r"cloud services",
        r"cloud solutions",
        r"cloud infrastructure",
        r"it services",
        r"it consulting",
        r"technology consulting",
        r"technology solutions",
        r"web development",
        r"mobile development",
        r"application development",
        r"ai solutions",
        r"artificial intelligence solutions",
        r"machine learning solutions",
        r"cybersecurity services",
        r"cyber security services",
        r"data engineering",
        r"data analytics services",
        r"software products",
        r"technology products",
        r"develops software",
        r"builds software",
        r"build software",
        r"developing software",
        r"software platform",
    ]

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in strong_patterns
    )


# ---------------------------------------------------------
# QWEN
# ---------------------------------------------------------

def extract_evidence(company):
    website_text = company.get("fetched_text") or ""

    domains = detect_domains(website_text)
    tech_company = detect_tech_company(website_text)

    # We only use Qwen for optional outreach information.
    # It does NOT decide whether the company is a tech company.
    prompt = f"""
Read the following company website evidence.

Extract ONLY these three factual signals:

1. remote_evidence:
true only if remote/hybrid/distributed work is explicitly mentioned.

2. internship_evidence:
true only if internships or interns are explicitly mentioned.

3. student_program_evidence:
true only if student/graduate/university programs are explicitly mentioned.

Return ONLY valid JSON:

{{
  "remote_evidence": false,
  "internship_evidence": false,
  "student_program_evidence": false
}}

WEBSITE:
{company.get("website", "")}

EVIDENCE:
{build_relevant_evidence(website_text, 5000)}
"""

    parsed = {}

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {
                    "temperature": 0,
                    "num_ctx": 4096,
                },
            },
            timeout=120,
        )

        response.raise_for_status()

        raw = response.json().get("response", "")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))

    except Exception as e:
        print(f"   ⚠ optional Qwen extraction failed: {e}")

    return CompanyEvidence(
        domains=domains,
        tech_company=tech_company,
        remote_evidence=bool(parsed.get("remote_evidence", False)),
        internship_evidence=bool(parsed.get("internship_evidence", False)),
        student_program_evidence=bool(
            parsed.get("student_program_evidence", False)
        ),
        reasoning="",
    )
# ---------------------------------------------------------
# ANALYSIS
# ---------------------------------------------------------

def calculate_score(company, evidence):
    """
    The score is only kept because the existing database expects it.

    It is NOT a PFE suitability score.
    """

    if not evidence.tech_company:
        return CompanyAnalysis(
            score=0,
            priority="LOW",
            domains=evidence.domains,
            remote_compatible=evidence.remote_evidence,
            pfe_potential="unknown",
            reasoning=(
                "Not classified as a relevant IT/technology company."
            ),
            evidence=evidence,
        )

    score = 60

    if len(evidence.domains) >= 2:
        score += 10

    if evidence.remote_evidence:
        score += 10

    if evidence.internship_evidence:
        score += 10

    if evidence.student_program_evidence:
        score += 10

    score = min(score, 100)

    if score >= 70:
        priority = "HIGH"
    elif score >= 40:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return CompanyAnalysis(
        score=score,
        priority=priority,
        domains=evidence.domains,
        remote_compatible=evidence.remote_evidence,
        pfe_potential="high"
        if evidence.internship_evidence
        else "unknown",
        reasoning=evidence.reasoning,
        evidence=evidence,
    )


def ask_qwen(company):
    evidence = extract_evidence(company)
    return calculate_score(company, evidence)


# ---------------------------------------------------------
# TEST
# ---------------------------------------------------------

def test():
    company = {
        "name": "Example Cloud Company",
        "website": "https://example.com",
        "fetched_text": """
        We are a software company building cloud infrastructure.
        Our engineers use AWS, Kubernetes and Docker.
        We develop backend APIs and AI-powered applications.
        """
    }

    result = ask_qwen(company)

    print(
        json.dumps(
            result.model_dump(),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    test()