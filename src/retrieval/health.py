"""Can retrieval actually work right now?

This module deliberately imports nothing heavy. ChromaDB, onnxruntime and
LangChain together cost hundreds of megabytes of resident memory and take tens of
seconds to import on a cold container, so a readiness probe that pulled them in
would be slow enough to time out - and if the host uses that probe as its health
check, slow enough to be marked unhealthy and restarted, over and over.

Everything here is a filesystem check, so it answers in milliseconds and is safe to
call from a health check.

The failure it exists to catch is the one this project actually hit: a deployment
with no corpus and no index that answered 200 to every request while every finding
cited a single hardcoded sentence.
"""

import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

CORPUS_PATH = "data/corpus/parsed_corpus_chunks.json"
PERSIST_DIRECTORY = "data/chroma_db"
FINGERPRINT_FILE = "corpus_fingerprint.json"

# The index is only usable if it was built by this encoder under this chunk schema.
# All three are stored in the fingerprint file and checked on every load.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_BACKEND = "onnx"
CHUNK_SCHEMA_VERSION = 2

# The index holds both RBI documents and lender policies. Only the former count as
# regulatory evidence.
REGULATORY_KIND = "regulatory_pdf"

# Resolved from this file rather than the working directory, so the encoder is found
# no matter where the process was started from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ONNX_MODEL_DIR = str(_PROJECT_ROOT / "data" / "models" / "onnx_models" / EMBEDDING_MODEL)
ONNX_MODEL_PATH = os.path.join(ONNX_MODEL_DIR, "onnx", "model.onnx")


def corpus_fingerprint(corpus_path=CORPUS_PATH):
    """SHA256 of the corpus file.

    If the corpus changes, a saved index built from the old text is stale and has to
    be rebuilt, so the vectors can never disagree with the passages they point at.
    """
    digest = hashlib.sha256()
    with open(corpus_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def index_matches_corpus(corpus_path=CORPUS_PATH, persist_directory=PERSIST_DIRECTORY):
    """Whether the saved index was built from this corpus by this encoder."""
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
    """Report what the retrieval stack can actually see.

    A health check that only proves the port is open is not worth much. This names
    the individual parts, so a deployment that is missing its corpus, its encoder or
    its index shows up here instead of silently citing a fallback passage.
    """
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
            # Counted straight from the file rather than by building Document
            # objects, so this stays cheap enough to serve as a probe.
            with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
                items = json.load(handle)
            status["chunks"] = len(items)
            status["regulatory_chunks"] = sum(
                1 for item in items if item.get("metadata", {}).get("type") == REGULATORY_KIND
            )
        except (OSError, ValueError) as error:
            status["corpus_error"] = str(error)

    # Retrieval needs a corpus to search, an encoder to embed with, and something to
    # search: either a saved index, or a corpus one can be built from.
    status["retrieval_ready"] = bool(
        status["corpus_file"]
        and status["onnx_model"]
        and status["regulatory_chunks"]
        and (status["index_directory"] or status["chunks"])
    )
    return status
