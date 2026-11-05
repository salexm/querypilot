# QueryPilot

A natural-language-to-SQL analytics assistant. Ask a question in plain English, and QueryPilot generates SQL from your schema, runs it read-only against PostgreSQL, and shows the results as a table and an automatic chart.

> **Status:** early development. The API works, and the web app isn't built yet.

## Planned stack

- **Frontend:** React, Vite, TypeScript
- **Backend:** FastAPI, with Anthropic Claude generating the SQL
- **Database:** PostgreSQL
- **Local environment:** Docker Compose

## Configuration

Copy the environment template and fill in your own values:

```bash
cp .env.example .env
```

`.env` is ignored by git. Never commit real keys or passwords.

## Demo data

Start Postgres and load the demo dataset:

```bash
docker compose up -d --wait db
docker compose run --rm --build seed
```

The seed script downloads about 45 MB, verifies each file against a pinned checksum, and replaces the data in one transaction, so you can run it again safely.

QueryPilot uses the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). The raw data isn't stored in this repository. The seed script changes it slightly, as described in [the dataset decision](docs/decisions/0001-demo-dataset.md).

## Ask a question

Set `LLM_API_KEY` in `.env` to an [Anthropic API key](https://console.anthropic.com), then start the API:

```bash
docker compose up -d --build --wait api
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many orders were delivered?"}'
```

The response includes the generated SQL and the rows:

```json
{
  "question": "How many orders were delivered?",
  "sql": "SELECT COUNT(*) AS delivered_orders FROM orders WHERE order_status = 'delivered'",
  "columns": ["delivered_orders"],
  "rows": [[96478]],
  "row_count": 1,
  "truncated": false
}
```

## Query safety

Generated SQL passes through several independent protections:

- **Read-only role:** Queries run as a Postgres role with `SELECT` access only. This is the main protection.
- **Validator:** `sqlglot` parses each query and rejects anything except a single `SELECT` on known tables, including writes hidden inside a `WITH` clause.
- **Limits:** Every query has a statement timeout and a row cap, set by `QUERY_TIMEOUT_MS` and `QUERY_MAX_ROWS`.

Run the tests, including attacks against a real database, with `docker compose exec api pytest`.

## License

The code is licensed under [MIT](LICENSE). The demo dataset keeps its own license.
