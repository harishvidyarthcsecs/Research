from dotenv import load_dotenv
load_dotenv(override=True)  # .env is authoritative, even over a polluted shell env

from app import app

if __name__ == '__main__':
    # threaded=True so the SSE progress stream (/research/events) doesn't block
    # the follow-up /research/result fetch on the single dev-server worker.
    app.run(port=5001, debug=True, threaded=True)
