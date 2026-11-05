import type { CellValue } from "../api/client";
import { formatCell } from "./formatCell";

interface ResultsTableProps {
  columns: string[];
  rows: CellValue[][];
}

function cellClass(value: CellValue): string | undefined {
  if (value === null) {
    return "cell-null";
  }
  return typeof value === "number" ? "cell-number" : undefined;
}

export function ResultsTable({ columns, rows }: ResultsTableProps) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Query results">
      <table>
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th key={index} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((value, columnIndex) => (
                <td key={columnIndex} className={cellClass(value)}>
                  {formatCell(value, columns[columnIndex] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
