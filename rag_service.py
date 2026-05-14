"""
rag_service.py
--------------
RAGService: a deliberately simple Retrieval-Augmented-Generation helper.

It does four things:
  1. Extract text from an uploaded PDF.
  2. Split that text into overlapping word-chunks.
  3. Store the document + chunks in SQLite (via DatabaseService).
  4. Search those chunks by keyword when the user asks a question.

No vector database — keyword matching is plenty for a hackathon MVP, and the
whole system still works fine when no PDFs have been uploaded at all.
"""

from pypdf import PdfReader

# Chunking configuration (kept as constants so they are easy to tune).
CHUNK_SIZE_WORDS = 700      # target words per chunk (spec: ~500-1000)
CHUNK_OVERLAP_WORDS = 100   # overlap between consecutive chunks
TOP_K_CHUNKS = 5            # how many chunks to retrieve per question (spec: 3-5)


class RAGService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------
    # PDF text extraction
    # ------------------------------------------------------------------
    def extract_text(self, pdf_path):
        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages).strip()

    # ------------------------------------------------------------------
    # Chunking (word-based, with overlap)
    # ------------------------------------------------------------------
    def chunk_text(self, text, size=CHUNK_SIZE_WORDS, overlap=CHUNK_OVERLAP_WORDS):
        words = text.split()
        if not words:
            return []
        chunks = []
        start = 0
        step = max(1, size - overlap)
        while start < len(words):
            chunk_words = words[start:start + size]
            chunks.append(" ".join(chunk_words))
            if start + size >= len(words):
                break
            start += step
        return chunks

    # ------------------------------------------------------------------
    # Full ingest pipeline: PDF file -> DB rows
    # ------------------------------------------------------------------
    def ingest(self, user_id, filename, file_path):
        """Returns (document_id, chunks_created)."""
        text = self.extract_text(file_path)
        document_id = self.db.add_document(user_id, filename, file_path)
        chunks = self.chunk_text(text)
        for index, chunk in enumerate(chunks):
            self.db.add_chunk(document_id, index, chunk)
        return document_id, len(chunks)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def search(self, question, limit=TOP_K_CHUNKS):
        """Return the most relevant chunk texts for a question (may be empty)."""
        return self.db.search_chunks(question, limit=limit)

    @staticmethod
    def format_context(chunks):
        """Turn retrieved chunks into a plain-text context block for the agents."""
        if not chunks:
            return ""
        parts = []
        for i, chunk in enumerate(chunks, start=1):
            parts.append(f"[Document excerpt {i}]\n{chunk}")
        return "\n\n".join(parts)
