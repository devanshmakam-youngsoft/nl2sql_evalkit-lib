"""The rules every question writer follows, whatever the category."""

common_rules = """You write test questions for an assistant that turns natural-language questions into SQL. A tester will put your question to that assistant and compare the SQL it writes with yours, so the question and the SQL must be right.

You are given a few tables of one database: their columns with types, primary keys, and the foreign keys between them. You never see any data.

Ground rules
- Use ONLY the tables and columns shown. Never invent a table, a column or a relationship, and never use outside knowledge of what the data holds.
- Write the question the way a real person would type it into a chat box: natural, specific, in their own words, in the language of the column comments if there are any (else English). The way you would ask a colleague who knows the data.
- NEVER mention SQL, "the table", "the column", "the schema" or "the database", and never copy a table or column name when plain words say it ("how many customers" not "count rows in customers"). A person asking does not know how the data is stored.
- Ask about something useful for a business: totals, counts, lists, rankings, comparisons, trends, exceptions. Not about the structure of the database itself.
- The SQL is a single read-only SELECT (a WITH ... SELECT is fine). It must run as written on the dialect given: use that dialect's functions for dates and text, and qualify columns with a table alias whenever more than one table is used.
- The SQL must answer exactly what the question asks: no extra filters, no missing ones. Spell out every filter the question states (a status, a date range, a region).
- Do not use SELECT * unless the question asks for every column."""
