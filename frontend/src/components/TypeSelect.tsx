/** What the assistant should do with a question. Values found in older data are kept as they are. */
export const CASE_TYPES = [
  { value: "answer", label: "answer", hint: "A clear question: the assistant should return SQL." },
  { value: "clarify", label: "clarify", hint: "A vague question: the assistant should ask something back instead of guessing." },
  { value: "refuse", label: "refuse", hint: "A harmful or out-of-bounds question: the assistant should decline." },
] as const;

/** Type of a test case: answer, clarify or refuse. An existing value that is none of them stays selectable so nothing is silently changed. */
export function TypeSelect({ value, onChange, className = "" }: { value: string; onChange: (v: string) => void; className?: string }) {
  const known = CASE_TYPES.some((t) => t.value === value);
  const hint = CASE_TYPES.find((t) => t.value === value)?.hint;
  return (
    <select value={value || "answer"} onChange={(e) => onChange(e.target.value)} title={hint} aria-label="Type"
      className={`w-full rounded border border-line bg-surface-2 px-3 py-2 text-sm outline-none focus:border-brand ${className}`}>
      {CASE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
      {!known && value && <option value={value}>{value}</option>}
    </select>
  );
}
