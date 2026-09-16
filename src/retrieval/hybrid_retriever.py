import hashlib
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

CORPUS_PATH = "data/corpus/parsed_corpus_chunks.json"
PERSIST_DIRECTORY = "data/chroma_db"
COLLECTION_NAME = "rbi_corpus"
FINGERPRINT_FILE = "corpus_fingerprint.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_BACKEND = "onnx"
ONNX_MODEL_DIR = Path(__file__).resolve().parents[2] / "data" / "models" / "onnx_models" / EMBEDDING_MODEL

# Chunk metadata is derived from the corpus file, so it has to be versioned
# separately: changing how it is built must invalidate the saved index too.
CHUNK_SCHEMA_VERSION = 2

# The index holds both the RBI documents and the lender policy documents. Only
# the former count as regulatory evidence.
REGULATORY_KIND = "regulatory_pdf"

DEFAULT_K = 4


def load_ensemble_retriever():
    """Return EnsembleRetriever without importing the package that ships it.

    `from langchain_classic.retrievers import EnsembleRetriever` runs that
    package's __init__, which eagerly imports every retriever LangChain has. One
    of them pulls in transformers, and transformers drags torch along behind it -
    hundreds of megabytes this pipeline never touches. Registering the package
    directory without running its __init__ lets the ensemble module load on its
    own; it needs nothing beyond langchain-core.
    """
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
    """The same ONNX encoder, reading its model file from inside the project.

    ChromaDB's version downloads 79 MB into ~/.cache on first use. Render's disk
    is ephemeral and the service sleeps when idle, so that download would repeat
    on every cold start. Shipping the file instead makes startup deterministic
    and keeps it off the network entirely.
    """

    DOWNLOAD_PATH = ONNX_MODEL_DIR


class OnnxMiniLmEmbeddings(Embeddings):
    """all-MiniLM-L6-v2 running on ONNX Runtime instead of PyTorch.

    It is the same model with the same weights, but it needs onnxruntime rather
    than torch, and torch on its own is roughly 250 MB of resident memory. On a
    512 MB instance that is the difference between an audit finishing and the
    process being killed. ChromaDB ships this encoder but exposes it with a
    different method name, so it is wrapped in the LangChain interface here.
    """

    def __init__(self):
        self._encode = LocalOnnxMiniLm()
        #The ONNX graph is read on the first call, not at construction, so make
        #that call here: this object is built during warm-up, which keeps the
        #cost out of the first audit.
        self._encode(["warm up"])

    def embed_documents(self, texts):
        #The encoder hands back numpy scalars, which ChromaDB refuses to store,
        #so each value is converted to a plain float on the way out.
        return [[float(value) for value in vector] for vector in self._encode(list(texts))]

    def embed_query(self, text):
        return [float(value) for value in self._encode([text])[0]]


def _build_metadata(item):
    """Build the metadata a chunk is stored and cited with.

    The corpus file only carries a filename plus a page or paragraph number. The
    chunk id and the curated passage fields are added here so that a finding can
    cite an actual passage rather than just a filename.
    """
    metadata = dict(item["metadata"])
    metadata["chunk_id"] = item["chunk_id"]

    if metadata.get("type") == REGULATORY_KIND:
        # Every value here is a scalar or a list of strings: ChromaDB refuses to
        # store nested objects, so the block is written flat.
        metadata.update(provenance.describe(metadata.get("source"), metadata.get("page")))

    return metadata


def load_chunks_from_json(json_path=CORPUS_PATH):
    #loading the parsed corpus chunks generated from Stage 1 parser.
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
    return documents


def is_regulatory(document):
    """True for an RBI document chunk, false for a lender policy chunk."""
    return document.metadata.get("type") == REGULATORY_KIND


def select_corpus(documents, regulatory_only=True):
    """Restrict a corpus to regulatory documents when asked."""
    if not regulatory_only:
        return documents
    return [document for document in documents if is_regulatory(document)]



#One shared embedding model and one shared retriever per persist directory. Both
#the auditor and the re-test agent ask for a retriever, and without this cache
#each one loaded its own copy of all-MiniLM-L6-v2 and its own BM25 index. On a
#512 MB instance that duplication is enough to get the process killed.
_embeddings = None
_retrievers = {}


def build_embeddings():
    #No encoding options are passed on purpose: the defaults are what this pipeline
    #has always used, and changing them (normalization, batching) changes the stored
    #vectors and therefore which passages come back.
    global _embeddings
    if _embeddings is None:
        _embeddings = OnnxMiniLmEmbeddings()
    return _embeddings


def _corpus_fingerprint(corpus_path):
    #sha256 of the corpus file. If the corpus changes, the saved index is stale and
    #gets rebuilt, so we never retrieve from vectors that no longer match the text.
    digest = hashlib.sha256()
    with open(corpus_path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _saved_index_is_current(corpus_path, persist_directory):
    marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
    if not (os.path.exists(marker_path) and os.path.exists(corpus_path)):
        return False

    try:
        with open(marker_path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        # The backend is part of the check because vectors written by one encoder
        # cannot be searched with queries from another. The schema version covers
        # the chunk metadata, which is stored alongside the vectors.
        return (
            saved.get("corpus_sha256") == _corpus_fingerprint(corpus_path)
            and saved.get("embedding_backend") == EMBEDDING_BACKEND
            and saved.get("chunk_schema_version") == CHUNK_SCHEMA_VERSION
        )
    except (OSError, ValueError):
        return False


def _write_fingerprint(corpus_path, persist_directory):
    os.makedirs(persist_directory, exist_ok=True)
    marker_path = os.path.join(persist_directory, FINGERPRINT_FILE)
    with open(marker_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "corpus_sha256": _corpus_fingerprint(corpus_path),
                "embedding_backend": EMBEDDING_BACKEND,
                "chunk_schema_version": CHUNK_SCHEMA_VERSION,
            },
            handle,
        )


def _load_or_build_vectorstore(documents, embeddings, corpus_path, persist_directory):
    #Encoding 1268 chunks takes minutes on a small instance, so a previously built
    #index is reused whenever it still matches the corpus.
    if _saved_index_is_current(corpus_path, persist_directory):
        print(f"-> Reusing the saved vector store at '{persist_directory}'")
        return Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )

    print(f"-> Embedding {len(documents)} chunks into '{persist_directory}'")
    # Start from an empty directory: adding to an existing collection would leave
    # duplicate vectors behind.
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
    """BM25 keyword search. This is the lexical half of the hybrid retriever."""
    corpus = select_corpus(documents, regulatory_only)
    print(f"Initializing BM25 keyword index over {len(corpus)} chunks...")
    retriever = BM25Retriever.from_documents(corpus)
    retriever.k = k
    return retriever


def build_dense_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    """Vector search. This is the semantic half of the hybrid retriever."""
    embeddings = build_embeddings()
    vectorstore = _load_or_build_vectorstore(documents, embeddings, CORPUS_PATH, persist_directory)

    search_kwargs = {"k": k}
    if regulatory_only:
        #Chroma applies this as a "where" clause, so a lender policy chunk can
        #never be returned as if it were RBI regulation.
        search_kwargs["filter"] = {"type": REGULATORY_KIND}

    return vectorstore.as_retriever(search_kwargs=search_kwargs)


def build_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY, regulatory_only=True, k=DEFAULT_K):
    """Blend keyword and vector search with weighted reciprocal rank fusion."""
    keyword = build_keyword_retriever(documents, regulatory_only=regulatory_only, k=k)
    dense = build_dense_retriever(
        documents, persist_directory=persist_directory, regulatory_only=regulatory_only, k=k
    )
    return EnsembleRetriever(retrievers=[keyword, dense], weights=[0.4, 0.6])


def build_retriever(documents, strategy="hybrid", persist_directory=PERSIST_DIRECTORY,
                    regulatory_only=True, k=DEFAULT_K):
    """Build one named retrieval strategy.

    The retrieval evaluation uses this to score BM25, dense search and the hybrid
    blend against each other on the same corpus with the same ground truth.
    """
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
    """The retriever the live pipeline uses.

    Cached per directory: both the auditor and the re-test agent ask for one, and
    building it twice costs a second copy of the model and the BM25 index.
    """
    key = (persist_directory, "hybrid", True)
    if key not in _retrievers:
        print("Blending retrievers into the hybrid ensemble...")
        _retrievers[key] = build_hybrid_retriever(documents, persist_directory=persist_directory)
    return _retrievers[key]


def corpus_status(persist_directory=PERSIST_DIRECTORY):
    """Report what the retrieval stack can actually see.

    A health check that only proves the port is open is not worth much. The
    failure this project actually hit was a deployment with no corpus and no
    index: every request answered 200 while every finding cited the same
    hardcoded fallback sentence. Naming the individual parts is what makes that
    show up in a readiness probe instead of silently in the results.
    """
    model_path = os.path.join(ONNX_MODEL_DIR, "onnx", "model.onnx")
    status = {
        "corpus_file": os.path.exists(CORPUS_PATH),
        "onnx_model": os.path.exists(model_path),
        "index_directory": os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")),
        "index_matches_corpus": _saved_index_is_current(CORPUS_PATH, persist_directory),
        "chunks": 0,
        "regulatory_chunks": 0,
    }

    if status["corpus_file"]:
        try:
            # Counted straight from the file rather than through
            # load_chunks_from_json, which would also build 1200+ Document objects
            # and run the provenance join on every readiness probe.
            with open(CORPUS_PATH, "r", encoding="utf-8") as handle:
                items = json.load(handle)
            status["chunks"] = len(items)
            status["regulatory_chunks"] = sum(
                1 for item in items if item.get("metadata", {}).get("type") == REGULATORY_KIND
            )
        except (OSError, ValueError) as error:
            status["corpus_error"] = str(error)

    # Retrieval needs a corpus to search, an encoder to embed with, and something
    # to search: either a saved index or a corpus that one can be built from.
    status["retrieval_ready"] = bool(
        status["corpus_file"]
        and status["onnx_model"]
        and status["regulatory_chunks"]
        and (status["index_directory"] or status["chunks"])
    )
    return status



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
