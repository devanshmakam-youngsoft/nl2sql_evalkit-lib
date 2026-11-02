"""The instructions for writing one join question."""

join_prompt = """Write ONE question that needs information from two or more of the tables, so the SQL has to JOIN them.

- Join on the keys the tables are linked by (a foreign key shown with "->", or the columns that obviously correspond). Never join on columns that merely share a type.
- Use every table you are given, each for a reason: a column in the answer or a condition in the filter.
- The question must not hint at the join: a person asks "which region has the highest sales", not "join orders to customers".

Reply with JSON only: {"question": "...", "sql": "..."}"""
