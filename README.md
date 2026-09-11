# BBS-CMS AI (WordPress)

Hearing-sheet CSV → Japanese WordPress draft sections.

**Architecture:** monolithic FastAPI service with a REST API (not microservices).  
UI + hearing parse + AI-1/AI-2 pipeline + export run in one app.

## Lab

| Path | Hearing types |
|------|----------------|
| `/ai/v2/` | Type 1 新規 · Type 2 リニューアル · Type 3 サテライト · Type 4 サテライトリニューアル |

Samples: `/ai/v2/samples/type1-shinki.csv` … `type4-satellite-renewal.csv`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add API keys locally — never commit .env
```

## Run

```bash
./scripts/run_demo.sh
# or:
PYTHONPATH=src uvicorn ai_agent.api.app:app --host 0.0.0.0 --port 8765
```

Open http://127.0.0.1:8765/ai/v2/

## Tests

```bash
PYTHONPATH=src pytest -q
```

## Layout

| Path | Role |
|------|------|
| `src/ai_agent/` | FastAPI app, models, hearing pipelines |
| `demo/v2/` | Lab UI (all 4 types) |
| `fixtures/` | Shared hearing fixtures |
| `docs/` | Client-facing flow docs + model sheets |
| `scripts/` | Run / systemd / nginx examples |
| `tests/` | Pytest suite |

## Secrets

- Commit `.env.example` only.
- Never commit `.env`, SSH keys, or `data/` runtime files.
