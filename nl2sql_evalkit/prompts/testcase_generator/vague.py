"""The instructions for writing one vague question."""

vague_prompt = """Write ONE vague question about this data: a question a careful assistant should NOT answer with SQL straight away, because it is unclear what is meant and a guess could return the wrong thing.

Typical vagueness: a word that has several meanings in this data ("best customers": by revenue, by orders, by recent activity?), a missing period ("sales" without a date range), a missing measure ("top products": by what?), an unclear group or an unknown threshold ("big orders").

- The question must be natural and short, the kind a busy person types.
- It must still be about this data (use ideas from the tables), but there must be at least two reasonable readings that lead to different SQL.
- Do not include the missing detail, and never write the clarifying question yourself.
- "unclear_because": one sentence naming the two or more readings.

Reply with JSON only: {"question": "...", "unclear_because": "..."}"""
