import type { CellValue, ChartSpec } from "../api/client";

export interface ChartPoint {
  label: string;
  value: number | null;
}

const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}(T|$)/;
const compactFormat = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const fullFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export const formatCompact = (value: number): string => compactFormat.format(value);
export const formatFull = (value: number): string => fullFormat.format(value);

function compareCells(left: CellValue, right: CellValue): number {
  if (typeof left === "number" && typeof right === "number") {
    return left - right;
  }
  return String(left).localeCompare(String(right));
}

/** Use the shortest date label that still tells every point apart. */
function timeLabels(values: CellValue[]): string[] {
  const dates = values.map(String);
  if (!dates.every((date) => ISO_TIMESTAMP.test(date))) {
    return dates;
  }
  if (dates.every((date) => date.slice(4, 10) === "-01-01")) {
    return dates.map((date) => date.slice(0, 4));
  }
  if (dates.every((date) => date.slice(7, 10) === "-01")) {
    return dates.map((date) => date.slice(0, 7));
  }
  return dates.map((date) => date.slice(0, 10));
}

export function chartPoints(rows: CellValue[][], chart: ChartSpec): ChartPoint[] {
  const ordered =
    chart.type === "line"
      ? [...rows].sort((a, b) => compareCells(a[chart.x_column] ?? null, b[chart.x_column] ?? null))
      : rows;
  const xValues = ordered.map((row) => row[chart.x_column] ?? null);
  const labels = chart.type === "line" ? timeLabels(xValues) : xValues.map(String);
  return ordered.map((row, index) => {
    const value = row[chart.y_column];
    return { label: labels[index] ?? "", value: typeof value === "number" ? value : null };
  });
}

function humanize(column: string): string {
  return column.replaceAll("_", " ");
}

export function chartTitle(columns: string[], chart: ChartSpec): string {
  const title = `${humanize(columns[chart.y_column] ?? "")} by ${humanize(columns[chart.x_column] ?? "")}`;
  return title.charAt(0).toUpperCase() + title.slice(1);
}
