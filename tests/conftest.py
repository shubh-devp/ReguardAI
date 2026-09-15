"""Shared fixtures.

The corpus and the curated passages are read once per session: they are a few
megabytes of JSON and several test modules need them.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def corpus():
    """Every chunk in the retrieval corpus."""
    from src.retrieval.hybrid_retriever import load_chunks_from_json

    return load_chunks_from_json()


@pytest.fixture(scope="session")
def curated_passages():
    """The reviewed passages used as ground truth."""
    from src.retrieval import provenance

    return provenance.load_curated_passages()


@pytest.fixture(scope="session")
def benchmark_records():
    """The labelled benchmark, with gold evidence resolved."""
    from src.evaluation.benchmark import build_dataset

    return build_dataset()
