"""Document processing and chunking."""

import hashlib
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Dict, Any, Optional
import pymupdf  # PyMuPDF
from pydantic import BaseModel

# Calibre's ebook-convert path (macOS)
EBOOK_CONVERT_PATHS = [
    "/Applications/calibre.app/Contents/MacOS/ebook-convert",
    "/usr/bin/ebook-convert",
    "ebook-convert",  # If in PATH
]


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML, preserving paragraph breaks."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_body = False
        self.skip_tags = {'script', 'style', 'head', 'title', 'meta', 'link'}
        self.current_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.current_skip += 1
        if tag == 'body':
            self.in_body = True
        elif tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'):
            self.text_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.current_skip -= 1
        if tag == 'body':
            self.in_body = False
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text_parts.append('\n')

    def handle_data(self, data):
        if self.current_skip == 0:
            self.text_parts.append(data)

    def get_text(self):
        return ''.join(self.text_parts)


class DocumentChunk(BaseModel):
    """Represents a chunk of text from a document."""

    text: str
    page_number: int
    chunk_index: int
    metadata: Dict[str, Any]


class DocumentProcessor:
    """Process documents and extract text chunks."""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        """
        Initialize processor.

        Args:
            chunk_size: Target size for text chunks (in characters)
            chunk_overlap: Overlap between chunks (in characters)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_pdf(self, file_path: Path) -> tuple[List[DocumentChunk], Dict[str, Any]]:
        """
        Extract text and metadata from PDF.

        Args:
            file_path: Path to PDF file

        Returns:
            Tuple of (chunks, metadata)

        Raises:
            ValueError: If PDF is corrupted or cannot be processed
        """
        # Calculate file hash for deduplication
        file_hash = self._calculate_file_hash(file_path)

        # Open PDF and validate
        try:
            doc = pymupdf.open(file_path)
        except Exception as e:
            raise ValueError(f"Failed to open PDF: {e}")

        # Validate PDF has content
        if len(doc) == 0:
            doc.close()
            raise ValueError("PDF has no pages")

        # Test first page extraction to catch early corruption
        try:
            first_page = doc[0]
            _ = first_page.get_text()
        except Exception as e:
            doc.close()
            raise ValueError(f"PDF appears corrupted - cannot extract text from first page: {e}")

        # Extract metadata
        metadata = {
            "filename": file_path.name,
            "file_path": str(file_path.absolute()),
            "file_hash": file_hash,
            "title": doc.metadata.get("title", file_path.stem),
            "author": doc.metadata.get("author", "Unknown"),
            "pages": len(doc),
            "subject": doc.metadata.get("subject", ""),
            "keywords": doc.metadata.get("keywords", ""),
        }

        # Extract text by page and chunk
        chunks = []
        chunk_index = 0
        error_count = 0
        max_errors = 5  # Allow some corrupted pages but not too many

        for page_num, page in enumerate(doc, start=1):
            try:
                page_text = page.get_text()

                # Skip empty pages
                if not page_text.strip():
                    continue

                # Chunk the page text
                page_chunks = self._chunk_text(page_text)

                for chunk_text in page_chunks:
                    chunk = DocumentChunk(
                        text=chunk_text,
                        page_number=page_num,
                        chunk_index=chunk_index,
                        metadata={
                            **metadata,
                            "page_number": page_num,
                            "chunk_index": chunk_index,
                        }
                    )
                    chunks.append(chunk)
                    chunk_index += 1

            except Exception as e:
                error_count += 1
                if error_count > max_errors:
                    doc.close()
                    raise ValueError(f"Too many errors processing PDF (page {page_num}): {e}")
                # Otherwise skip the corrupted page and continue

        doc.close()

        if not chunks:
            raise ValueError("No text could be extracted from PDF")

        return chunks, metadata

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        # Simple character-based chunking
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundary (only if it's far enough from start)
            if end < len(text):
                # Look for sentence endings in the last quarter of the chunk
                search_start = start + (self.chunk_size * 3 // 4)
                for punct in ['. ', '! ', '? ', '\n\n']:
                    last_punct = text.rfind(punct, search_start, end)
                    if last_punct != -1:
                        end = last_punct + len(punct)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start position with overlap, ensuring forward progress
            next_start = end - self.chunk_overlap
            if next_start <= start:
                next_start = start + max(1, self.chunk_size // 2)
            start = next_start

        return chunks

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for deduplication."""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    def process_epub(self, file_path: Path) -> tuple[List[DocumentChunk], Dict[str, Any]]:
        """
        Extract text and metadata from ePub.

        Args:
            file_path: Path to ePub file

        Returns:
            Tuple of (chunks, metadata)

        Raises:
            ValueError: If ePub is corrupted or cannot be processed
        """
        file_hash = self._calculate_file_hash(file_path)

        try:
            epub = zipfile.ZipFile(file_path, 'r')
        except Exception as e:
            raise ValueError(f"Failed to open ePub: {e}")

        # Parse container.xml to find content.opf
        try:
            container = epub.read('META-INF/container.xml')
            container_root = ET.fromstring(container)
            ns = {'container': 'urn:oasis:names:tc:opendocument:xmlns:container'}
            rootfile = container_root.find('.//container:rootfile', ns)
            if rootfile is None:
                raise ValueError("Could not find rootfile in container.xml")
            opf_path = rootfile.get('full-path')
        except Exception as e:
            epub.close()
            raise ValueError(f"Failed to parse ePub structure: {e}")

        # Parse content.opf for metadata and spine
        try:
            opf_content = epub.read(opf_path)
            opf_root = ET.fromstring(opf_content)
            opf_dir = str(Path(opf_path).parent)
            if opf_dir == '.':
                opf_dir = ''

            # Extract metadata
            dc_ns = {'dc': 'http://purl.org/dc/elements/1.1/'}
            opf_ns = {'opf': 'http://www.idpf.org/2007/opf'}

            title_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}title')
            author_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}creator')

            title = title_el.text if title_el is not None and title_el.text else file_path.stem
            author = author_el.text if author_el is not None and author_el.text else "Unknown"

            # Get spine order (reading order of chapters)
            spine = opf_root.find('.//{http://www.idpf.org/2007/opf}spine')
            manifest = opf_root.find('.//{http://www.idpf.org/2007/opf}manifest')

            # Build id -> href mapping from manifest
            id_to_href = {}
            for item in manifest.findall('.//{http://www.idpf.org/2007/opf}item'):
                item_id = item.get('id')
                href = item.get('href')
                media_type = item.get('media-type', '')
                if 'html' in media_type or 'xhtml' in media_type:
                    id_to_href[item_id] = href

            # Get ordered content files from spine
            content_files = []
            for itemref in spine.findall('.//{http://www.idpf.org/2007/opf}itemref'):
                idref = itemref.get('idref')
                if idref in id_to_href:
                    href = id_to_href[idref]
                    if opf_dir:
                        full_path = f"{opf_dir}/{href}"
                    else:
                        full_path = href
                    content_files.append(full_path)

        except Exception as e:
            epub.close()
            raise ValueError(f"Failed to parse ePub metadata: {e}")

        metadata = {
            "filename": file_path.name,
            "file_path": str(file_path.absolute()),
            "file_hash": file_hash,
            "title": title,
            "author": author,
            "pages": len(content_files),  # chapters as "pages"
            "format": "epub",
        }

        # Extract text from each content file (chapter)
        chunks = []
        chunk_index = 0

        for chapter_num, content_path in enumerate(content_files, start=1):
            try:
                content = epub.read(content_path).decode('utf-8', errors='ignore')

                # Parse HTML and extract text
                parser = HTMLTextExtractor()
                parser.feed(content)
                chapter_text = parser.get_text().strip()

                if not chapter_text:
                    continue

                # Chunk the chapter text
                chapter_chunks = self._chunk_text(chapter_text)

                for chunk_text in chapter_chunks:
                    chunk = DocumentChunk(
                        text=chunk_text,
                        page_number=chapter_num,  # chapter as page
                        chunk_index=chunk_index,
                        metadata={
                            **metadata,
                            "page_number": chapter_num,
                            "chunk_index": chunk_index,
                            "chapter": chapter_num,
                        }
                    )
                    chunks.append(chunk)
                    chunk_index += 1

            except Exception:
                # Skip problematic chapters
                continue

        epub.close()

        if not chunks:
            raise ValueError("No text could be extracted from ePub")

        return chunks, metadata

    def _find_ebook_convert(self) -> Optional[str]:
        """Find ebook-convert executable."""
        for path in EBOOK_CONVERT_PATHS:
            if Path(path).exists():
                return path
            # Check if it's in PATH
            try:
                result = subprocess.run(
                    ["which", path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except Exception:
                pass
        return None

    def process_mobi(self, file_path: Path) -> tuple[List[DocumentChunk], Dict[str, Any]]:
        """
        Extract text from MOBI/AZW3/AZW by converting to EPUB first.

        Args:
            file_path: Path to MOBI file

        Returns:
            Tuple of (chunks, metadata)

        Raises:
            ValueError: If conversion fails or no text extracted
        """
        ebook_convert = self._find_ebook_convert()
        if not ebook_convert:
            raise ValueError(
                "ebook-convert not found. Install Calibre or ensure it's in PATH."
            )

        # Create temp file for converted EPUB
        with tempfile.NamedTemporaryFile(suffix='.epub', delete=False) as tmp:
            tmp_epub = Path(tmp.name)

        try:
            # Convert to EPUB
            result = subprocess.run(
                [ebook_convert, str(file_path), str(tmp_epub)],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )

            if result.returncode != 0:
                raise ValueError(f"Conversion failed: {result.stderr[:200]}")

            # Process the converted EPUB
            chunks, metadata = self.process_epub(tmp_epub)

            # Update metadata to reflect original file
            metadata['filename'] = file_path.name
            metadata['file_path'] = str(file_path.absolute())
            metadata['file_hash'] = self._calculate_file_hash(file_path)
            metadata['format'] = file_path.suffix.lower().strip('.')
            metadata['converted_from'] = file_path.suffix.lower()

            # Update chunk metadata too
            for chunk in chunks:
                chunk.metadata['filename'] = file_path.name
                chunk.metadata['file_path'] = str(file_path.absolute())
                chunk.metadata['file_hash'] = metadata['file_hash']

            return chunks, metadata

        finally:
            # Clean up temp file
            if tmp_epub.exists():
                tmp_epub.unlink()
