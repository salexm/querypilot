const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type CellValue = string | number | boolean | null;

export interface ChartSpec {
  type: "bar" | "line";
  x_column: number;
  y_column: number;
}

export interface QueryResponse {
  question: string;
  sql: string;
  columns: string[];
  rows: CellValue[][];
  row_count: number;
  truncated: boolean;
  chart: ChartSpec | null;
}

export class ApiError extends Error {
  readonly code: string;
  readonly sql: string | null;

  constructor(code: string, message: string, sql: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.sql = sql;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isQueryResponse(body: unknown): body is QueryResponse {
  return (
    isRecord(body) &&
    typeof body.sql === "string" &&
    Array.isArray(body.columns) &&
    Array.isArray(body.rows)
  );
}

function toApiError(body: unknown): ApiError {
  if (isRecord(body) && typeof body.code === "string" && typeof body.message === "string") {
    return new ApiError(body.code, body.message, typeof body.sql === "string" ? body.sql : null);
  }
  return new ApiError("unexpected_response", "The API returned an unexpected response.");
}

async function send(question: string): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
  } catch {
    throw new ApiError("network_error", "Couldn't reach the API. Check that it's running.");
  }
}

export async function askQuestion(question: string): Promise<QueryResponse> {
  const response = await send(question);
  const body: unknown = await response.json().catch(() => null);
  if (response.ok && isQueryResponse(body)) {
    return body;
  }
  throw toApiError(body);
}
