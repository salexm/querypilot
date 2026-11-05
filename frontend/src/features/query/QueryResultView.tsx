import type { QueryResponse } from "../../api/client";
import { ResultChart } from "../../components/ResultChart";
import { ResultsTable } from "../../components/ResultsTable";
import { SqlViewer } from "../../components/SqlViewer";

interface QueryResultViewProps {
  result: QueryResponse;
}

function rowSummary(count: number): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? "row" : "rows"}`;
}

export function QueryResultView({ result }: QueryResultViewProps) {
  return (
    <div className="stack">
      <SqlViewer sql={result.sql} />
      {result.row_count === 0 ? (
        <div className="notice">
          <h2>No matching rows</h2>
          <p>The query ran, but nothing matched. Try a broader question.</p>
        </div>
      ) : (
        <>
          {result.chart && (
            <ResultChart chart={result.chart} columns={result.columns} rows={result.rows} />
          )}
          <section aria-label="Results" className="stack-tight">
            <div className="results-header">
              <h2>Results</h2>
              <span className="muted">{rowSummary(result.row_count)}</span>
            </div>
            {result.truncated && (
              <p className="notice notice-warning">
                Showing the first {rowSummary(result.row_count)}. More rows matched, so add a filter
                to see them.
              </p>
            )}
            <ResultsTable columns={result.columns} rows={result.rows} />
          </section>
        </>
      )}
    </div>
  );
}
