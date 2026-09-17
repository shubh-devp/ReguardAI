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
    """SHA256 of the corpus text, independent of how it was checked out.

    Line endings are normalised before hashing. Git stores LF and checks out CRLF on
    Windows, so hashing the raw bytes made the fingerprint depend on which platform
    computed it. The index was built and fingerprinted on Windows; the Linux
    instance then read a different hash, concluded its index was stale, threw it
    away and began re-embedding all 1160 chunks at startup. That rebuild is what
    exhausted the instance and returned 502 on every route.

    Normalising is safe because a JSON string cannot contain a raw newline - every
    newline inside a chunk is an escape sequence, so the decoded text, and therefore
    the vectors, are identical either way. The whole file is read at once because a
    streaming version could split a CRLF pair across a block boundary.
    """
    with open(corpus_path, "rb") as handle:
        raw = handle.read()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


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






# """Filesystem-based health and readiness diagnostics for the retrieval stack."""

# from pathlib import Path
# import hashlib
# import json
# import os

# CORPUS_PATH = "data/corpus/parsed_corpus_chunks.json"
# PERSIST_DIRECTORY = "data/chroma_db"
# FINGERPRINT_FILE = "corpus_fingerprint.json"

# EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# EMBEDDING_BACKEND = "onnx"
# CHUNK_SCHEMA_VERSION = 2
# REGULATORY_KIND = "regulatory_pdf"

# _PROJECT_ROOT = Path(__file__).resolve().parents[2]
# ONNX_MODEL_DIR = str(_PROJECT_ROOT / "data" / "models" / "onnx_models" / EMBEDDING_MODEL)
# ONNX_MODEL_PATH = os.path.join(ONNX_MODEL_DIR, "onnx", "model.onnx")


# def corpus_fingerprint(corpus_path=CORPUS_PATH):
#     """Compute normalized SHA256 hash of the corpus to prevent cross-platform mismatch."""
#     try:
#         with open(corpus_path, "rb") as f:
#             raw = f.read()
#         return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
#     except OSError:
#         return ""


# def index_matches_corpus(corpus_path=CORPUS_PATH, persist_directory=PERSIST_DIRECTORY):
#     """Verify if the saved vector index matches the current corpus and encoder schema."""
#     marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
#     if not (os.path.exists(marker_path) and os.path.exists(corpus_path)):
#         return False

#     try:
#         with open(marker_path, "r", encoding="utf-8") as f:
#             saved = json.load(f)
#         return (
#             saved.get("corpus_sha256") == corpus_fingerprint(corpus_path)
#             and saved.get("embedding_backend") == EMBEDDING_BACKEND
#             and saved.get("chunk_schema_version") == CHUNK_SCHEMA_VERSION
#         )
#     except (OSError, ValueError):
#         return False


# def corpus_status(persist_directory=PERSIST_DIRECTORY):
#     """Inspect availability of corpus files, models, and index status."""
#     status = {
#         "corpus_file": os.path.exists(CORPUS_PATH),
#         "onnx_model": os.path.exists(ONNX_MODEL_PATH),
#         "index_directory": os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")),
#         "index_matches_corpus": index_matches_corpus(CORPUS_PATH, persist_directory),
#         "chunks": 0,
#         "regulatory_chunks": 0,
#     }

#     if status["corpus_file"]:
#         try:
#             with open(CORPUS_PATH, "r", encoding="utf-8") as f:
#                 items = json.load(f)
#             status["chunks"] = len(items)
#             status["regulatory_chunks"] = sum(
#                 1 for item in items if item.get("metadata", {}).get("type") == REGULATORY_KIND
#             )
#         except (OSError, ValueError) as error:
#             status["corpus_error"] = str(error)

#     status["retrieval_ready"] = bool(
#         status["corpus_file"]
#         and status["onnx_model"]
#         and status["regulatory_chunks"]
#         and (status["index_directory"] or status["chunks"])
#     )
#     return status