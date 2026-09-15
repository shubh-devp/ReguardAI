import os
import json
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.retrievers import EnsembleRetriever



def load_chunks_from_json(json_path="data/corpus/parsed_corpus_chunks.json"):
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


def build_chroma_hybrid_retriever(documents, persist_directory="data/chroma_db"):
    #hybrid search engine combining BM25 (exact keyword matching) 
    #and  dense vector search
    print("⚙️ Initializing BM25 keyword index...")
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = 4

    print("⚙️ Loading local SentenceTransformer model (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    print(f"⚙️ Initializing ChromaDB vector store at '{persist_directory}'...")

    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    chroma_retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    print("⚖️ Blending retrievers into a secure Hybrid Ensemble...")
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, chroma_retriever],
        weights=[0.4, 0.6]  # 40% keyword precision, 60% semantic similarity
    )

    return ensemble_retriever

if __name__ == "__main__":
    print("🔒 Starting Stage 2: Local ChromaDB & BM25 Hybrid Retrieval Engine...")
    
    try:
        # Load chunks from JSON
        docs = load_chunks_from_json()
        
        # Build Chroma hybrid retriever
        retriever = build_chroma_hybrid_retriever(docs)
        
        # Test query mimicking a fintech regulatory compliance check
        query = "What is the minimum cooling-off period required for digital loans?"
        print(f"\n🔍 Executing test query locally via ChromaDB: '{query}'")
        
        results = retriever.invoke(query)
        
        print(f"\n✨ ChromaDB hybrid retrieval successful! Top {len(results)} matches found:")
        print("=" * 60)
        for idx, res in enumerate(results):
            print(f"Match [{idx + 1}] | Source: {res.metadata.get('source')} | Type: {res.metadata.get('type')}")
            print(f"Snippet: {res.page_content[:250]}...")
            print("-" * 60)
            
    except Exception as e:
        print(f"❌ Error setting up ChromaDB hybrid retrieval: {e}")