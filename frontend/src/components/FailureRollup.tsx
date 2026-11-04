import { Term } from "./Hint";
import { plural } from "../lib/format";
import type { CheckCounts, VersionSummary } from "../api/types";

/** The ways a reply can fail the checks, with the count it belongs to ("answers" or "declines"). */
const FAILURES: { key: keyof CheckCounts; label: string; of: "answers" | "declines" | "lookup_graded" | "reply_graded" }[] = [
  { key: "no_sql", label: "No SQL in the reply", of: "answers" },
  { key: "syntax_failed", label: "SQL does not parse", of: "answers" },
  { key: "not_read_only", label: "SQL is not read-only", of: "answers" },
  { key: "tables_missing", label: "Expected table left out", of: "answers" },
  { key: "columns_missing", label: "Expected column left out", of: "answers" },
  { key: "joins_differ", label: "Joins differ from the expected SQL", of: "answers" },
  { key: "declines_with_sql", label: "Should have declined but wrote SQL", of: "declines" },
  { key: "lookup_missed", label: "Schema lookup missed an expected table or column", of: "lookup_graded" },
  { key: "reply_weak", label: "Reply off the requested style", of: "reply_graded" },
];

const NOUNS = { answers: "answer", declines: "decline", lookup_graded: "question", reply_graded: "reply" } as const;

const share = (n: number, of: number) => (of > 0 ? Math.round((n / of) * 100) : 0);

/** The sentence that names the biggest change between the last two runs: "v3 fixed joins but broke columns". */
function headline(runs: VersionSummary[]): string | null {
  if (runs.length < 2) return null;
  const [before, after] = runs.slice(-2);
  const a = before.scores?.checks, b = after.scores?.checks;
  if (!a || !b) return null;
  const rate = (c: CheckCounts, f: (typeof FAILURES)[number]) => share(c[f.key] ?? 0, c[f.of] ?? 0);
  const fixed: string[] = [], broke: string[] = [];
  for (const f of FAILURES) {
    const change = rate(b, f) - rate(a, f);
    if (change <= -10) fixed.push(f.label.toLowerCase());
    else if (change >= 10) broke.push(f.label.toLowerCase());
  }
  if (!fixed.length && !broke.length) return `v${after.version} fails about the same checks as v${before.version}.`;
  const parts = [fixed.length ? `fixed: ${fixed.join(", ")}` : "", broke.length ? `broke: ${broke.join(", ")}` : ""].filter(Boolean);
  return `v${after.version} compared with v${before.version} · ${parts.join(" · ")}`;
}

/** Which checks the replies fail, for one run or several side by side. A cell is the share of replies that failed,
 *  so runs with different numbers of questions can be read together; lower is better. */
export function FailureRollup({ runs }: { runs: VersionSummary[] }) {
  const withChecks = runs.filter((r) => r.scores?.checks);
  if (withChecks.length === 0) return null;
  const rows = FAILURES.filter((f) => withChecks.some((r) => (r.scores!.checks[f.of] ?? 0) > 0));
  const note = headline(withChecks);

  return (
    <section className="card mt-4 overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <h3 className="label"><Term k="failures" /></h3>
        <p className="mt-1 text-xs text-muted">
          {note ?? "How many replies failed each check. The SQL is read, never run."}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface-2 text-[11px] uppercase tracking-[0.08em] text-muted">
            <tr>
              <th className="px-5 py-3 font-medium">Check</th>
              {withChecks.map((r) => <th key={r.run_id} className="px-4 py-3 text-center font-medium"><span className="mono text-brand">v{r.version}</span></th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.length === 0 && (
              <tr><td colSpan={withChecks.length + 1} className="px-5 py-4 text-sm text-good">No reply failed a check.</td></tr>
            )}
            {rows.map((f) => (
              <tr key={f.key}>
                <td className="px-5 py-2.5 text-[13px]">{f.label}</td>
                {withChecks.map((r, i) => {
                  const c = r.scores!.checks;
                  const n = c[f.key] ?? 0, total = c[f.of] ?? 0;
                  const before = i > 0 ? withChecks[i - 1].scores!.checks : null;
                  const change = before ? share(n, total) - share(before[f.key] ?? 0, before[f.of] ?? 0) : 0;
                  return (
                    <td key={r.run_id} className="px-4 py-2.5 text-center" title={`${plural(n, NOUNS[f.of], f.of === "reply_graded" ? "replies" : undefined)} of ${total}`}>
                      <span className={`num ${n === 0 ? "text-muted" : "font-medium text-fg"}`}>{n}</span>
                      <span className="mono ml-1 text-[11px] text-muted">of {total}</span>
                      {before && change !== 0 && (
                        <span className={`mono ml-2 text-[11px] ${change < 0 ? "text-good" : "text-bad"}`}>{change < 0 ? "▼" : "▲"}{Math.abs(change)}%</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
