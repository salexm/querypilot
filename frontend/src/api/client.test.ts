import { describe, expect, it, vi } from "vitest";

import { ApiError, askQuestion } from "./client";

function stubResponse(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

const success = {
  question: "How many?",
  sql: "SELECT 1",
  columns: ["total"],
  rows: [[1]],
  row_count: 1,
  truncated: false,
  chart: null,
};

describe("askQuestion", () => {
  it("posts the question and returns the response", async () => {
    stubResponse(200, success);

    await expect(askQuestion("How many?")).resolves.toEqual(success);

    const [url, options] = vi.mocked(fetch).mock.calls[0] ?? [];
    expect(url).toMatch(/\/query$/);
    expect(options?.method).toBe("POST");
    expect(options?.body).toBe(JSON.stringify({ question: "How many?" }));
  });

  it("keeps the code, message, and SQL from API errors", async () => {
    stubResponse(422, { code: "invalid_sql", message: "Blocked.", sql: "DROP TABLE orders" });

    const error = await askQuestion("Drop it").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "invalid_sql",
      message: "Blocked.",
      sql: "DROP TABLE orders",
    });
  });

  it("reports unexpected error bodies", async () => {
    stubResponse(422, { detail: [{ msg: "Field required" }] });

    await expect(askQuestion("x")).rejects.toMatchObject({ code: "unexpected_response" });
  });

  it("reports a success status with the wrong body", async () => {
    stubResponse(200, { hello: "world" });

    await expect(askQuestion("x")).rejects.toMatchObject({ code: "unexpected_response" });
  });

  it("reports responses that aren't JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })));

    await expect(askQuestion("x")).rejects.toMatchObject({ code: "unexpected_response" });
  });

  it("reports network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(askQuestion("x")).rejects.toMatchObject({ code: "network_error" });
  });
});
