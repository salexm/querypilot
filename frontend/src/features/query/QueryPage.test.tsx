import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryPage } from "./QueryPage";

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <QueryPage />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

function stubApi(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status })),
  );
}

function result(overrides: object = {}) {
  return {
    question: "How many?",
    sql: "SELECT count(*) AS total FROM orders",
    columns: ["total"],
    rows: [[99441]],
    row_count: 1,
    truncated: false,
    chart: null,
    ...overrides,
  };
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "How many?") {
  await user.type(screen.getByLabelText("Your question"), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

describe("QueryPage", () => {
  it("starts with example questions and a disabled button", () => {
    renderPage();

    expect(screen.getByRole("region", { name: "Example questions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("shows the question, SQL, and rows in the thread", async () => {
    stubApi(200, result());
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("cell", { name: "99,441" })).toBeInTheDocument();
    expect(screen.getByText("How many?")).toHaveClass("user-message");
    expect(screen.getByRole("region", { name: "Generated SQL" })).toHaveTextContent(
      "SELECT count(*) AS total FROM orders",
    );
    expect(screen.getByText("1 row")).toBeInTheDocument();
  });

  it("clears the input and hides the examples after sending", async () => {
    stubApi(200, result());
    const user = renderPage();

    await ask(user);

    expect(screen.getByLabelText("Your question")).toHaveValue("");
    expect(screen.queryByRole("region", { name: "Example questions" })).not.toBeInTheDocument();
  });

  it("sends with Enter and adds a line with Shift+Enter", async () => {
    stubApi(200, result());
    const user = renderPage();
    const input = screen.getByLabelText("Your question");

    await user.type(input, "first{Shift>}{Enter}{/Shift}second");
    expect(input).toHaveValue("first\nsecond");
    expect(fetch).not.toHaveBeenCalled();

    await user.type(input, "{Enter}");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps earlier answers when asking again", async () => {
    stubApi(200, result());
    const user = renderPage();
    await ask(user, "First question");
    await screen.findByRole("cell", { name: "99,441" });

    stubApi(200, result({ rows: [[7]] }));
    await ask(user, "Second question");

    expect(await screen.findByRole("cell", { name: "7" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "99,441" })).toBeInTheDocument();
    expect(screen.getByText("First question")).toBeInTheDocument();
  });

  it("shows a loading state and blocks a second send", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetchStub = vi.fn(() => new Promise<Response>((resolve) => (finish = resolve)));
    vi.stubGlobal("fetch", fetchStub);
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("status")).toHaveTextContent("Writing SQL");
    await user.type(screen.getByLabelText("Your question"), "Another{Enter}");
    expect(fetchStub).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Your question")).toHaveValue("Another");

    finish(new Response(JSON.stringify(result())));
    expect(await screen.findByRole("cell", { name: "99,441" })).toBeInTheDocument();
  });

  it("asks an example question when clicked", async () => {
    stubApi(200, result());
    const user = renderPage();
    const example = "How many customers ordered more than once?";

    await user.click(screen.getByRole("button", { name: example }));

    expect(await screen.findByRole("cell", { name: "99,441" })).toBeInTheDocument();
    expect(screen.getByText(example)).toHaveClass("user-message");
  });

  it("ignores blank questions", async () => {
    const fetchStub = vi.fn();
    vi.stubGlobal("fetch", fetchStub);
    const user = renderPage();

    await user.type(screen.getByLabelText("Your question"), "   {Enter}");

    expect(fetchStub).not.toHaveBeenCalled();
  });

  it("shows a chart when the API picks one", async () => {
    stubApi(
      200,
      result({
        columns: ["state", "orders"],
        rows: [
          ["SP", 9],
          ["RJ", 4],
        ],
        row_count: 2,
        chart: { type: "bar", x_column: 0, y_column: 1 },
      }),
    );
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("region", { name: "Orders by state chart" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows no chart when the API picks none", async () => {
    stubApi(200, result());
    const user = renderPage();

    await ask(user);

    await screen.findByRole("table");
    expect(screen.queryByRole("region", { name: /chart/ })).not.toBeInTheDocument();
  });

  it("explains when no rows match", async () => {
    stubApi(200, result({ rows: [], row_count: 0 }));
    const user = renderPage();

    await ask(user);

    expect(await screen.findByText("No matching rows")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("warns when results are truncated", async () => {
    stubApi(200, result({ row_count: 1000, truncated: true }));
    const user = renderPage();

    await ask(user);

    expect(await screen.findByText(/Showing the first 1,000 rows/)).toBeInTheDocument();
  });

  it("shows blocked SQL without claiming it ran", async () => {
    stubApi(422, { code: "invalid_sql", message: "Drop isn't allowed.", sql: "DROP TABLE orders" });
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Query blocked for safety");
    expect(screen.getByRole("region", { name: "SQL that didn't run" })).toHaveTextContent(
      "DROP TABLE orders",
    );
  });

  it.each([
    ["unanswerable_question", "This data can't answer that"],
    ["query_timeout", "The query took too long"],
    ["llm_failed", "SQL couldn't be generated"],
    ["some_new_code", "Something went wrong"],
  ])("explains the %s error", async (code, title) => {
    stubApi(500, { code, message: "Details.", sql: null });
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(title);
  });

  it("explains when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const user = renderPage();

    await ask(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach the API");
  });

  it("lets the user ask again after an error", async () => {
    stubApi(502, { code: "llm_failed", message: "Rate limited.", sql: null });
    const user = renderPage();
    await ask(user);
    await screen.findByRole("alert");

    stubApi(200, result());
    await ask(user, "Try again");

    expect(await screen.findByRole("cell", { name: "99,441" })).toBeInTheDocument();
  });
});
