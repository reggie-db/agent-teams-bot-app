# app.py
from flask import Flask, request, jsonify
import os, time, threading, requests

APP_ID = os.getenv("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

app = Flask(__name__)

_token_cache = {"value": None, "exp": 0.0}

def get_token():
    now = time.time()
    if _token_cache["value"] and now < _token_cache["exp"] - 60:
        return _token_cache["value"]
    r = requests.post(
        "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": APP_ID,
            "client_secret": APP_PASSWORD,
            "scope": "https://api.botframework.com/.default",
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["exp"] = now + int(data.get("expires_in", 3600))
    return _token_cache["value"]

def post_activity(service_url, conversation_id, activity):
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    r = requests.post(url, json=activity, headers={"Authorization": f"Bearer {get_token()}"}, timeout=10)
    r.raise_for_status()
    return r.json()

def respond(activity):
    svc = activity["serviceUrl"]
    conv = activity["conversation"]["id"]
    user = activity["from"]["id"]
    bot = activity["recipient"]["id"]
    text = activity.get("text", "") or ""

    post_activity(svc, conv, {"type": "typing", "from": {"id": bot}, "recipient": {"id": user}, "conversation": {"id": conv}})
    post_activity(svc, conv, {"type": "message", "from": {"id": bot}, "recipient": {"id": user}, "conversation": {"id": conv}, "text": "thinking..."})
    post_activity(svc, conv, {"type": "message", "from": {"id": bot}, "recipient": {"id": user}, "conversation": {"id": conv}, "text": f"you asked: {text}"})

@app.post("/chat")
def chat():
    activity = request.get_json(silent=True) or {}
    if activity.get("type") == "message" and activity.get("text"):
        threading.Thread(target=respond, args=(activity,), daemon=True).start()
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)