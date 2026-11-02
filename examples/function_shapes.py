"""The shapes of function nl2sql_evalkit understands. Pick the one that matches how your text-to-SQL assistant works.

Whatever the shape, the function returns the SQL (a string, or a message when it declines or asks a question). The SQL is
read by the checks and the judge, never run."""
import nl2sql_evalkit

SALES_PER_REGION = "SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c ON o.customer_id = c.id GROUP BY c.region"


# Shape 1: a question in, SQL out. Every question is answered on its own.
def answer_only(question: str) -> str:
    return SALES_PER_REGION


# Shape 2: a stateless assistant. You receive the earlier turns of the chat every time and rebuild the prompt from them.
# history looks like [{"question": "...", "answer": "..."}, ...] and is empty on the first turn.
def answer_with_history(question: str, history: list) -> str:
    if history:
        return f"-- follows up on: {history[-1]['question']}\n{SALES_PER_REGION} HAVING SUM(o.amount) > 0"
    return SALES_PER_REGION


# Shape 3: a stateful assistant. Your backend remembers the conversation itself, so nl2sql_evalkit only passes a session id
# (the same id for every turn of one chat, a new one for the next chat).
SESSIONS: dict[str, list] = {}


def answer_in_session(question: str, session_id: str) -> str:
    turns = SESSIONS.setdefault(session_id, [])
    turns.append(question)
    return f"-- message {len(turns)} of this chat\n{SALES_PER_REGION}"


# Your function may also return a dict (nl2sql_evalkit reads the "sql" key; "query", "answer", "response", "output",
# "result" and "text" work too), or a Pydantic model with such a field.
def answer_as_dict(question: str) -> dict:
    return {"sql": SALES_PER_REGION, "confidence": 0.92}


# ...or be async.
async def answer_async(question: str) -> str:
    return SALES_PER_REGION


# Parameter names of your own? Tell nl2sql_evalkit what they mean:
#     nl2sql_evalkit.serve(answer_with_other_names, history_params=["past_chats"], session_params=["chat_token"])
def answer_with_other_names(question: str, past_chats: list) -> str:
    return f"-- I can see {len(past_chats)} earlier turns.\n{SALES_PER_REGION}"


# With serve(..., history_format="openai") the history arrives as chat messages instead of question/answer pairs.
def answer_with_openai_history(question: str, messages: list) -> str:
    # messages = [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
    return f"-- earlier you asked: {last_user}\n{SALES_PER_REGION}" if last_user else SALES_PER_REGION


if __name__ == "__main__":
    nl2sql_evalkit.serve(answer_with_history, dialect="postgres")   # or answer_only, or answer_in_session
