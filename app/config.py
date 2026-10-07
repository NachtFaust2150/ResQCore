import os

JWT_SECRET = os.environ.get("JWT_SECRET", "resqcore_secret_key_2026_disaster_response")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = "resqcore"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)
