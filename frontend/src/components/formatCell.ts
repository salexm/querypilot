import type { CellValue } from "../api/client";

const numberFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

// Grouping digits would turn a year into "2,017" and an ID into a false quantity.
const UNGROUPED_COLUMN = /(^|_)(year|id|zip|code)($|_)/i;

export function formatCell(value: CellValue, column: string): string {
  if (value === null) {
    return "NULL";
  }
  if (typeof value === "number" && !UNGROUPED_COLUMN.test(column)) {
    return numberFormat.format(value);
  }
  return String(value);
}
