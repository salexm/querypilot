import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { chartPoints, chartTitle } from "./chartData";
import { formatCell } from "./formatCell";
import { ResultChart } from "./ResultChart";
import { ResultsTable } from "./ResultsTable";
import { SqlViewer } from "./SqlViewer";

describe("formatCell", () => {
  it.each([
    [96478, "orders", "96,478"],
    [1412089.534, "revenue", "1,412,089.53"],
    [2017, "year", "2017"],
    [2017, "order_year", "2017"],
    [12345, "seller_id", "12345"],
    [null, "revenue", "NULL"],
    [true, "active", "true"],
    ["SP", "state", "SP"],
  ])("formats %s in column %s", (value, column, expected) => {
    expect(formatCell(value, column)).toBe(expected);
  });
});

describe("ResultsTable", () => {
  it("shows headers, values, and nulls", () => {
    render(
      <ResultsTable
        columns={["state", "orders"]}
        rows={[
          ["SP", 41746],
          [null, 5],
        ]}
      />,
    );

    const table = within(screen.getByRole("table"));
    expect(table.getByRole("columnheader", { name: "state" })).toBeInTheDocument();
    expect(table.getByRole("cell", { name: "41,746" })).toBeInTheDocument();
    expect(table.getByRole("cell", { name: "NULL" })).toHaveClass("cell-null");
  });

  it("keeps duplicate column names", () => {
    render(<ResultsTable columns={["order_id", "order_id"]} rows={[["a", "b"]]} />);

    expect(screen.getAllByRole("columnheader", { name: "order_id" })).toHaveLength(2);
  });

  it("renders markup in data as plain text", () => {
    render(<ResultsTable columns={["note"]} rows={[["<img src=x onerror=alert(1)>"]]} />);

    expect(screen.getByRole("cell")).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

describe("SqlViewer", () => {
  it("highlights keywords and keeps the SQL text intact", () => {
    const sql = "SELECT count(*) FROM orders WHERE order_status = 'delivered'";
    render(<SqlViewer sql={sql} />);

    const region = screen.getByRole("region", { name: "Generated SQL" });
    expect(region.querySelector("code")?.textContent).toBe(sql);
    expect(within(region).getByText("SELECT")).toHaveClass("sql-keyword");
    expect(within(region).getByText("'delivered'")).toHaveClass("sql-string");
  });

  it("renders markup in SQL as plain text", () => {
    render(<SqlViewer sql="SELECT '<img src=x onerror=alert(1)>'" />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("copies the SQL", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    render(<SqlViewer sql="SELECT 1" />);

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith("SELECT 1");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("reports a failed copy", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    render(<SqlViewer sql="SELECT 1" />);

    await user.click(screen.getByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("button", { name: "Copy failed" })).toBeInTheDocument();
  });
});

describe("chartPoints", () => {
  const bar = { type: "bar", x_column: 0, y_column: 1 } as const;
  const line = { type: "line", x_column: 0, y_column: 1 } as const;

  it("keeps the SQL order for bars", () => {
    const points = chartPoints(
      [
        ["SP", 9],
        ["AC", 4],
      ],
      bar,
    );

    expect(points.map((point) => point.label)).toEqual(["SP", "AC"]);
  });

  it("sorts lines by time, whatever the SQL order", () => {
    const points = chartPoints(
      [
        [2018, 2],
        [2016, 1],
      ],
      line,
    );

    expect(points).toEqual([
      { label: "2016", value: 1 },
      { label: "2018", value: 2 },
    ]);
  });

  it.each([
    [["2017-01-01T00:00:00", "2018-01-01T00:00:00"], ["2017", "2018"]],
    [["2017-01-01T00:00:00", "2017-02-01T00:00:00"], ["2017-01", "2017-02"]],
    [["2017-01-01T00:00:00", "2017-01-02T00:00:00"], ["2017-01-01", "2017-01-02"]],
    [["2017-01", "2017-02"], ["2017-01", "2017-02"]],
  ])("labels %j as %j", (dates, expected) => {
    const points = chartPoints(
      dates.map((date) => [date, 1]),
      line,
    );

    expect(points.map((point) => point.label)).toEqual(expected);
  });

  it("uses the chosen columns and keeps missing values empty", () => {
    const points = chartPoints([[5, "SP", null]], { type: "bar", x_column: 1, y_column: 2 });

    expect(points).toEqual([{ label: "SP", value: null }]);
  });
});

describe("chartTitle", () => {
  it("names the measure and the dimension", () => {
    const chart = { type: "bar", x_column: 0, y_column: 1 } as const;

    expect(chartTitle(["customer_state", "total_orders"], chart)).toBe(
      "Total orders by customer state",
    );
  });
});

describe("ResultChart", () => {
  it("labels the chart for screen readers", () => {
    render(
      <ResultChart
        chart={{ type: "line", x_column: 0, y_column: 1 }}
        columns={["year", "revenue"]}
        rows={[
          [2017, 1],
          [2018, 2],
        ]}
      />,
    );

    expect(screen.getByRole("region", { name: "Revenue by year chart" })).toBeInTheDocument();
  });
});
