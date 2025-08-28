from flask import Flask, request
import os

app = Flask(__name__)

@app.get("/")
def index():
    headers_lines = [f"{key}: {value}" for key, value in request.headers.items()]
    return "\n".join(headers_lines)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)