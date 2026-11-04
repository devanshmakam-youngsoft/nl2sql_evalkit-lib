import { Term } from "./Hint";
import type { ResultRow } from "../api/types";

const CAUSES: Record<string, string> = {
  schema_lookup: "the schema lookup missed something",
  sql: "the SQL went wrong",
  both: "both the lookup and the SQL",
};

/** The judge's reading of why a query is wrong, as a small tag; nothing when it found no cause. */
export function CauseTag({ cause }: { cause?: string | null }) {
  if (!cause || !CAUSES[cause]) return null;
  return <span className="rounded border border-line bg-surface-2 px-1.5 py-0.5 text-xs font-medium">{CAUSES[cause]}</span>;
}

function Names({ label, found, missing }: { label: string; found: string[]; missing: string[] }) {
  if (found.length + missing.length === 0) return null;
  return (
    <div className="flex flex-wrap items-baseline gap-1.5 text-xs">
      <span className="w-16 shrink-0 text-muted">{label}</span>
      {found.map((n) => <span key={`f${n}`} className="rounded border border-line px-1.5 py-0.5 text-good" title="in the schema the assistant looked at">✓ {n}</span>)}
      {missing.map((n) => <span key={`m${n}`} className="rounded border border-bad px-1.5 py-0.5 text-bad" title="not in the schema the assistant looked at">✗ {n}</span>)}
    </div>
  );
}

/** The tables and columns the assistant looked at before writing the SQL, and which expected ones that schema had or lacked. */
export function SchemaLookupBlock({ row }: { row: ResultRow }) {
  if (!row.schema_context) return null;
  const lookup = row.schema_lookup;
  return (
    <div className="mt-5">
      <div className="label mb-1.5">Schema the assistant looked at <Term k="lookup" /></div>
      {lookup?.graded && (
        <div className="mb-2 space-y-1.5">
          <Names label="Tables" found={lookup.tables_found} missing={lookup.tables_missing} />
          <Names label="Columns" found={lookup.columns_found} missing={lookup.columns_missing} />
        </div>
      )}
      <div className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-3.5 font-mono text-xs leading-relaxed">{row.schema_context}</div>
    </div>
  );
}
