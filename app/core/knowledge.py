from agno.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb
from agno.knowledge.embedder.sentence_transformer import SentenceTransformerEmbedder
from agno.knowledge.reader.pdf_reader import PDFReader
import os

# Ensure data directory exists
PDF_DIR = "data/pdf"
LANCEDB_URI = "data/lancedb"

def get_knowledge_base(vector_table_name: str = "agent_docs"):
    """
    Returns a Knowledge instance with LanceDb vector store.
    """
    # Create LanceDb instance
    vector_db = LanceDb(
        table_name=vector_table_name,
        uri=LANCEDB_URI,
        embedder=SentenceTransformerEmbedder(id="all-MiniLM-L6-v2"),
    )

    # Create Knowledge Base
    knowledge_base = Knowledge(
        vector_db=vector_db,
    )

    return knowledge_base

def ingest_pdfs():
    """
    Loads all PDFs from data/pdf into the knowledge base.
    """
    kb = get_knowledge_base()

    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)
        return "PDF directory created. Please add files."

    pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith(".pdf")]
    if not pdf_files:
        return "No PDF files found in data/pdf."

    reader = PDFReader()
    documents = []
    for pdf_file in pdf_files:
        path = os.path.join(PDF_DIR, pdf_file)
        try:
            print(f"Reading {path}...")
            docs = reader.read(pdf=path)
            print(f"Read {len(docs)} documents from {path}")
            documents.extend(docs)
        except Exception as e:
            print(f"Error reading {path}: {e}")

    if not documents:
        return "Could not load documents from PDFs."

    print(f"Loading {len(documents)} docs into VectorDB...")
    # Pass content_hash
    kb.vector_db.create() # Ensure table exists
    kb.vector_db.upsert(content_hash="manual_ingest", documents=documents)

    return f"Successfully ingested {len(documents)} documents (chunks) from {len(pdf_files)} files."
