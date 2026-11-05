# Contributing to QueryPilot

Thanks for your interest. Bug reports, ideas, and pull requests are all welcome.

## Set up

You need Docker and an [Anthropic API key](https://console.anthropic.com).

```bash
cp .env.example .env      # then set LLM_API_KEY and your own passwords
docker compose up --build
```

## Make a change

1. Create a branch from an up-to-date `main`, named by type, such as `feat/follow-up-questions` or `fix/row-cap`.
2. Keep the change focused on one thing.
3. Add tests with each feature, and a regression test with each bug fix.
4. Open a pull request that says what changed, why, and how you tested it.

Use [conventional commit](https://www.conventionalcommits.org/) prefixes, in the imperative: `feat: add read-only query executor`. The prefixes in use are `feat:`, `fix:`, `test:`, `docs:`, and `chore:`.

## Run the checks

CI runs all of these on every push and pull request.

```bash
docker compose exec api pytest      # backend tests
docker compose exec web npm test    # frontend tests
ruff check . && ruff format --check .
cd frontend && npm run lint && npm run build
```

Unit tests must never call a real LLM, so use the fake adapter in `backend/tests/fakes.py`.

## Safety rules

QueryPilot runs SQL written by an LLM, so these rules apply to every change:

- Run generated SQL only through the read-only database role.
- Never weaken the database role or the validator to make a query work.
- Validate SQL by parsing it with `sqlglot`, not with regex.
- Keep the statement timeout, row cap, and `/query` rate limits.
- Never commit keys, passwords, or `.env` files.
- Never put secrets in `VITE_*` variables, because they reach the browser.

## Change the benchmark

If a benchmark question fails, read the failure before trusting the score. Reword an ambiguous question if you need to, but never edit gold SQL to match generated SQL. Run `python -m eval.runner --check-gold` after changing questions.

Review benchmark reports before committing them, because they can contain full queries and results.

## Report a security problem

Please don't open a public issue for a way to bypass the SQL safety layers. Use [GitHub's private vulnerability reporting](https://github.com/salexm/querypilot/security/advisories/new) instead.
