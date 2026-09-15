import hashlib
import importlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys

from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma

CORPUS_PATH = "data/corpus/parsed_corpus_chunks.json"
PERSIST_DIRECTORY = "data/chroma_db"
COLLECTION_NAME = "rbi_corpus"
FINGERPRINT_FILE = "corpus_fingerprint.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_BACKEND = "onnx"


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


class OnnxMiniLmEmbeddings(Embeddings):
    """all-MiniLM-L6-v2 running on ONNX Runtime instead of PyTorch.

    It is the same model with the same weights, but it needs onnxruntime rather
    than torch, and torch on its own is roughly 250 MB of resident memory. On a
    512 MB instance that is the difference between an audit finishing and the
    process being killed. ChromaDB ships this encoder but exposes it with a
    different method name, so it is wrapped in the LangChain interface here.
    """

    def __init__(self):
        self._encode = ONNXMiniLM_L6_V2()
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
            metadata=item["metadata"]
        )
        for item in data
    ]
    print(f"-> Loaded {len(documents)} documents into memory.")
    return documents


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
        # cannot be searched with queries from another.
        return (
            saved.get("corpus_sha256") == _corpus_fingerprint(corpus_path)
            and saved.get("embedding_backend") == EMBEDDING_BACKEND
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


def build_chroma_hybrid_retriever(documents, persist_directory=PERSIST_DIRECTORY):
    #hybrid search engine combining BM25 (exact keyword matching) 
    #and  dense vector search
    #Callers that pass the same corpus get the same retriever back, so only one
    #BM25 index and one vector store are held in memory.
    if persist_directory in _retrievers:
        return _retrievers[persist_directory]

    print("Initializing BM25 keyword index...")
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = 4

    print(f"Loading local SentenceTransformer model ({EMBEDDING_MODEL})...")
    embeddings = build_embeddings()

    vectorstore = _load_or_build_vectorstore(documents, embeddings, CORPUS_PATH, persist_directory)
    chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    print("Blending retrievers into a secure Hybrid Ensemble...")
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, chroma_retriever],
        weights=[0.4, 0.6]  # 40% keyword precision, 60% semantic similarity
    )

    _retrievers[persist_directory] = ensemble_retriever
    return ensemble_retriever


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
