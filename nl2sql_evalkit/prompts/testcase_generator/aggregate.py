"""The instructions for writing one aggregation question."""

aggregate_prompt = """Write ONE question that needs an aggregate: a count, a sum, an average, a minimum or maximum, usually per group (per region, per month, per customer), sometimes with a condition on the group ("only those with more than 10 orders", which is HAVING).

- Ask for a result a person would actually read: a short list of groups with their figures, or one number.
- If you group, the question must make clear what the groups are ("per region", "by status").

Reply with JSON only: {"question": "...", "sql": "..."}"""
