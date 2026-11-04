import { Term } from "./Hint";
import type { ResultRow } from "../api/types";

/** The written reply that came with the SQL and the style it was asked to have; nothing when no reply style applied. */
export function ReplyBlock({ row }: { row: ResultRow }) {
  if (!row.reply_style) return null;
  return (
    <div className="mt-5">
      <div className="label mb-1.5">Written reply <Term k="reply" /></div>
      <div className="mb-2 max-h-20 overflow-auto break-words text-xs text-muted">Asked to be: <span className="text-fg">{row.reply_style}</span></div>
      {row.reply_text
        ? <div className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded bg-surface-2 p-3.5 text-sm leading-relaxed">{row.reply_text}</div>
        : <div className="text-sm text-muted">The assistant returned no written reply.</div>}
    </div>
  );
}
