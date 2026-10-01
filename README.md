# AI Architect

Describe a system in plain English and let an AI agent design it for you. Built on LangChain agents, with conversation memory persisted in Postgres so sessions can be resumed.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- A Postgres database (e.g. Supabase)
- An Anthropic or OpenAI API key

## Setup

```bash
uv sync
cp .env.example .env   # then fill in your keys
uv run pre-commit install   # lint, format and type-check on every commit
```

`.env`:

| Variable | Description |
| --- | --- |
| `ANTHROPIC_API_KEY` | API key for Claude (or `OPENAI_API_KEY` if using OpenAI) |
| `DATABASE_CONN_STR` | Postgres connection string for conversation memory |
| `LANGSMITH_*` | Optional LangSmith tracing |

Non-secret settings (LLM provider/model, summarization thresholds) live in `config.yaml`.

## Usage

**Terminal**

```bash
uv run ai-architect
```

| Command | Description |
| --- | --- |
| `/ask <question>` | Ask the agent a question |
| `/sessions` | List saved sessions |
| `/switch <# \| id>` | Resume a session |
| `/new_session` | Start a fresh conversation |
| `/session` | Show the current session id |
| `/help` | Show all commands |
| `/exit` | Quit |

**Web UI**

```bash
uv run ai-architect-ui
```

Opens a Streamlit chat at http://localhost:8501, with past sessions in the sidebar.

## Project layout

```
agent/          agent construction and query orchestration
console/        terminal app
ui/             Streamlit app
llm/            LLM provider factory
memory/         Postgres-backed short-term memory
observability/  logging
config.py       loads config.yaml + .env
```
