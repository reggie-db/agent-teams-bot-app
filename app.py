# app.py
from flask import Flask, request, jsonify
import os, time, threading, requests, logging
from compact_json import Formatter

APP_ID = os.getenv("MICROSOFT_APP_ID", "")
APP_PASSWORD = os.getenv("MICROSOFT_APP_PASSWORD", "")

app = Flask(__name__)

# Logging setup
logger = logging.getLogger("teams-bot")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Compact JSON
_cj = Formatter(indent_spaces=2, max_inline_length=120).serialize

_token_cache = {"value": None, "exp": 0.0}



def get_token():
    now = time.time()
    if _token_cache["value"] and now < _token_cache["exp"] - 60:
        return _token_cache["value"]
    logger.info("Fetching Bot Framework token")
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
    try:
        r.raise_for_status()
    except Exception:
        logger.error("Token request failed: %s %s\n%s", r.status_code, r.reason, r.text)
        raise
    data = r.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["exp"] = now + int(data.get("expires_in", 3600))
    logger.info("Token acquired")
    return _token_cache["value"]

def post_activity(service_url, conversation_id, activity):
    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    # Log outbound activity
    safe_headers = {"Authorization": "Bearer [REDACTED]"}
    logger.info("POST %s", url)
    logger.info("Outbound activity:\n%s", _cj(activity))
    r = requests.post(url, json=activity, headers={"Authorization": f"Bearer {get_token()}"}, timeout=10)
    try:
        r.raise_for_status()
    except Exception:
        logger.error("Activity post failed: %s %s\nHeaders: %s\nBody: %s",
                     r.status_code, r.reason, _cj(dict(r.headers)), r.text)
        raise
    logger.info("Activity accepted: %s %s", r.status_code, r.reason)
    if r.headers.get("Content-Type", "").startswith("application/json"):
        try:
            logger.info("Connector response JSON:\n%s", _cj(r.json()))
        except Exception:
            pass
    return r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}

def respond(activity):
    try:
        svc = activity["serviceUrl"]
        conv = activity["conversation"]["id"]
        user = activity["from"]["id"]
        bot = activity["recipient"]["id"]
        text = activity.get("text", "") or ""

        logger.info("Responding to conversation %s", conv)

        post_activity(svc, conv, {
            "type": "typing",
            "from": {"id": bot},
            "recipient": {"id": user},
            "conversation": {"id": conv},
        })

        post_activity(svc, conv, {
            "type": "message",
            "from": {"id": bot},
            "recipient": {"id": user},
            "conversation": {"id": conv},
            "text": "thinking..."
        })

        post_activity(svc, conv, {
            "type": "message",
            "from": {"id": bot},
            "recipient": {"id": user},
            "conversation": {"id": conv},
            "text": f"you asked: {text}"
        })
    except Exception as e:
        logger.exception("Error in respond: %s", e)

@app.post("/chat")
def chat():
    # Log inbound headers and body using compact-json
    try:
        headers_dict = dict(request.headers)
        # Redact auth if present
        if "Authorization" in headers_dict:
            headers_dict["Authorization"] = "[REDACTED]"
        logger.info("Inbound /chat headers:\n%s", _cj(headers_dict))
    except Exception:
        logger.exception("Failed to log headers")

    activity = request.get_json(silent=True) or {}
    try:
        logger.info("Inbound /chat body:\n%s", _cj(activity))
    except Exception:
        logger.exception("Failed to log body")

    if activity.get("type") == "message" and activity.get("text"):
        logger.info("Spawning responder thread for conversation %s", activity.get("conversation", {}).get("id"))
        threading.Thread(target=respond, args=(activity,), daemon=True).start()
    else:
        logger.info("Non message activity type: %s", activity.get("type"))

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    logger.info("Starting app")
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)