from dotenv import load_dotenv
load_dotenv()  # loads .env before anything else

from app import app

if __name__ == '__main__':
    app.run(port=5001, debug=True)
