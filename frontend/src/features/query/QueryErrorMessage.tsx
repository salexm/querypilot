import type { ApiError } from "../../api/client";
import { SqlViewer } from "../../components/SqlViewer";
import { errorContent } from "./errorContent";

interface QueryErrorMessageProps {
  error: ApiError;
}

export function QueryErrorMessage({ error }: QueryErrorMessageProps) {
  const { title, hint } = errorContent(error.code);

  return (
    <div className="stack">
      <div className="notice notice-error" role="alert">
        <h2>{title}</h2>
        <p>{hint}</p>
        <p className="notice-detail">{error.message}</p>
      </div>
      {error.sql && <SqlViewer sql={error.sql} label="SQL that didn't run" />}
    </div>
  );
}
