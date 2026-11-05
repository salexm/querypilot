import type { CellValue } from "../api/client";
import { formatFull } from "./chartData";

// Grouping digits would turn a year into "2,017" and an ID into a false quantity.
const UNGROUPED_COLUMN = /(^|_)(year|id|zip|code)($|_)/i;

export function formatCell(value: CellValue, column: string): string {
  if (value === null) {
    return "NULL";
  }
  if (typeof value === "number" && !UNGROUPED_COLUMN.test(column)) {
    return formatFull(value);
  }
  return String(value);
}
