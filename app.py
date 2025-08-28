from flask import Flask, request, Response
import os
from collections import deque
from threading import Lock
from compact_json import Formatter

app = Flask(__name__)

# In memory store for received payloads
_messages = deque(maxlen=1000)
_lock = Lock()

# Compact JSON formatter
formatter = Formatter(indent_spaces=2, max_inline_length=80)

def pretty_json(obj) -> str:
    return formatter.serialize(obj) + "\n"

@app.post("/chat")
def chat():
    payload = request.get_json(silent=True)
    if payload is None:
        return {"error": "Expected JSON body"}, 400

    entry = {
        "headers": dict(request.headers),
        "body": payload
    }

    with _lock:
        _messages.append(entry)

    return {"status": "ok"}, 200

@app.get("/")
def index():
    with _lock:
        body = "".join(pretty_json(m) for m in _messages)
    return Response(body or "[]\n", mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)