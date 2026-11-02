import { useState } from "react";

/**
 * Plain-language explanations for every score the dashboard shows, in one place so the same
 * name and wording are used everywhere. Written for someone who has never seen the code.
 */
export const GLOSSARY = {
  answer: {
    label: "SQL score",
    hint: "How well the SQL the assistant wrote answers the question, scored 0–10 by an AI reviewer who reads it. Higher is better; below 5 means the query is mostly wrong or misses the point. A reply with no SQL, SQL that does not parse, or SQL that is not read-only scores 0.",
  },
  context: {
    label: "Tables and columns",
    hint: "Whether the SQL used the tables and columns the test case expects, 0–10: the share of them it used. Blank when a test case expects none.",
  },
  time: {
    label: "Response time",
    hint: "How long the assistant took to reply to one question, from asking to final answer. Lower is better.",
  },
  steps: {
    label: "Timing of steps",
    hint: "Where the time goes: every stage the assistant goes through (for example finding the tables, then writing the SQL), with the average seconds each takes and its share of the whole response time. Time outside any step shows as “Not in a step”, and steps that run at the same time can add up to more than 100%.",
  },
  overall: {
    label: "Overall score",
    hint: "SQL score and tables and columns score combined into one number out of 10 (the mix is shown next to it). It decides the recommended version; speed only breaks near-ties.",
  },
  tolerance: {
    label: "Treat as tied within",
    hint: "Versions whose overall score is within this many points of the best are treated as equal, and the fastest of them is recommended.",
  },
  maxTime: {
    label: "Slowest allowed",
    hint: "Optional limit in seconds. Versions slower than this are not recommended, however well they score.",
  },
  checks: {
    label: "Checks",
    hint: "The program reads the SQL without running it: does it parse, is it read-only, does it use the expected tables and columns, and join the way the expected SQL does.",
  },
  failures: {
    label: "Where answers fail",
    hint: "How many replies failed each check, out of the questions that should be answered (or declined). Lower is better. The arrows show the change since the run before.",
  },
  tiers: {
    label: "How answers scored",
    hint: "Every question's SQL grouped by score: strong (8–10), fair (5–7) or weak (0–4).",
  },
  groupScores: {
    label: "Scores by group",
    hint: "Average scores for each group of test cases in this run. A test case in several groups counts in each of them, but only once in the version's overall scores.",
  },
} as const;

/** A small "i" that explains a term on hover or keyboard focus. Positioned on screen so tables never clip it. */
export function Hint({ text }: { text: string }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const show = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    const half = 130; // half the tooltip width, kept inside the window
    setPos({ x: Math.min(Math.max(r.left + r.width / 2, half + 8), window.innerWidth - half - 8), y: r.bottom + 6 });
  };
  return (
    <span className="relative ml-1 inline-flex align-middle">
      <span
        tabIndex={0}
        role="img"
        aria-label={text}
        onMouseEnter={(e) => show(e.currentTarget)}
        onMouseLeave={() => setPos(null)}
        onFocus={(e) => show(e.currentTarget)}
        onBlur={() => setPos(null)}
        onClick={(e) => e.stopPropagation()}
        className="grid h-3.5 w-3.5 cursor-help place-items-center rounded-full border border-muted text-[9px] font-semibold normal-case leading-none tracking-normal text-muted outline-none hover:border-brand hover:text-brand focus-visible:border-brand focus-visible:text-brand"
      >
        i
      </span>
      {pos && (
        <span
          role="tooltip"
          style={{ position: "fixed", left: pos.x, top: pos.y, transform: "translateX(-50%)", width: 260 }}
          className="pointer-events-none z-[70] rounded border border-line bg-surface p-2.5 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-fg shadow-lg"
        >
          {text}
        </span>
      )}
    </span>
  );
}

/** A label followed by its explanation, for column headers and stat cards. */
/** A glossary label with its info hint. `avg` writes it as an average ("Avg answer quality"), for columns that average many rows. */
export function Term({ k, avg = false }: { k: keyof typeof GLOSSARY; avg?: boolean }) {
  const label = GLOSSARY[k].label;
  return <>{avg ? `Avg ${label.charAt(0).toLowerCase()}${label.slice(1)}` : label}<Hint text={GLOSSARY[k].hint} /></>;
}
