import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
RAW_SOURCES_DIR = DATA_DIR / "raw_sources"
CASE_STUDIES_DIR = DATA_DIR / "case_studies"
KB_PATH = DATA_DIR / "terragni_kb.json"
INDEX_PATH = DATA_DIR / "document_index.json"

load_dotenv(BACKEND_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
TOP_K_CHUNKS = int(os.getenv("TOP_K_CHUNKS", "10"))
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "4500"))

