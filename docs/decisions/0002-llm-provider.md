# 0002: Use Anthropic Claude for SQL generation

**Status:** Accepted

## Decision

Use Anthropic Claude through the official Python SDK, with `claude-opus-5-5` as the default model. The model is set by `LLM_MODEL`, so a cheaper one can be used in development.

## Why

- Multi-table joins are the hard part of this dataset, and accuracy matters more than cost at this stage.
- Structured output returns SQL in a typed field, so nothing needs to be scraped from prose.

Ollama was considered for free local use, but it was dropped in favour of a hosted API. OpenAI wasn't compared directly. The Milestone 6 benchmark can test other providers and models.

## Consequences

- Each question costs money and needs an API key in `LLM_API_KEY`.
- Questions and the database schema are sent to Anthropic. Query results aren't.
- Provider code stays in `backend/app/llm/`, so adding a provider means a new adapter and a change to `factory.py`.
- Server-side refusal fallback is on for models that support it. It needs a beta header, which may change.
