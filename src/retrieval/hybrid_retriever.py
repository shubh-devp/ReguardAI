import importlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma

from src.retrieval import provenance
from src.retrieval.health import (
    CHUNK_SCHEMA_VERSION,
    CORPUS_PATH,
    EMBEDDING_BACKEND,
    EMBEDDING_MODEL,
    FINGERPRINT_FILE,
    ONNX_MODEL_DIR as _ONNX_MODEL_DIR,
    PERSIST_DIRECTORY,
    REGULATORY_KIND,
    corpus_fingerprint,
    index_matches_corpus,
)

__all__ = [
    "CORPUS_PATH",
    "PERSIST_DIRECTORY",
    "COLLECTION_NAME",
    "REGULATORY_KIND",
    "DEFAULT_K",
    "load_chunks_from_json",
    "build_retriever",
    "build_chroma_hybrid_retriever",
]

COLLECTION_NAME = "rbi_corpus"
ONNX_MODEL_DIR = Path(_ONNX_MODEL_DIR)

DEFAULT_K = 4


def load_ensemble_retriever():
    package = "langchain_classic.retrievers"
    if package not in sys.modules:
        import langchain_classic

        spec = importlib.machinery.ModuleSpec(package, None, is_package=True)
        stub = importlib.util.module_from_spec(spec)
        stub.__path__ = [
            os.path.join(os.path.dirname(langchain_classic.__file__), "retrievers")
        ]
        sys.modules[package] = stub

    return importlib.import_module(f"{package}.ensemble").EnsembleRetriever


EnsembleRetriever = load_ensemble_retriever()


class LocalOnnxMiniLm(ONNXMiniLM_L6_V2):

    DOWNLOAD_PATH = ONNX_MODEL_DIR


class OnnxMiniLmEmbeddings(Embeddings):

    def __init__(self):
        self._encode = LocalOnnxMiniLm()
        self._encode(["warm up"])

    def embed_documents(self, texts):
        return [[float(value) for value in vector] for vector in self._encode(list(texts))]

    def embed_query(self, text):
        return [float(value) for value in self._encode([text])[0]]


def _build_metadata(item):
    metadata = dict(item["metadata"])
    metadata["chunk_id"] = item["chunk_id"]

    if metadata.get("type") == REGULATORY_KIND:
        metadata.update(provenance.describe(metadata.get("source"), metadata.get("page")))

    return metadata

_documents = {}


def load_chunks_from_json(json_path=CORPUS_PATH):
    if json_path in _documents:
        return _documents[json_path]

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Corpus JSON not found at {json_path}. Run parser.py first!")

    print(f"Loading chunks from corpus: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    documents = [
        Document(
            page_content=item["page_content"],
            metadata=_build_metadata(item)
        )
        for item in data
    ]
    print(f"-> Loaded {len(documents)} documents into memory.")
    _documents[json_path] = documents
    return documents


def is_regulatory(document):
    return document.metadata.get("type") == REGULATORY_KIND


def select_corpus(documents, regulatory_only=True):
    if not regulatory_only:
        return documents
    return [document for document in documents if is_regulatory(document)]


_embeddings = None
_retrievers = {}


def build_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OnnxMiniLmEmbeddings()
    return _embeddings


def _write_fingerprint(corpus_path, persist_directory):
    os.makedirs(persist_directory, exist_ok=True)
    marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
    with open(marker_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "corpus_sha256": corpus_fingerprint(corpus_path),
                "embedding_backend": EMBEDDING_BACKEND,
                "chunk_schema_version": CHUNK_SCHEMA_VERSION,
            },
            handle,
        )


def _load_or_build_vectorstore(documents, embeddings, corpus_path, persist_directory):
    if index_matches_corpus(corpus_path, persist_directory):
        print(f"-> Reusing the saved vector store at '{persist_directory}'")
        return Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )

    print(f"-> Embedding {len(documents)} chunks into '{persist_directory}'")
    shutil.rmtree(persist_directory, ignore_errors=True)
    store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
    )

    if os.path.exists(corpus_path):
        _write_fingerprint(corpus_path, persist_directory)

    return store


def build_keyword_retriever(documents, regulatory_only=True, k=DEFAULT_K):
    corpus = select_corpus(documents, regulatory_only)
    print(f"Initializing BM25 keyword index over {len(corpus)} chunks...")
    retriever = BM25Retriever.from_documents(corpus)
    retriever.k = k
    return retriever


def build_dense_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    embeddings = build_embeddings()
    vectorstore = _load_or_build_vectorstore(documents, embeddings, CORPUS_PATH, persist_directory)

    search_kwargs = {"k": k}
    if regulatory_only:
        search_kwargs["filter"] = {"type": REGULATORY_KIND}

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def build_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    keyword = build_keyword_retriever(documents, regulatory_only=regulatory_only, k=k)
    dense = build_dense_retriever(
        documents, persist_directory=persist_directory, regulatory_only=regulatory_only, k=k
    )
    return EnsembleRetriever(retrievers=[keyword, dense], weights=[0.4, 0.6])


def build_retriever(documents, strategy="hybrid", persist_directory=PERSIST_DIRECTORY,
                    regulatory_only=True, k=DEFAULT_K):
    builders = {
        "bm25": build_keyword_retriever,
        "dense": build_dense_retriever,
        "hybrid": build_hybrid_retriever,
    }
    if strategy not in builders:
        raise ValueError(f"Unknown retrieval strategy {strategy!r}. Choose from {sorted(builders)}")

    if strategy == "bm25":
        return builders[strategy](documents, regulatory_only=regulatory_only, k=k)
    return builders[strategy](documents, persist_directory=persist_directory,
                              regulatory_only=regulatory_only, k=k)


def build_chroma_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY):
    key = (persist_directory, "hybrid", True)
    if key not in _retrievers:
        print("Blending retrievers into the hybrid ensemble...")
        _retrievers[key] = build_hybrid_retriever(documents, persist_directory=persist_directory)
    return _retrievers[key]


def corpus_status(persist_directory=PERSIST_DIRECTORY):

    from src.retrieval.health import corpus_status as _corpus_status

    return _corpus_status(persist_directory)


if __name__ == "__main__":
    print("Starting Stage 2: Local ChromaDB & BM25 Hybrid Retrieval Engine...")

    try:
        # Load chunks from JSON
        docs = load_chunks_from_json()

        # Build Chroma hybrid retriever
        retriever = build_chroma_hybrid_retriever(docs)

        # Test query mimicking a fintech regulatory compliance check
        query = "What is the minimum cooling-off period required for digital loans?"
        print(f"\nExecuting test query locally via ChromaDB: '{query}'")
        results = retriever.invoke(query)

        print(f"\nChromaDB hybrid retrieval successful! Top {len(results)} matches found:")
        print("=" * 60)
        for idx, res in enumerate(results):
            print(f"Match [{idx + 1}] | Source: {res.metadata.get('source')} | Type: {res.metadata.get('type')}")
            print(f"Snippet: {res.page_content[:250]}...")
            print("-" * 60)

    except Exception as e:
        print(f"Error setting up ChromaDB hybrid retrieval: {e}")
