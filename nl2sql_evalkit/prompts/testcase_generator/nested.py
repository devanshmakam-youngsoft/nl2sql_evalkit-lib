"""The instructions for writing one question that needs a subquery or a CTE."""

nested_prompt = """Write ONE question whose SQL needs a subquery or a WITH (CTE): comparing with an overall figure ("above the average"), "customers who have never ordered", the latest row per group, a ranking that is then filtered, or a result built in two steps.

- The question reads naturally: people ask "which products sell better than average", not "use a subquery".
- The SQL really needs the second step: it cannot be written as a plain filter on one query.

Reply with JSON only: {"question": "...", "sql": "..."}"""
