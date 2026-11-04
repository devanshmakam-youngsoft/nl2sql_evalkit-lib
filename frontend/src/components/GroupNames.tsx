/** The groups a run covered, as small tags. A run can cover dozens, so only the first few are shown and the rest
 *  are counted (the full list is the tooltip), which keeps every row and card the same height. */
export function GroupNames({ names, max = 3, className = "" }: { names: string[]; max?: number; className?: string }) {
  if (names.length === 0) return null;
  const shown = names.slice(0, max);
  const rest = names.slice(max);
  const tag = "inline-block max-w-[140px] truncate rounded border border-line bg-surface-2 px-1.5 py-0.5 align-middle text-[10px] font-medium text-muted";
  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {shown.map((n) => <span key={n} title={n} className={tag}>{n}</span>)}
      {rest.length > 0 && <span title={rest.join(", ")} className={`${tag} cursor-default`}>+{rest.length} more</span>}
    </div>
  );
}
