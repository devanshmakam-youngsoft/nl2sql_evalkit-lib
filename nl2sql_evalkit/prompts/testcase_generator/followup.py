"""The instructions for writing one follow-up conversation."""

followup_prompt = """Write ONE realistic conversation of exactly {turns} turns between a user and an assistant that answers with SQL.

How the conversation must work
- Turn 1 is an ordinary, self-contained question about one topic in the data.
- Every later turn is what a real person types NEXT, after seeing the result of the last query. It must be IMPOSSIBLE to understand without the earlier turns. Refer back the way people do: "and for last month?", "only those in the north", "what about the other status?", "sort that by amount", "now per customer", "why not include ...?".
- Do NOT repeat the topic's words: people say "that", "those", "it", not "total sales per region" again.
- Each follow-up refines or extends the previous result: add a filter, change the grouping, change the period, rank or limit the rows, add a measure. Never start a new, unrelated question.
- Every turn has its own complete SQL that answers the whole conversation so far (the filters and groupings of the earlier turns are included when they still apply).
- For every turn after the first add "depends_on": one short sentence saying exactly what from the earlier turns the question relies on.
- Check before you reply: read each follow-up on its own, as if it were the first message. If it makes sense alone, rewrite it so it refers back.

Bad follow-up (it stands alone, so it is just another new question): "What is the total amount of orders per region?"
Good follow-up (it needs the earlier turn): "And only for the last three months?"

Reply with JSON only: {"turns": [{"question": "...", "sql": "..."}, {"question": "...", "sql": "...", "depends_on": "..."}, ...]}"""
