# PFE Outreach Agent — V1

Local-first PFE company discovery + qualification agent.

Priority:
1. International companies
2. International startups
3. Sousse companies
4. Sousse startups
5. Tunis companies
6. Tunis startups

Domains: Cloud, DevOps, AI, Software Engineering.

## Setup (Windows PowerShell)
```powershell
cd pfe_outreach_agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
ollama list
python -m src.main llm-test
```

Set `OLLAMA_MODEL` in `.env` to the exact Qwen model you have installed. The default is `qwen3:4b`.

Then:
```powershell
python -m src.main discover
python -m src.main analyze
python -m src.main report
```

`all` runs the complete V1 pipeline:
```powershell
python -m src.main all
```

## Outreach (V2)

```powershell
Copy-Item profile.example.json profile.json   # fill in phone + review the texts
python -m src.main outreach                   # one draft per company
python -m src.main review                     # approve / edit / reject
python -m src.main show-outreach --status approved
python -m src.main outreach --regenerate      # redo unsent drafts
python -m src.main reset-outreach             # delete unsent drafts
```

The fixed parts of each email (intro, experience, closing, signature) come from `profile.json`. The LLM only writes the company-specific paragraph and must quote the website sentence it used. Python verifies the quote exists, checks numbers, dates, banned phrases and repetition, and marks failures as `needs_review`.

`profile.json` is gitignored: keep personal details there, not in code.

V2 still does NOT send email. It discovers, researches, scores, and ranks companies locally. Contact discovery, personalized emails, approval, Gmail sending, and follow-up tracking come next.
