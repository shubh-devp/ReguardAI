# import importlib
# import importlib.machinery
# import importlib.util
# import json
# import os
# import shutil
# import sys
# from pathlib import Path

# from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
# from langchain_community.retrievers import BM25Retriever
# from langchain_core.documents import Document
# from langchain_core.embeddings import Embeddings
# from langchain_chroma import Chroma

# from src.retrieval import provenance
# from src.retrieval.health import (
#     CHUNK_SCHEMA_VERSION,
#     CORPUS_PATH,
#     EMBEDDING_BACKEND,
#     EMBEDDING_MODEL,
#     FINGERPRINT_FILE,
#     ONNX_MODEL_DIR as _ONNX_MODEL_DIR,
#     PERSIST_DIRECTORY,
#     REGULATORY_KIND,
#     corpus_fingerprint,
#     index_matches_corpus,
# )

# # Re-exported here as well, because this module was the original home of these
# # names and other code imports them from it.
# __all__ = [
#     "CORPUS_PATH",
#     "PERSIST_DIRECTORY",
#     "COLLECTION_NAME",
#     "REGULATORY_KIND",
#     "DEFAULT_K",
#     "load_chunks_from_json",
#     "build_retriever",
#     "build_chroma_hybrid_retriever",
# ]

# COLLECTION_NAME = "rbi_corpus"
# ONNX_MODEL_DIR = Path(_ONNX_MODEL_DIR)

# DEFAULT_K = 4


# def load_ensemble_retriever():
#     """Return EnsembleRetriever without importing the package that ships it.

#     `from langchain_classic.retrievers import EnsembleRetriever` runs that
#     package's __init__, which eagerly imports every retriever LangChain has. One
#     of them pulls in transformers, and transformers drags torch along behind it -
#     hundreds of megabytes this pipeline never touches. Registering the package
#     directory without running its __init__ lets the ensemble module load on its
#     own; it needs nothing beyond langchain-core.
#     """
#     package = "langchain_classic.retrievers"
#     if package not in sys.modules:
#         import langchain_classic

#         spec = importlib.machinery.ModuleSpec(package, None, is_package=True)
#         stub = importlib.util.module_from_spec(spec)
#         stub.__path__ = [
#             os.path.join(os.path.dirname(langchain_classic.__file__), "retrievers")
#         ]
#         sys.modules[package] = stub

#     return importlib.import_module(f"{package}.ensemble").EnsembleRetriever


# EnsembleRetriever = load_ensemble_retriever()


# class LocalOnnxMiniLm(ONNXMiniLM_L6_V2):
#     """The same ONNX encoder, reading its model file from inside the project.

#     ChromaDB's version downloads 79 MB into ~/.cache on first use. Render's disk
#     is ephemeral and the service sleeps when idle, so that download would repeat
#     on every cold start. Shipping the file instead makes startup deterministic
#     and keeps it off the network entirely.
#     """

#     DOWNLOAD_PATH = ONNX_MODEL_DIR


# class OnnxMiniLmEmbeddings(Embeddings):
#     """all-MiniLM-L6-v2 running on ONNX Runtime instead of PyTorch.

#     It is the same model with the same weights, but it needs onnxruntime rather
#     than torch, and torch on its own is roughly 250 MB of resident memory. On a
#     512 MB instance that is the difference between an audit finishing and the
#     process being killed. ChromaDB ships this encoder but exposes it with a
#     different method name, so it is wrapped in the LangChain interface here.
#     """

#     def __init__(self):
#         self._encode = LocalOnnxMiniLm()
#         #The ONNX graph is read on the first call, not at construction, so make
#         #that call here: this object is built during warm-up, which keeps the
#         #cost out of the first audit.
#         self._encode(["warm up"])

#     def embed_documents(self, texts):
#         #The encoder hands back numpy scalars, which ChromaDB refuses to store,
#         #so each value is converted to a plain float on the way out.
#         return [[float(value) for value in vector] for vector in self._encode(list(texts))]

#     def embed_query(self, text):
#         return [float(value) for value in self._encode([text])[0]]


# def _build_metadata(item):
#     """Build the metadata a chunk is stored and cited with.

#     The corpus file only carries a filename plus a page or paragraph number. The
#     chunk id and the curated passage fields are added here so that a finding can
#     cite an actual passage rather than just a filename.
#     """
#     metadata = dict(item["metadata"])
#     metadata["chunk_id"] = item["chunk_id"]

#     if metadata.get("type") == REGULATORY_KIND:
#         # Every value here is a scalar or a list of strings: ChromaDB refuses to
#         # store nested objects, so the block is written flat.
#         metadata.update(provenance.describe(metadata.get("source"), metadata.get("page")))

#     return metadata


# #The parsed corpus, cached per path. Both the auditor and the re-test agent build a
# #retriever, and each one used to parse its own copy of all 1268 chunks - the same
# #JSON decoded twice into two sets of Document objects. The retriever was already
# #cached; this caches what the retriever is built from.
# _documents = {}


# def load_chunks_from_json(json_path=CORPUS_PATH):
#     #loading the parsed corpus chunks generated from Stage 1 parser.
#     if json_path in _documents:
#         return _documents[json_path]

#     if not os.path.exists(json_path):
#         raise FileNotFoundError(f"Corpus JSON not found at {json_path}. Run parser.py first!")

#     print(f"Loading chunks from corpus: {json_path}")
#     with open(json_path, "r", encoding="utf-8") as f:
#         data = json.load(f)

#     documents = [
#         Document(
#             page_content=item["page_content"],
#             metadata=_build_metadata(item)
#         )
#         for item in data
#     ]
#     print(f"-> Loaded {len(documents)} documents into memory.")
#     _documents[json_path] = documents
#     return documents


# def is_regulatory(document):
#     """True for an RBI document chunk, false for a lender policy chunk."""
#     return document.metadata.get("type") == REGULATORY_KIND


# def select_corpus(documents, regulatory_only=True):
#     """Restrict a corpus to regulatory documents when asked."""
#     if not regulatory_only:
#         return documents
#     return [document for document in documents if is_regulatory(document)]



# #One shared embedding model and one shared retriever per persist directory. Both
# #the auditor and the re-test agent ask for a retriever, and without this cache
# #each one loaded its own copy of all-MiniLM-L6-v2 and its own BM25 index. On a
# #512 MB instance that duplication is enough to get the process killed.
# _embeddings = None
# _retrievers = {}


# def build_embeddings():
#     #No encoding options are passed on purpose: the defaults are what this pipeline
#     #has always used, and changing them (normalization, batching) changes the stored
#     #vectors and therefore which passages come back.
#     global _embeddings
#     if _embeddings is None:
#         _embeddings = OnnxMiniLmEmbeddings()
#     return _embeddings


# def _write_fingerprint(corpus_path, persist_directory):
#     os.makedirs(persist_directory, exist_ok=True)
#     marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
#     with open(marker_path, "w", encoding="utf-8") as handle:
#         json.dump(
#             {
#                 "corpus_sha256": corpus_fingerprint(corpus_path),
#                 "embedding_backend": EMBEDDING_BACKEND,
#                 "chunk_schema_version": CHUNK_SCHEMA_VERSION,
#             },
#             handle,
#         )


# def _load_or_build_vectorstore(documents, embeddings, corpus_path, persist_directory):
#     #Encoding 1268 chunks takes minutes on a small instance, so a previously built
#     #index is reused whenever it still matches the corpus.
#     if index_matches_corpus(corpus_path, persist_directory):
#         print(f"-> Reusing the saved vector store at '{persist_directory}'")
#         return Chroma(
#             collection_name=COLLECTION_NAME,
#             embedding_function=embeddings,
#             persist_directory=persist_directory,
#         )

#     print(f"-> Embedding {len(documents)} chunks into '{persist_directory}'")
#     # Start from an empty directory: adding to an existing collection would leave
#     # duplicate vectors behind.
#     shutil.rmtree(persist_directory, ignore_errors=True)
#     store = Chroma.from_documents(
#         documents=documents,
#         embedding=embeddings,
#         collection_name=COLLECTION_NAME,
#         persist_directory=persist_directory,
#     )

#     if os.path.exists(corpus_path):
#         _write_fingerprint(corpus_path, persist_directory)

#     return store


# def build_keyword_retriever(documents, regulatory_only=True, k=DEFAULT_K):
#     """BM25 keyword search. This is the lexical half of the hybrid retriever."""
#     corpus = select_corpus(documents, regulatory_only)
#     print(f"Initializing BM25 keyword index over {len(corpus)} chunks...")
#     retriever = BM25Retriever.from_documents(corpus)
#     retriever.k = k
#     return retriever


# def build_dense_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
#     """Vector search. This is the semantic half of the hybrid retriever."""
#     embeddings = build_embeddings()
#     vectorstore = _load_or_build_vectorstore(documents, embeddings, CORPUS_PATH, persist_directory)

#     search_kwargs = {"k": k}
#     if regulatory_only:
#         #Chroma applies this as a "where" clause, so a lender policy chunk can
#         #never be returned as if it were RBI regulation.
#         search_kwargs["filter"] = {"type": REGULATORY_KIND}

#     return vectorstore.as_retriever(search_kwargs=search_kwargs)


# def build_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
#     """Blend keyword and vector search with weighted reciprocal rank fusion."""
#     keyword = build_keyword_retriever(documents, regulatory_only=regulatory_only, k=k)
#     dense = build_dense_retriever(
#         documents, persist_directory=persist_directory, regulatory_only=regulatory_only, k=k
#     )
#     return EnsembleRetriever(retrievers=[keyword, dense], weights=[0.4, 0.6])


# def build_retriever(documents, strategy="hybrid", persist_directory=PERSIST_DIRECTORY,
#                     regulatory_only=True, k=DEFAULT_K):
#     """Build one named retrieval strategy.

#     The retrieval evaluation uses this to score BM25, dense search and the hybrid
#     blend against each other on the same corpus with the same ground truth.
#     """
#     builders = {
#         "bm25": build_keyword_retriever,
#         "dense": build_dense_retriever,
#         "hybrid": build_hybrid_retriever,
#     }
#     if strategy not in builders:
#         raise ValueError(f"Unknown retrieval strategy {strategy!r}. Choose from {sorted(builders)}")

#     if strategy == "bm25":
#         return builders[strategy](documents, regulatory_only=regulatory_only, k=k)
#     return builders[strategy](documents, persist_directory=persist_directory,
#                               regulatory_only=regulatory_only, k=k)


# def build_chroma_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY):
#     """The retriever the live pipeline uses.

#     Cached per directory: both the auditor and the re-test agent ask for one, and
#     building it twice costs a second copy of the model and the BM25 index.
#     """
#     key = (persist_directory, "hybrid", True)
#     if key not in _retrievers:
#         print("Blending retrievers into the hybrid ensemble...")
#         _retrievers[key] = build_hybrid_retriever(documents, persist_directory=persist_directory)
#     return _retrievers[key]


# def corpus_status(persist_directory=PERSIST_DIRECTORY):
#     """Deprecated alias. The real implementation lives in src/retrieval/health.py.

#     It moved so that a readiness probe does not have to import ChromaDB,
#     onnxruntime and LangChain just to stat a few files. Kept as a re-export so
#     existing callers keep working.
#     """
#     from src.retrieval.health import corpus_status as _corpus_status

#     return _corpus_status(persist_directory)


# if __name__ == "__main__":
#     print("Starting Stage 2: Local ChromaDB & BM25 Hybrid Retrieval Engine...")

#     try:
#         # Load chunks from JSON
#         docs = load_chunks_from_json()

#         # Build Chroma hybrid retriever
#         retriever = build_chroma_hybrid_retriever(docs)

#         # Test query mimicking a fintech regulatory compliance check
#         query = "What is the minimum cooling-off period required for digital loans?"
#         print(f"\nExecuting test query locally via ChromaDB: '{query}'")
#         results = retriever.invoke(query)

#         print(f"\nChromaDB hybrid retrieval successful! Top {len(results)} matches found:")
#         print("=" * 60)
#         for idx, res in enumerate(results):
#             print(f"Match [{idx + 1}] | Source: {res.metadata.get('source')} | Type: {res.metadata.get('type')}")
#             print(f"Snippet: {res.page_content[:250]}...")
#             print("-" * 60)

#     except Exception as e:
#         print(f"Error setting up ChromaDB hybrid retrieval: {e}")





"""Simplified hybrid retrieval engine combining BM25 and ChromaDB."""

import json
import os
import shutil
from pathlib import Path

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma
from langchain.retrievers import EnsembleRetriever

from src.retrieval import provenance
from src.retrieval.health import (
    CORPUS_PATH,
    PERSIST_DIRECTORY,
    REGULATORY_KIND,
    index_matches_corpus,
)

__all__ = [
    "CORPUS_PATH",
    "PERSIST_DIRECTORY",
    "load_chunks_from_json",
    "build_retriever",
    "build_chroma_hybrid_retriever",
]

COLLECTION_NAME = "rbi_corpus"
ONNX_MODEL_DIR = Path("data/chroma_db/onnx_models")
DEFAULT_K = 4

_documents = {}
_embeddings = None
_retrievers = {}


class LocalOnnxMiniLm(ONNXMiniLM_L6_V2):
    DOWNLOAD_PATH = ONNX_MODEL_DIR


class OnnxMiniLmEmbeddings(Embeddings):
    def __init__(self):
        self._encode = LocalOnnxMiniLm()
        self._encode(["warm up"])

    def embed_documents(self, texts):
        return [[float(v) for v in vec] for vec in self._encode(list(texts))]

    def embed_query(self, text):
        return [float(v) for v in self._encode([text])[0]]


def _build_metadata(item):
    metadata = dict(item["metadata"])
    metadata["chunk_id"] = item["chunk_id"]
    if metadata.get("type") == REGULATORY_KIND:
        metadata.update(provenance.describe(metadata.get("source"), metadata.get("page")))
    return metadata


def load_chunks_from_json(json_path=CORPUS_PATH):
    if json_path in _documents:
        return _documents[json_path]

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Corpus JSON not found at {json_path}.")

    print(f"Loading chunks from corpus: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    documents = [
        Document(page_content=item["page_content"], metadata=_build_metadata(item))
        for item in data
    ]
    print(f"-> Loaded {len(documents)} documents.")
    _documents[json_path] = documents
    return documents


def build_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OnnxMiniLmEmbeddings()
    return _embeddings


def build_keyword_retriever(documents, regulatory_only=True, k=DEFAULT_K):
    corpus = [doc for doc in documents if not regulatory_only or doc.metadata.get("type") == REGULATORY_KIND]
    retriever = BM25Retriever.from_documents(corpus)
    retriever.k = k
    return retriever


def build_dense_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    embeddings = build_embeddings()
    
    if index_matches_corpus(CORPUS_PATH, persist_directory):
        vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )
    else:
        shutil.rmtree(persist_directory, ignore_errors=True)
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            collection_name=COLLECTION_NAME,
            persist_directory=persist_directory,
        )

    search_kwargs = {"k": k}
    if regulatory_only:
        search_kwargs["filter"] = {"type": REGULATORY_KIND}

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def build_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    keyword = build_keyword_retriever(documents, regulatory_only=regulatory_only, k=k)
    dense = build_dense_retriever(documents, persist_directory=persist_directory, regulatory_only=regulatory_only, k=k)
    return EnsembleRetriever(retrievers=[keyword, dense], weights=[0.4, 0.6])


def build_retriever(documents, strategy="hybrid", persist_directory=PERSIST_DIRECTORY,
                    regulatory_only=True, k=DEFAULT_K):
    """Instantiate a specified retrieval strategy safely for external callers."""
    builders = {
        "bm25": build_keyword_retriever,
        "dense": build_dense_retriever,
        "hybrid": build_hybrid_retriever,
    }
    if strategy not in builders:
        raise ValueError(f"Unknown retrieval strategy {strategy!r}.")

    if strategy == "bm25":
        return builders[strategy](documents, regulatory_only=regulatory_only, k=k)
    return builders[strategy](documents, persist_directory=persist_directory,
                            regulatory_only=regulatory_only, k=k)


def build_chroma_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY):
    key = (persist_directory, "hybrid")
    if key not in _retrievers:
        _retrievers[key] = build_hybrid_retriever(documents, persist_directory=persist_directory)
    return _retrievers[key]


def corpus_status(persist_directory=PERSIST_DIRECTORY):
    """Re-export health status checking for external callers."""
    from src.retrieval.health import corpus_status as _corpus_status
    return _corpus_status(persist_directory)


if __name__ == "__main__":
    docs = load_chunks_from_json()
    retriever = build_chroma_hybrid_retriever(docs)
    results = retriever.invoke("What is the minimum cooling-off period required for digital loans?")
    print(f"Retrieved {len(results)} matches successfully.")