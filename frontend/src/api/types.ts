/** Pipeline nodes are data, not code: whatever the RAG app reports shows up here. */
export interface NodeAvg {
  name: string;
  avg: number;
}

export interface VersionSummary {
  version: string | number;
  run_id: string;
  date: string;
  duration_seconds: number;
  dataset: string;
  total_rows: number;
  failed_rows: number;
  avg_sql_marks: number | null;
  avg_schema_marks: number | null;
  /** Mean schema lookup score; null when no step recorded the schema the assistant looked at. */
  avg_lookup_marks?: number | null;
  /** Mean reply score; null when no reply was scored against a reply style. */
  avg_reply_marks?: number | null;
  avg_total_time: number | null;
  comment: string;
  /** Problems met during the run, and the name of its log file (see the Download log link). */
  issues?: Issue[];
  issue_total?: number;
  log_file?: string | null;
  /** Average seconds per node, in pipeline order (only nodes that ran in that version). */
  nodes: NodeAvg[];
  archived?: boolean;
  /** The run was stopped early; it is never recommended or compared as a finished run. */
  stopped?: boolean;
  /** What needs attention and what to try next, written for a non-technical reader. */
  insights?: { pitfalls: string[]; suggestions: string[]; items?: { watch_out: string; suggestion: string }[] };
  /** Short "what changed?" note entered when the run was started. */
  notes?: string;
  /** Names of the test case groups used in this run. */
  group_names?: string[];
  /** Per-group score breakdown (present when the run covered named test-case groups). */
  /** Detailed scores saved with the run: tiers, per type, and what the checks on the SQL found. */
  scores?: { checks: CheckCounts };
  group_stats?: Record<string, {
    avg_sql_marks: number | null;
    avg_schema_marks: number | null;
    avg_lookup_marks?: number | null;
    avg_reply_marks?: number | null;
    avg_total_time: number | null;
    total_rows: number;
    failed_rows?: number;
  }>;
}

/** How many replies of a run failed each check; `answers` and `declines` are what the other counts are out of. */
export interface CheckCounts {
  answers: number;
  no_sql: number;
  syntax_failed: number;
  not_read_only: number;
  tables_missing: number;
  columns_missing: number;
  joins_differ: number;
  declines: number;
  declines_with_sql: number;
  /** Replies whose step recorded a schema, and how many of those lacked an expected table or column (older runs have neither). */
  lookup_graded?: number;
  lookup_missed?: number;
  /** Written replies scored against a reply style, and how many of those scored under 5 (older runs have neither). */
  reply_graded?: number;
  reply_weak?: number;
}

/** The server's answer to "which version should ship?" (version ids are strings). */
export interface RecoResult {
  best: string | null;
  reason: string;
  fastest: string | null;
  runner_up: string | null;
  latest_gap: { version: string; gap: number } | null;
  /** The newest run against the recommended one (null when the newest run is the recommended one, or was not compared). */
  latest_vs_best: { version: string; answer: number | null; schema_use: number | null; time: number | null; quality: number | null } | null;
  /** What was recommended before the newest run. */
  previous_best: string | null;
  /** Nothing reached `min_quality`: no recommendation, but the best so far is named. */
  min_quality: number;
  below_minimum: boolean;
  best_so_far: { version: string; quality: number } | null;
  not_comparable: string[];
  /** What each version that could not be compared scored on its own test cases. */
  not_comparable_scores: Record<string, { answer: number | null; schema_use: number | null; time: number | null; cases: number }>;
  /** Why each version in `not_comparable` was left out. */
  not_comparable_detail: Record<string, string>;
  excluded: string[];
  excluded_detail: Record<string, string>;
  budget_miss: boolean;
  /** "weighted" = answer + tables and columns; "answer_only" = tables and columns were not graded for every version. */
  basis: "weighted" | "answer_only";
  basis_note: string;
  weights: { answer: number; schema_use: number };
  tolerance: number;
  max_time: number | null;
  qualities: Record<string, number | null>;
  considered: number;
  /** How many test cases the comparison was made on: the ones every compared version ran. */
  compared_cases: number | null;
  /** Versions that ran more test cases than were compared (judged on the shared ones only). */
  partial: { version: string; ran: number; compared: number }[];
  /** Each compared version's scores on the shared test cases. */
  scores: Record<string, { answer: number | null; schema_use: number | null; time: number | null; cases: number; quality: number | null }>;
}

/** One group's scores in one run. */
export interface GroupRunStat {
  version: string;
  date: string;
  total_rows: number;
  failed_rows: number;
  avg_sql_marks: number | null;
  avg_schema_marks: number | null;
  avg_total_time: number | null;
  quality: number | null;
  stopped: boolean;
}

export interface GroupHistory {
  group: Group;
  run_count: number;
  last: GroupRunStat | null;
  best: GroupRunStat | null;
  reason: string;
  basis_note: string;
  compared_cases?: number | null;
  runs: GroupRunStat[];
}

export interface ResultRow {
  chat_id: string;
  session_id: string | null;
  turn_no: number;
  type: string;
  question: string;
  expected_sql: string;
  expected_tables?: string;
  expected_columns?: string;
  intent: string | null;
  generated_answer: string | null;
  status: string;
  total_time_taken: number | null;
  /** Seconds per node for this question, in execution order. */
  node_timings: Record<string, number>;
  sql_marks: number | null;
  sql_remarks: string | null;
  schema_marks: number | null;
  schema_remarks: string | null;
  /** The tables and columns the assistant looked at (recorded by a step), what that schema had or lacked, and its score. */
  schema_context?: string;
  schema_lookup?: SchemaLookup;
  lookup_marks?: number | null;
  lookup_remarks?: string;
  /** Why the judge thinks the SQL is wrong: "schema_lookup", "sql", "both" or "none". */
  sql_cause?: string;
  /** The reply style the question was scored with, the written reply, and its score with the reason and a suggestion. */
  reply_style?: string;
  reply_text?: string;
  reply_marks?: number | null;
  reply_remarks?: string;
  reply_suggestion?: string;
  /** Groups this test case belonged to when it ran. */
  groups?: string[];
  /** Set when the test case has been deleted since this version ran (the question and answer here are kept). */
  case_deleted?: boolean;
  /** Set when the question could not be answered or graded: a plain message, and the technical text on request. */
  error_message?: string;
  error_detail?: string;
  /** Free-form notes attached via nl2sql_evalkit.note() during the pipeline run. */
  flags?: Record<string, string>;
  /** The SQL in the reply, without any text around it (empty when there is none). */
  generated_sql?: string;
  /** The one change the judge suggests. */
  sql_suggestion?: string;
  /** What the checks on the SQL found. The SQL is read, never run. */
  sql_checks?: SqlChecks;
}

/** Which of the expected tables and columns were in the schema the assistant looked at. `graded` is false when nothing was scored. */
export interface SchemaLookup {
  graded: boolean;
  tables_found: string[];
  tables_missing: string[];
  columns_found: string[];
  columns_missing: string[];
}

/** The findings of the checks on one reply. `null` means the check did not apply. */
export interface SqlChecks {
  sql: string;
  message: string;
  returned_sql: boolean;
  syntax_ok: boolean | null;
  syntax_error: string;
  read_only: boolean | null;
  read_only_problem: string;
  tables_used: string[];
  columns_used: string[];
  star: boolean;
  tables_missing: string[] | null;
  columns_missing: string[] | null;
  joins_match: boolean | null;
  joins_missing: string[];
  joins_extra: string[];
}

/** A problem met while something ran: `message` is for anyone, `technical` is shown on request. */
export interface Issue {
  stage: string;
  where: string;
  message: string;
  technical: string;
  severity: "error" | "warning";
  at: string;
  /** How many times the same problem happened. */
  count: number;
}

/** What the dashboard calls itself, as set on the server. */
export interface AppInfo {
  name: string;
}

/** What the server has switched on: the guide (serve(show_guide=...)). */
export interface Features {
  guide: boolean;
}

export interface VersionDetail {
  summary: VersionSummary;
  rows: ResultRow[];
}

export interface RunState {
  run_id: string;
  version: string;
  status: "running" | "completed" | "failed" | "stopped";
  total: number;
  done: number;
  current_question: string;
  date: string;
  dataset: string;
  error: string | null;
  /** The technical version of `error`, shown on request. */
  error_detail?: string;
  issue_count?: number;
}

export interface DatasetInfo {
  name: string;
  rows: number;
  chats: number;
  required_columns?: string[];
}

export interface Group {
  group_id: string;
  name: string;
  created_at: string;
  member_count: number;
  /** Set when the group has been deleted (hidden but kept; can be restored). */
  deleted_at?: string | null;
  /** Present on the groups list: how the group has done across non-archived runs. */
  run_count?: number;
  last_run?: GroupRunStat | null;
  best_run?: GroupRunStat | null;
}

/** Backward-compat alias — prefer Group in new code. */
export type Dataset = Group;

/** A group label on a test case. */
export interface GroupRef {
  group_id: string;
  name: string;
}

export interface TestCase {
  tc_id: string;
  chat_id: string;
  turn_no: number;
  question: string;
  expected_sql: string;
  expected_tables?: string;
  expected_columns?: string;
  /** How the assistant's written reply should read; when set, the reply is scored too. */
  reply_style?: string;
  type: string;
  status: "active" | "inactive";
  version: number;
  created_at: string;
  updated_at?: string;
  /** Group labels this case carries (a case can have any number). */
  groups: GroupRef[];
  /** Set on cases written from a schema file: which file and category, and why a vague or unsafe question is one. */
  origin?: { kind: string; file: string; model?: string; category?: string; needs_context?: string; note?: string };
}

/** Writing test cases from schema files. */
export interface GenCategory { key: string; label: string }

export interface GenLimits {
  max_files: number;
  max_file_mb: number;
  per_category_max: number;
  per_category_default: number;
  turns_default: number;
  categories: GenCategory[];
  model: string;
  dialect: string;
  ttl_hours: number;
  formats: string[];
}

/** One turn of a generated item. A vague or unsafe question has a `note` and no SQL. */
export interface GenTurn { question: string; expected_sql?: string; expected_tables?: string; expected_columns?: string; note?: string; needs_context?: string }
export interface GenItem { item_id: string; category: string; file: string; number: number; type?: string; turns: GenTurn[] }

export interface GenBatch {
  batch_id: string;
  status: "running" | "ready" | "failed" | "cancelled" | "interrupted";
  created_at: string;
  expires_at: string;
  options: { per_category: number; categories: string[]; turns: number };
  model: string;
  files: { name: string; tables?: number; relations?: number; skipped?: string[]; error?: string }[];
  total_tasks: number;
  done_tasks: number;
  items: GenItem[];
  errors: { category: string; file: string; reason: string; detail?: string }[];
  error: string;
  error_detail?: string;
}

/** A batch without its items: what the "waiting for review" banner needs. */
export type GenSummary = Omit<GenBatch, "items"> & { item_count: number; case_count: number; by_category: Record<string, number> };

/** The fields a test case import understands, and which file column feeds each. */
export type ImportMapping = Record<string, string | null>;

export interface ImportProblem {
  /** Row number as shown in the spreadsheet (the header is row 1). */
  row: number;
  reason: string;
  cells: Record<string, string>;
}

export interface ImportPreview {
  filename: string;
  sheets: string[];
  sheet: string | null;
  columns: string[];
  mapping: ImportMapping;
  fields: string[];
  field_labels: Record<string, string>;
  ignored_columns: string[];
  question_missing: boolean;
  auto_chat: boolean;
  auto_turn: boolean;
  total_rows: number;
  counts: { new: number; update: number; unchanged: number; problem: number };
  slot_conflicts: number;
  sample: { row: number; chat_id: string; turn_no: number; question: string; expected_sql: string; groups: string[]; outcome: string }[];
  problems: ImportProblem[];
  group_names_in_file: string[];
  new_group_names: string[];
}

export interface ImportResult {
  new: number;
  updated: number;
  unchanged: number;
  slot_conflicts: number;
  labelled: number;
  groups_created: string[];
  problems: number;
  problem_rows: ImportProblem[];
  columns: string[];
}

/** What a run should execute: groups and/or individually picked test cases. */
export interface RunSelection {
  groupIds?: string[];
  tcIds?: string[];
  statusFilter?: string;
  includeContext?: boolean;
}

export interface RunPreview {
  selected: number;
  context: number;
  total: number;
  missing: number;
  group_names: string[];
  collisions: { chat_id: string; turn_no: number; tc_ids: string[] }[];
}
