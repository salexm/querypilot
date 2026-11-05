# QueryPilot

A natural-language-to-SQL analytics assistant. Ask a question in plain English, and QueryPilot generates SQL from your schema, runs it read-only against PostgreSQL, and shows the results as a table and an automatic chart.

> **Status:** early development. The repository is set up, and the application isn't built yet.

## Planned stack

- **Frontend:** React, Vite, TypeScript
- **Backend:** FastAPI
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

## License

The code is licensed under [MIT](LICENSE). The demo dataset keeps its own license.
