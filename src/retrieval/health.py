import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CORPUS_PATH = "data/corpus/parsed_corpus_chunks.json"
PERSIST_DIRECTORY = "data/chroma_db"
FINGERPRINT_FILE = "corpus_fingerprint.json"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_BACKEND = "onnx"
CHUNK_SCHEMA_VERSION = 2


REGULATORY_KIND = "regulatory_pdf"


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONNX_MODEL_DIR = str(_PROJECT_ROOT / "data" / "models" / "onnx_models" / EMBEDDING_MODEL)
ONNX_MODEL_PATH = os.path.join(ONNX_MODEL_DIR, "onnx", "model.onnx")


def corpus_fingerprint(corpus_path=CORPUS_PATH):
    with open(corpus_path, "rb") as handle:
        raw = handle.read()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def index_matches_corpus(corpus_path=CORPUS_PATH, persist_directory=PERSIST_DIRECTORY):
    marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
    if not (os.path.exists(marker_path) and os.path.exists(corpus_path)):
        return False

    try:
        with open(marker_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        return (
            saved.get("corpus_sha256") == corpus_fingerprint(corpus_path)
            and saved.get("embedding_backend") == EMBEDDING_BACKEND
            and saved.get("chunk_schema_version") == CHUNK_SCHEMA_VERSION
        )
    except (OSError, ValueError):
        return False


def corpus_status(persist_directory=PERSIST_DIRECTORY):
    status = {
        "corpus_file": os.path.exists(CORPUS_PATH),
        "onnx_model": os.path.exists(ONNX_MODEL_PATH),
        "index_directory": os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")),
        "index_matches_corpus": index_matches_corpus(CORPUS_PATH, persist_directory),
        "chunks": 0,
        "regulatory_chunks": 0,
    }

    if status["corpus_file"]:
        try:
            with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
                items = json.load(handle)
            status["chunks"] = len(items)
            status["regulatory_chunks"] = sum(
                1 for item in items if item.get("metadata", {}).get("type") == REGULATORY_KIND
            )
        except (OSError, ValueError) as error:
            status["corpus_error"] = str(error)

    status["retrieval_ready"] = bool(
        status["corpus_file"]
        and status["onnx_model"]
        and status["regulatory_chunks"]
        and (status["index_directory"] or status["chunks"])
    )
    return status
