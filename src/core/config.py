"""
Lab 11 — Configuration & API Key Setup
"""
import os


def setup_api_key():
    """Load Google API key from .env file or environment, preferring .env to avoid prompting."""
    # Find .env in the parent directory of src
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    env_path = os.path.normpath(env_path)
    
    env_key = None
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if key == "GOOGLE_API_KEY" and value:
                        env_key = value
                        break

    if env_key:
        os.environ["GOOGLE_API_KEY"] = env_key
        print("API key loaded from .env.")
    elif "GOOGLE_API_KEY" not in os.environ or not os.environ["GOOGLE_API_KEY"]:
        os.environ["GOOGLE_API_KEY"] = input("Enter Google API Key: ")
        print("API key loaded from input prompt.")
    else:
        print("API key loaded from environment.")
        
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "0"


# Model to use throughout the project
GEMINI_MODEL = "gemini-3.1-flash-lite"

# Allowed banking topics (used by topic_filter)
ALLOWED_TOPICS = [
    "banking", "account", "transaction", "transfer",
    "loan", "interest", "savings", "credit",
    "deposit", "withdrawal", "balance", "payment",
    "tai khoan", "giao dich", "tiet kiem", "lai suat",
    "chuyen tien", "the tin dung", "so du", "vay",
    "ngan hang", "atm",
]

# Blocked topics (immediate reject)
BLOCKED_TOPICS = [
    "hack", "exploit", "weapon", "drug", "illegal",
    "violence", "gambling", "bomb", "kill", "steal",
]
