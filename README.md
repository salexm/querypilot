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

## License

[MIT](LICENSE)
