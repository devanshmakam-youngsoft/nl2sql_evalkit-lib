"""The instructions for the findings of a run: each watch-out paired with the suggestion that answers it."""


run_summary_prompt = """You are reviewing the results of one evaluation run of an assistant that turns questions into SQL, for the
person who maintains it. The reader already sees the headline averages (SQL score, tables and columns score, speed) on
screen, so do NOT restate them and do not open with an overall verdict. Point out what needs attention and what to do
about it, using the numbers provided only as evidence.

Give 2-5 findings, the most important first. Each finding has two parts that belong together:
watch_out: ONE concrete weakness and the evidence for it: which group or question type scored lowest, which questions
scored poorly and what their SQL got wrong (a join, a filter, a column), SQL that did not parse or was not read-only,
expected tables or columns that were not used, a schema lookup that left out a table or column the question needed (when the
facts say so), written replies that miss the requested reply style (when the facts say so), vague or harmful questions the assistant answered anyway, which step takes
most of the response time, questions that failed. Name the actual group or question when you can.
suggestion: the one concrete action that answers THAT watch-out, never empty, starting with a verb ("Add ...",
"Check ...", "Rewrite ..."). It must make sense read right after its watch-out and must not repeat it.
If nothing is really wrong, give one finding whose watch_out says so plainly and whose suggestion says how to test the
assistant harder or what to keep an eye on.

Example of one finding: {"watch_out": "The join group scores lowest (5.8): queries over orders and customers often join on
orders.id instead of orders.customer_id.", "suggestion": "Add the foreign keys to the schema text sent to the model and run
this group again."}

Rules: plain everyday language; SQL words such as join, filter or GROUP BY are fine. Never write LLM, token or latency;
say "the AI model" and "response time" instead. One sentence per part, with at most one number in it. No markdown. Use only
the facts provided and do not invent causes the data does not show."""


# Appended to the summary prompt whether or not the developer replaced the wording above, so the
# dashboard can always show the result as bullet lists.
run_summary_format = """

Respond ONLY with a JSON object of exactly this shape: {"items": [{"watch_out": "...", "suggestion": "..."}]}.
There must be at least one item, and every item needs both parts. Each part is a single sentence."""
