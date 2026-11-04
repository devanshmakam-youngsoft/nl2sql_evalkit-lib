"""Score the written reply as well as the SQL.

The assistant returns its SQL and a short summary for the user. ``reply_style`` says how that summary should read; the judge
scores it 0 to 10 against that style, with a reason and a suggestion. A test case can carry its own ``reply_style``, which
wins over this default. Without a reply style no reply is scored and nothing else changes."""
import nl2sql_evalkit


def my_assistant(question: str) -> dict:
    return {
        "sql": "SELECT region, COUNT(*) FROM customers GROUP BY region",
        "summary": "You have customers in 4 regions, and the north has the most.",
    }


def short_and_plain(question: str, reply_style: str, reply_text: str, sql: str) -> dict:
    """Your own reply judge (optional): two sentences at most, and no SQL words."""
    sentences = [s for s in reply_text.replace("?", ".").replace("!", ".").split(".") if s.strip()]
    sql_words = [w for w in ("select", "table", "column", "group by") if w in reply_text.lower()]
    if len(sentences) > 2 or sql_words:
        return {"reply_marks": 4, "reply_comment": "Too long, or it uses SQL words.", "suggestion": "Say it in two plain sentences."}
    return {"reply_marks": 10, "reply_comment": "Short and plain."}


if __name__ == "__main__":
    nl2sql_evalkit.serve(my_assistant, reply_style="Friendly, two sentences at most, say how many rows, no SQL words")
