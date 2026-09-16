# """Links an indexed chunk back to the reviewed RBI passage it came from.

# Two corpora describe the same RBI documents:

# - ``data/corpus/parsed_corpus_chunks.json`` is what retrieval actually searches.
#   It is mechanically split, so a chunk only knows a filename and a page number.
# - ``data/corpus/regulatory_corpus.json`` is a reviewed set of 57 passages, each
#   with a passage id, section, regulation, effective date and status.

# Both use the same page numbering for the same PDFs, so a chunk can be joined to
# its curated passage on ``(document, page)``. That join is what lets a finding
# cite ``RBI-DL-0004`` instead of just "RBI_KFS_Loans_Advances_2024.pdf", and it is
# also how the retrieval evaluation compares retrieved chunks against gold
# passage ids.
# """

# import json
# import logging
# import os

# logger = logging.getLogger(__name__)

# CURATED_CORPUS_PATH = "data/corpus/regulatory_corpus.json"

# #Fields copied onto a chunk when the join finds a curated passage.
# PROVENANCE_FIELDS = (
#     "passage_id",
#     "section",
#     "subsection",
#     "regulation",
#     "authority",
#     "status",
#     "effective_date",
#     "topic",
# )

# _passage_index = None


# def load_curated_passages(json_path=CURATED_CORPUS_PATH):
#     """Return the reviewed passages, or an empty list if the file is missing."""
#     if not os.path.exists(json_path):
#         logger.warning("Curated corpus not found at %s; findings will cite pages only", json_path)
#         return []

#     with open(json_path, "r", encoding="utf-8") as handle:
#         return json.load(handle)


# def build_passage_index(passages):
#     """Map ``(source_document, page)`` to the passages that start on that page.

#     A page can carry more than one curated passage, so every value is a list.
#     """
#     index = {}
#     for passage in passages:
#         document = passage.get("source_document")
#         page = passage.get("page")
#         if document is None or page is None:
#             continue
#         index.setdefault((document, page), []).append(passage)
#     return index


# def get_passage_index():
#     """Build the join index once and reuse it."""
#     global _passage_index
#     if _passage_index is None:
#         _passage_index = build_passage_index(load_curated_passages())
#         logger.info("Curated corpus loaded: %d pages indexed", len(_passage_index))
#     return _passage_index


# def lookup_passages(source, page):
#     """Return the curated passages on a given page of a given document."""
#     if source is None or page is None:
#         return []
#     return get_passage_index().get((source, page), [])


# def describe(source, page):
#     """Build the provenance block for a retrieved chunk.

#     Every value is a string, a number, or a list of strings, because ChromaDB
#     refuses to store nested objects and this block is written into chunk
#     metadata. The document and page are always present; the curated fields are
#     added only when the join finds a reviewed passage.
#     """
#     provenance = {
#         "document": source,
#         "page": page,
#         "citation": f"{source} p.{page}" if page is not None else str(source),
#         "passage_id": None,
#         "section": None,
#         "regulation": None,
#         "effective_date": None,
#         "status": None,
#         "topic": None,
#     }

#     matches = lookup_passages(source, page)
#     if not matches:
#         return provenance

#     primary = matches[0]
#     passage_ids = [match.get("passage_id") for match in matches if match.get("passage_id")]
#     if passage_ids:
#         # An empty list is not a storable metadata value, so only set it when
#         # the page actually resolved to a passage.
#         provenance["passage_ids"] = passage_ids

#     provenance["passage_id"] = primary.get("passage_id")
#     provenance["section"] = primary.get("section")
#     provenance["regulation"] = primary.get("regulation")
#     provenance["effective_date"] = primary.get("effective_date")
#     provenance["status"] = primary.get("status")
#     provenance["topic"] = primary.get("topic")
#     return provenance


# def from_metadata(metadata):
#     """Rebuild the provenance block from a stored chunk's metadata."""
#     return {
#         "document": metadata.get("source"),
#         "page": metadata.get("page"),
#         "citation": metadata.get("citation"),
#         "passage_id": metadata.get("passage_id"),
#         "passage_ids": metadata.get("passage_ids") or [],
#         "section": metadata.get("section"),
#         "regulation": metadata.get("regulation"),
#         "effective_date": metadata.get("effective_date"),
#         "status": metadata.get("status"),
#         "topic": metadata.get("topic"),
#     }





"""Links an indexed chunk back to the reviewed RBI passage it came from.

Two corpora describe the same RBI documents:
- Parsed chunks know filenames and page numbers.
- Curated regulatory corpus holds reviewed passages with metadata.
Both share identical page numbering, allowing a join on (document, page).
"""

from pathlib import Path
import json

CURATED_PATH = Path("data/corpus/regulatory_corpus.json")

PROVENANCE_KEYS = (
    "passage_id",
    "section",
    "subsection",
    "regulation",
    "authority",
    "status",
    "effective_date",
    "topic",
)

_index_cache = None


def load_curated_passages(json_path: Path = CURATED_PATH) -> list:
    """Return reviewed passages, or an empty list if file is missing."""
    target = Path(json_path)
    if not target.exists():
        print(f"Notice: Curated corpus not found at {target}; citations will use raw pages only.")
        return []

    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


def build_passage_index(passages: list) -> dict:
    """Map (source_document, page) to matching passages."""
    index = {}
    for item in passages:
        doc = item.get("source_document")
        pg = item.get("page")
        if doc is None or pg is None:
            continue
        index.setdefault((doc, pg), []).append(item)
    return index


def get_passage_index() -> dict:
    """Build or fetch the join index lazily."""
    global _index_cache
    if _index_cache is None:
        passages = load_curated_passages()
        _index_cache = build_passage_index(passages)
        print(f"Curated corpus initialized: {len(_index_cache)} pages indexed.")
    return _index_cache


def lookup_passages(source: str, page: int) -> list:
    """Return curated passages for a specific page of a document."""
    if source is None or page is None:
        return []
    return get_passage_index().get((source, page), [])


def describe(source: str, page: int) -> dict:
    """Build a metadata provenance block compatible with ChromaDB storage."""
    meta = {
        "document": source,
        "page": page,
        "citation": f"{source} p.{page}" if page is not None else str(source),
        "passage_id": None,
        "section": None,
        "regulation": None,
        "effective_date": None,
        "status": None,
        "topic": None,
    }

    matches = lookup_passages(source, page)
    if not matches:
        return meta

    primary = matches[0]
    all_pids = [m.get("passage_id") for m in matches if m.get("passage_id")]
    
    if all_pids:
        meta["passage_ids"] = all_pids

    meta["passage_id"] = primary.get("passage_id")
    meta["section"] = primary.get("section")
    meta["regulation"] = primary.get("regulation")
    meta["effective_date"] = primary.get("effective_date")
    meta["status"] = primary.get("status")
    meta["topic"] = primary.get("topic")
    
    return meta


def from_metadata(metadata: dict) -> dict:
    """Rebuild a provenance block straight from stored chunk metadata."""
    return {
        "document": metadata.get("source"),
        "page": metadata.get("page"),
        "citation": metadata.get("citation"),
        "passage_id": metadata.get("passage_id"),
        "passage_ids": metadata.get("passage_ids") or [],
        "section": metadata.get("section"),
        "regulation": metadata.get("regulation"),
        "effective_date": metadata.get("effective_date"),
        "status": metadata.get("status"),
        "topic": metadata.get("topic"),
    }