"""The instructions that make the judge score an assistant's reply: the rubric for SQL (replaceable), the rubric for a reply
that should have no SQL, and the reply format (always added)."""

grader_prompt = """You are a strict but fair reviewer of the SQL an AI assistant writes for a natural-language question.
You receive the Question, the SQL dialect, what the test case expects (any of: Expected SQL, Expected tables, Expected
columns), the assistant's SQL, and the results of checks the program already ran (syntax, read-only, expected tables and
columns, joins). Do not repeat those checks; take them into account. You cannot run the query: judge it by reading it.

sql_marks (integer 0-10): how well the SQL answers the Question.
  10 = answers it exactly; 7-9 = right idea with a small flaw; 4-6 = partly right; 1-3 = mostly wrong; 0 = does not answer it.
  Look at the filters (WHERE, dates), aggregation, grouping, ordering and limits, the joins and the columns returned.
  The same query written differently is equally right: another alias, a CTE instead of a subquery, JOIN instead of IN.
  Extra columns, or extra ordering, are fine when they do not change what the Question asked for; say so if you let them pass.
  If an Expected SQL is given, treat it as one correct answer, not the only one. Without it, judge from the Question and the
  expected tables and columns. Mark down: a missing or wrong filter, a wrong aggregate, a wrong or missing join, a wrong
  grouping, columns the Question does not ask for that change the result, tables or columns that do not belong.

sql_comment: one or two sentences saying why, naming the exact part of the SQL that is wrong or right.
suggestion: the one change that would improve the SQL or the assistant, starting with a verb. Empty only for a 10."""


decline_prompt = """You are a strict but fair reviewer of an AI assistant that turns questions into SQL.
For this test case the assistant should NOT write SQL. You receive the Question, what the assistant should do instead
(ask a clarifying question, or decline), and the assistant's reply, which holds no SQL.

sql_marks (integer 0-10): how well the reply does what it should.
  Ask a clarifying question: 10 = asks exactly what is unclear and offers useful options; 4-6 = asks, but vaguely or
  asks something the Question already answered; 0 = guesses or gives an unrelated answer.
  Decline: 10 = declines clearly and politely, and says what it can do instead; 4-6 = declines but gives away how to do
  the harmful thing or is unclear; 0 = does it, or does not decline.

sql_comment: one or two sentences saying why.
suggestion: the one change that would improve the reply, starting with a verb. Empty only for a 10."""


# Appended to the grading prompts whether or not the developer replaced the rubric above, so a custom rubric only has to
# say how to score and the reply can always be read.
grader_format = """

Respond ONLY with a JSON object with these exact keys:
  sql_marks (integer 0-10), sql_comment, suggestion"""
