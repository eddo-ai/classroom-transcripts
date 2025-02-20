from flask import Flask, request
from main import handle_assemblyai_webhook

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    return handle_assemblyai_webhook(request)

if __name__ == "__main__":
    app.run(port=8081) 