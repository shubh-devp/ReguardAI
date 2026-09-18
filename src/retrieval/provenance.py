import json
import logging
import os

logger = logging.getLogger(__name__)

CURATED_CORPUS_PATH = "data/corpus/regulatory_corpus.json"

#Fields copied onto a chunk when the join finds a curated passage.
PROVENANCE_FIELDS = (
    "passage_id",
    "section",
    "subsection",
    "regulation",
    "authority",
    "status",
    "effective_date",
    "topic",
)

_passage_index = None


def load_curated_passages(json_path=CURATED_CORPUS_PATH):
    """Return the reviewed passages, or an empty list if the file is missing."""
    if not os.path.exists(json_path):
        logger.warning("Curated corpus not found at %s; findings will cite pages only", json_path)
        return []

    with open(json_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_passage_index(passages):
    index = {}
    for passage in passages:
        document = passage.get("source_document")
        page = passage.get("page")
        if document is None or page is None:
            continue
        index.setdefault((document, page), []).append(passage)
    return index


def get_passage_index():
    global _passage_index
    if _passage_index is None:
        _passage_index = build_passage_index(load_curated_passages())
        logger.info("Curated corpus loaded: %d pages indexed", len(_passage_index))
    return _passage_index


def lookup_passages(source, page):
    if source is None or page is None:
        return []
    return get_passage_index().get((source, page), [])


def describe(source, page):
    provenance = {
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
        return provenance

    primary = matches[0]
    passage_ids = [match.get("passage_id") for match in matches if match.get("passage_id")]
    if passage_ids:
        provenance["passage_ids"] = passage_ids

    provenance["passage_id"] = primary.get("passage_id")
    provenance["section"] = primary.get("section")
    provenance["regulation"] = primary.get("regulation")
    provenance["effective_date"] = primary.get("effective_date")
    provenance["status"] = primary.get("status")
    provenance["topic"] = primary.get("topic")
    return provenance


def from_metadata(metadata):
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

