import { useState } from "react";
import { getSegments } from "sql-highlight";

interface SqlViewerProps {
  sql: string;
  label?: string;
}

type CopyStatus = "idle" | "copied" | "failed";

const COPY_LABELS: Record<CopyStatus, string> = {
  idle: "Copy",
  copied: "Copied",
  failed: "Copy failed",
};

export function SqlViewer({ sql, label = "Generated SQL" }: SqlViewerProps) {
  const [status, setStatus] = useState<CopyStatus>("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  return (
    <section className="sql-viewer" aria-label={label}>
      <div className="sql-header">
        <h2>{label}</h2>
        <button type="button" className="button-quiet" onClick={() => void copy()}>
          {COPY_LABELS[status]}
        </button>
      </div>
      <pre tabIndex={0}>
        <code>
          {getSegments(sql).map((segment, index) => (
            <span key={index} className={`sql-${segment.name}`}>
              {segment.content}
            </span>
          ))}
        </code>
      </pre>
    </section>
  );
}
