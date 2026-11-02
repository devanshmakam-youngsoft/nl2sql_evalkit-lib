"""Evaluate a text-to-SQL service that is already deployed: your function just calls it over HTTP and returns its SQL."""
import json
import os
import urllib.request

import nl2sql_evalkit

BOT_URL = os.environ.get("BOT_URL", "http://localhost:9000/chat")


def ask_deployed_bot(question: str, session_id: str) -> str:
    body = json.dumps({"message": question, "session_id": session_id}).encode()
    request = urllib.request.Request(BOT_URL, data=body, headers={"Content-Type": "application/json"})
    with nl2sql_evalkit.step("http_call"):
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())["reply"]


if __name__ == "__main__":
    nl2sql_evalkit.serve(ask_deployed_bot, dialect="postgres")
