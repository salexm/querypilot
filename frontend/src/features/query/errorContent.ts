interface ErrorContent {
  title: string;
  hint: string;
}

const ERROR_CONTENT: Record<string, ErrorContent> = {
  rate_limited: {
    title: "Please slow down a little",
    hint: "This public demo limits how often each visitor can ask, to keep it free to run.",
  },
  daily_limit_reached: {
    title: "The demo is resting",
    hint: "This public demo has a daily budget, and today's has been used.",
  },
  invalid_question: {
    title: "That question can't be sent",
    hint: "Try a shorter question.",
  },
  unanswerable_question: {
    title: "This data can't answer that",
    hint: "Try asking about orders, products, sellers, customers, payments, or reviews.",
  },
  invalid_sql: {
    title: "Query blocked for safety",
    hint: "Only read-only queries on this dataset can run. Nothing was executed.",
  },
  query_failed: {
    title: "The query failed",
    hint: "The generated SQL didn't run. Rewording the question may help.",
  },
  query_timeout: {
    title: "The query took too long",
    hint: "Try narrowing the question, such as to one year or one state.",
  },
  database_unavailable: {
    title: "The database isn't available",
    hint: "Check that the database is running and the dataset is loaded.",
  },
  llm_not_configured: {
    title: "The LLM isn't set up",
    hint: "Check LLM_API_KEY and LLM_MODEL in your .env file.",
  },
  llm_failed: {
    title: "SQL couldn't be generated",
    hint: "The LLM provider had a problem. Try again in a moment.",
  },
  network_error: {
    title: "Couldn't reach the API",
    hint: "Check that the API is running on the expected address.",
  },
};

const FALLBACK: ErrorContent = {
  title: "Something went wrong",
  hint: "Try again in a moment.",
};

export function errorContent(code: string): ErrorContent {
  return ERROR_CONTENT[code] ?? FALLBACK;
}
