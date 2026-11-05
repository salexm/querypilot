# QueryPilot

QueryPilot is a natural-language-to-SQL analytics assistant and a public portfolio project. A user types a question, an LLM generates SQL from the schema, the SQL runs read-only against PostgreSQL, and the results appear as a table and an automatic chart. An evaluation benchmark and self-correction on SQL errors come later.

## Current status

**Milestones 1 and 2 are done, and Milestone 0 is in progress.** The API answers questions through `POST /query`. There's no frontend yet.

| # | Milestone | Status |
|---|---|---|
| 0 | Skeleton: Compose, health checks, linting, CI | In progress: Compose and health checks done; linting and CI remain |
| 1 | Safe execution: data, roles, validator, executor | Done |
| 2 | NL to SQL: schema service, LLM adapter, `/query` | Done |
| 3 | Core UI: question flow, SQL view, table, errors | Not started |
| 4 | Auto charts: rule-based chart selection | Not started |
| 5 | History and traces | Not started |
| 6 | Benchmark: baseline accuracy, latency, cost | Not started |
| 7 | Self-correction: retry loop, before-and-after results | Not started |
| 8 | Portfolio polish: README results, diagram, demo GIF | Not started |

Open decisions: public demo or local only, and target roles. Don't assume an answer; ask when the work depends on one.

## Stack

- **Frontend:** React, Vite, TypeScript, TanStack Query, Recharts
- **Backend:** Python, FastAPI, `sqlglot` for SQL validation, `psycopg`, Alembic for app database migrations (not added yet)
- **LLM:** Anthropic Claude, behind the adapter in `backend/app/llm/`
- **Database:** PostgreSQL 17, with separate analytics and app databases
- **Demo data:** Olist e-commerce dataset (CC BY-NC-SA 4.0), loaded by a Python seed script with `psycopg`
- **Tests:** pytest for the backend
- **Local environment:** Docker Compose

## Architecture

The API and the benchmark both call one headless pipeline:

```text
question → schema context → generate SQL → validate → execute → chart spec → response + saved trace
```

Self-correction will be a bounded loop around generate, validate, and execute. Don't put pipeline logic in API routes, or the benchmark can't reuse it.

## Folder structure

This is the planned layout. `frontend/`, `eval/`, `.github/`, `backend/alembic/`, and `backend/app/store/` don't exist yet. Update this section when the real structure changes.

```text
querypilot/
├── docker-compose.yml
├── .env.example
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
│   └── decisions/             # short records of key choices
├── db/
│   ├── init/                  # databases, roles, grants
│   └── seed/                  # demo dataset load, schema, and tests
├── backend/
│   ├── alembic/               # app database only
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/               # routes and request/response models
│   │   ├── pipeline/          # orchestrator, generate, validate, execute, chart
│   │   ├── prompts/           # versioned prompt files
│   │   ├── schema/            # introspection and prompt formatting
│   │   ├── llm/               # interface and provider adapters
│   │   └── store/             # history and traces
│   └── tests/
├── frontend/src/
│   ├── api/                   # typed client
│   ├── components/            # table, chart, SQL viewer
│   └── features/query/
└── eval/
    ├── datasets/              # questions and gold SQL
    ├── runner.py
    ├── scoring.py
    └── reports/               # ignored unless added with `git add -f`
```

## Coding conventions

**General**
- Keep functions small and focused on one job.
- Prefer clear names over comments. Use comments to explain why, not what.
- Keep changes scoped to the current feature.
- Read configuration from environment variables through `backend/app/config.py`. Don't hardcode settings.

**Python**
- Add type hints to all function signatures, including return types.
- Use Pydantic models for API requests, API responses, and structured LLM output.
- Keep LLM provider code inside `backend/app/llm/`.
- Keep prompts in `backend/app/prompts/`, not in inline strings.

**TypeScript**
- Use strict mode and avoid `any`.
- Keep API calls in `frontend/src/api/`, not in components.
- Handle loading, empty, and error states in every feature that fetches data.

**Testing**
- Write backend tests with pytest in `backend/tests/`. Seed script tests live in `db/seed/tests/`.
- Mark tests that need the seeded database with `integration`. They skip when it isn't reachable, so run them in the `api` container.
- Add tests with each feature, and add a regression test with each bug fix.
- Don't call a real LLM in unit tests. Use a fake adapter.
- Run the relevant tests before calling a feature working, and report failures plainly.

## Safety rules

These apply to all work, because the repo is public and the app runs LLM-generated SQL.

- Run generated SQL only through the read-only analytics role, never the admin or app role.
- Keep the Postgres role as the main protection and the validator as a second layer. Don't weaken either one to make a query work.
- Validate SQL by parsing it with `sqlglot`, not with regex.
- Always enforce the statement timeout and row cap.
- Never commit real keys, passwords, or `.env` files. Add new settings to `.env.example` with placeholder values.
- Never put secrets in `VITE_*` variables, because they're exposed to the browser.
- Review eval output before committing it, because it can contain full prompts and query results.

## How to run

### Works today

```bash
cp .env.example .env              # then fill in your own values
docker compose up -d --wait db    # start Postgres and wait until it's healthy
docker compose run --rm --build seed  # download, verify, and load the dataset
docker compose up -d --build --wait api  # start the API on http://localhost:8000
docker compose exec api pytest    # run backend unit and integration tests

# Seed script tests, from db/seed with Python 3.12
pip install -r requirements-dev.txt
python -m pytest
```

`db/init/` runs only on an empty data volume. To apply changed database settings, run `docker compose down -v`, which deletes the data, then start again and reseed.

### Planned

These commands won't work until the milestone in brackets is finished. When one starts working, move it to "Works today" and correct it to match reality.

```bash
docker compose up --build                    # start web as well as db and api [3]
docker compose exec api alembic upgrade head # migrate the app database [5]
docker compose exec api python -m eval.runner # run the benchmark [6]
```

The API runs at `http://localhost:8000`. The planned web app URL is `http://localhost:5173`.

## Workflow rules

### Branches

- Build each major feature on its own branch, created from an up-to-date `main`. Each milestone in the status table counts as at least one major feature.
- Name branches by type, such as `feat/safe-execution`, `fix/row-cap`, or `docs/architecture`.
- If a major feature is about to start on `main`, create the branch first.

### Commits

- After each working feature, suggest a clear conventional commit message and remind the user to commit.
- Use these prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Write the message in the imperative, such as `feat: add read-only query executor`.
- "Working" means the code runs and the relevant tests pass. If something is unverified, say so.
- Only commit or push when the user asks.

### Pull requests

- When a feature is done, offer to help open a pull request with `gh pr create`.
- Describe what changed, why, and how it was tested.
- Only open the PR once the user confirms.

### Keeping this file updated

Update this file in the same branch as the change that makes it out of date:

- **Status:** when a milestone starts or finishes.
- **Open decisions:** when one is made.
- **Stack, structure, and conventions:** when they change.
- **How to run:** when a command starts working or changes.

Keep it accurate and concise. Don't list something as working until it's been run.
