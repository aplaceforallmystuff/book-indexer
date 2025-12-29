"""ChromaDB indexing operations."""

from pathlib import Path
from typing import List, Optional
import chromadb
from chromadb.utils import embedding_functions
from .processor import DocumentProcessor, DocumentChunk


class BookIndexer:
    """Manages book indexing into ChromaDB."""

    def __init__(
        self,
        chroma_host: str = "localhost",
        chroma_port: int = 8000,
        collection_name: str = "books",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        """
        Initialize indexer.

        Args:
            chroma_host: ChromaDB server host
            chroma_port: ChromaDB server port
            collection_name: Name of collection to use
            embedding_model: Sentence transformer model name
        """
        self.chroma_host = chroma_host
        self.chroma_port = chroma_port
        self.collection_name = collection_name

        # Initialize ChromaDB client
        self.client = chromadb.HttpClient(
            host=chroma_host,
            port=chroma_port,
        )

        # Initialize document processor
        self.processor = DocumentProcessor()

        # Use ChromaDB's built-in embedding function (more efficient)
        embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )

        # Get or create collection with embedding function
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function,
            metadata={"description": "Book and PDF collection for semantic search"}
        )

    def is_document_indexed(self, file_path: Path) -> bool:
        """
        Check if document is already indexed.

        Args:
            file_path: Path to document

        Returns:
            True if document is already indexed
        """
        file_hash = self.processor._calculate_file_hash(file_path)

        # Query for existing document by hash
        results = self.collection.get(
            where={"file_hash": file_hash},
            limit=1
        )

        return len(results['ids']) > 0

    def index_document(
        self, file_path: Path, force: bool = False, batch_size: int = 50
    ) -> dict:
        """
        Index a single document.

        Args:
            file_path: Path to document
            force: Force re-indexing if already exists
            batch_size: Number of chunks to add per batch (reduces memory usage)

        Returns:
            Dictionary with indexing results
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Check if already indexed
        if not force and self.is_document_indexed(file_path):
            return {
                "status": "skipped",
                "reason": "already_indexed",
                "file": str(file_path),
            }

        # Process document based on file type
        suffix = file_path.suffix.lower()
        if suffix == '.pdf':
            chunks, metadata = self.processor.process_pdf(file_path)
        elif suffix == '.epub':
            chunks, metadata = self.processor.process_epub(file_path)
        elif suffix in ('.mobi', '.azw3', '.azw'):
            chunks, metadata = self.processor.process_mobi(file_path)
        else:
            raise ValueError(f"Unsupported file type: {suffix}. Supported: .pdf, .epub, .mobi, .azw3")

        if not chunks:
            return {
                "status": "skipped",
                "reason": "no_text_extracted",
                "file": str(file_path),
            }

        # Add chunks in batches to prevent OOM on large documents
        total_chunks = len(chunks)
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i : i + batch_size]

            ids = [f"{metadata['file_hash']}_{chunk.chunk_index}" for chunk in batch]
            texts = [chunk.text for chunk in batch]
            metadatas = [chunk.metadata for chunk in batch]

            # Add batch to collection (ChromaDB generates embeddings)
            self.collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
            )

        return {
            "status": "indexed",
            "file": str(file_path),
            "chunks": total_chunks,
            "title": metadata["title"],
            "author": metadata["author"],
            "pages": metadata["pages"],
        }

    def delete_document(self, file_path: Path) -> dict:
        """
        Delete a document from the index.

        Args:
            file_path: Path to document

        Returns:
            Dictionary with deletion results
        """
        file_hash = self.processor._calculate_file_hash(file_path)

        # Get all chunk IDs for this document
        results = self.collection.get(
            where={"file_hash": file_hash}
        )

        if not results['ids']:
            return {
                "status": "not_found",
                "file": str(file_path),
            }

        # Delete all chunks
        self.collection.delete(ids=results['ids'])

        return {
            "status": "deleted",
            "file": str(file_path),
            "chunks_deleted": len(results['ids']),
        }

    def list_documents(self) -> List[dict]:
        """
        List all indexed documents.

        Returns:
            List of document metadata
        """
        # Get all results and deduplicate by file_hash
        results = self.collection.get()

        # Group by file_hash to get unique documents
        documents = {}
        for metadata in results['metadatas']:
            file_hash = metadata['file_hash']
            if file_hash not in documents:
                documents[file_hash] = {
                    "title": metadata.get("title", "Unknown"),
                    "author": metadata.get("author", "Unknown"),
                    "filename": metadata.get("filename", "Unknown"),
                    "pages": metadata.get("pages", 0),
                    "file_path": metadata.get("file_path", ""),
                }

        return list(documents.values())

    def search(self, query: str, n_results: int = 10) -> List[dict]:
        """
        Search indexed documents.

        Args:
            query: Search query
            n_results: Number of results to return

        Returns:
            List of search results with text and metadata
        """
        # Query collection (ChromaDB handles embedding generation)
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        # Format results
        search_results = []
        for i, doc_id in enumerate(results['ids'][0]):
            search_results.append({
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i] if results['distances'] else None,
            })

        return search_results
