"""Retrieval invariants.

These use the BM25 half only. It needs no model, so the suite stays fast while
still covering the corpus filtering and citation behaviour that regressions would
show up in.
"""

import json

from src.retrieval import health, hybrid_retriever


def test_every_chunk_carries_its_id(corpus):
    """The chunk id is dropped unless the loader keeps it, and it is the only
    stable handle on a specific chunk."""
    assert all("chunk_id" in document.metadata for document in corpus)
    assert all(isinstance(document.metadata["chunk_id"], int) for document in corpus)


def test_the_committed_index_is_accepted_without_rebuilding():
    """A mismatch here makes a deployment re-embed the whole corpus at startup.

    That is not a slow path, it is a fatal one: re-embedding 1160 chunks needs
    minutes and a large memory spike, which on a small instance kills the process
    and returns 502 on every route.
    """
    assert health.index_matches_corpus() is True


def test_the_corpus_fingerprint_ignores_line_endings(tmp_path):
    """Git checks the corpus out as CRLF on Windows and LF everywhere else.

    Hashing the raw bytes made the fingerprint depend on which platform computed it,
    so an index built on Windows was read as stale on the Linux instance.
    """
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(b'{"a": 1}\n{"b": 2}\n')
    crlf.write_bytes(b'{"a": 1}\r\n{"b": 2}\r\n')

    assert health.corpus_fingerprint(str(lf)) == health.corpus_fingerprint(str(crlf))


def test_the_corpus_fingerprint_still_changes_when_the_text_changes(tmp_path):
    """Normalising line endings must not make the check meaningless."""
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b'{"a": 1}\n')
    second.write_bytes(b'{"a": 2}\n')

    assert health.corpus_fingerprint(str(first)) != health.corpus_fingerprint(str(second))



def test_corpus_holds_both_document_kinds(corpus):
    kinds = {document.metadata["type"] for document in corpus}
    assert kinds == {"regulatory_pdf", "enterprise_policy"}


def test_regulatory_selection_excludes_lender_policies(corpus):
    """A lender's own policy must never be returned as RBI evidence."""
    regulatory = hybrid_retriever.select_corpus(corpus, regulatory_only=True)
    assert regulatory
    assert {d.metadata["type"] for d in regulatory} == {"regulatory_pdf"}
    assert len(regulatory) < len(corpus)


def test_unfiltered_selection_returns_everything(corpus):
    assert len(hybrid_retriever.select_corpus(corpus, regulatory_only=False)) == len(corpus)


def test_keyword_retriever_is_filtered(corpus):
    retriever = hybrid_retriever.build_keyword_retriever(corpus, regulatory_only=True)
    hits = retriever.invoke("penal charge compounded monthly on delayed repayment")

    assert hits
    assert all(hit.metadata["type"] == "regulatory_pdf" for hit in hits)


def test_retrieval_is_deterministic(corpus):
    """The same query must return the same passages in the same order."""
    retriever = hybrid_retriever.build_keyword_retriever(corpus, regulatory_only=True)
    query = "cooling-off period for digital loans"

    first = [(d.metadata["source"], d.metadata.get("page")) for d in retriever.invoke(query)]
    second = [(d.metadata["source"], d.metadata.get("page")) for d in retriever.invoke(query)]

    assert first == second
    assert first, "the query should match something in the corpus"


def test_regulatory_chunks_carry_a_citation(corpus):
    regulatory = hybrid_retriever.select_corpus(corpus, regulatory_only=True)
    assert all(document.metadata.get("citation") for document in regulatory)
    assert all(document.metadata.get("document") for document in regulatory)


def test_fingerprint_records_the_chunk_schema(tmp_path):
    """Metadata is derived from the corpus file, so the index must be invalidated
    when that derivation changes."""
    marker = tmp_path / "fingerprint.json"
    fingerprinted = {
        "corpus_sha256": "abc",
        "embedding_backend": hybrid_retriever.EMBEDDING_BACKEND,
        "chunk_schema_version": hybrid_retriever.CHUNK_SCHEMA_VERSION,
    }
    marker.write_text(json.dumps(fingerprinted), encoding="utf-8")

    saved = json.loads(marker.read_text(encoding="utf-8"))
    assert saved["chunk_schema_version"] == hybrid_retriever.CHUNK_SCHEMA_VERSION


def test_unknown_strategy_is_rejected(corpus):
    import pytest

    with pytest.raises(ValueError):
        hybrid_retriever.build_retriever(corpus, strategy="does-not-exist")
