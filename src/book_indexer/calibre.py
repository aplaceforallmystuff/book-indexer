"""Calibre library database access."""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class CalibreBook:
    """Represents a book from Calibre library."""
    id: int
    title: str
    authors: List[str]
    tags: List[str]
    formats: List[str]  # Available formats (epub, pdf, mobi, etc.)
    path: str  # Relative path within library
    series: Optional[str] = None
    series_index: Optional[float] = None

    def get_format_path(self, library_path: Path, format: str) -> Optional[Path]:
        """Get full path to a specific format file."""
        format = format.upper()
        if format not in [f.upper() for f in self.formats]:
            return None

        # Calibre stores files as: library/Author/Title (ID)/Title - Author.format
        book_dir = library_path / self.path
        for file in book_dir.iterdir():
            if file.suffix.upper() == f'.{format}':
                return file
        return None

    def get_best_format(self, library_path: Path, preferred: List[str] = None) -> Optional[Path]:
        """Get path to best available format, preferring epub > pdf > mobi."""
        if preferred is None:
            preferred = ['EPUB', 'PDF', 'MOBI', 'AZW3', 'AZW']

        for fmt in preferred:
            path = self.get_format_path(library_path, fmt)
            if path and path.exists():
                return path
        return None


class CalibreLibrary:
    """Read-only access to Calibre library database."""

    def __init__(self, library_path: str | Path):
        """
        Initialize Calibre library connection.

        Args:
            library_path: Path to Calibre library folder (contains metadata.db)
        """
        self.library_path = Path(library_path)
        self.db_path = self.library_path / 'metadata.db'

        if not self.db_path.exists():
            raise FileNotFoundError(f"Calibre database not found: {self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        """Create database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Get all tags in the library."""
        conn = self._connect()
        cursor = conn.execute("""
            SELECT t.id, t.name, COUNT(btl.book) as book_count
            FROM tags t
            LEFT JOIN books_tags_link btl ON t.id = btl.tag
            GROUP BY t.id, t.name
            ORDER BY t.name
        """)
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def get_books_by_tag(self, tag_name: str) -> List[CalibreBook]:
        """
        Get all books with a specific tag.

        Args:
            tag_name: Tag name to filter by (case-insensitive)

        Returns:
            List of CalibreBook objects
        """
        conn = self._connect()

        # Get books with the specified tag
        cursor = conn.execute("""
            SELECT DISTINCT b.id, b.title, b.path, b.series_index
            FROM books b
            JOIN books_tags_link btl ON b.id = btl.book
            JOIN tags t ON btl.tag = t.id
            WHERE t.name = ? COLLATE NOCASE
            ORDER BY b.title
        """, (tag_name,))

        books = []
        for row in cursor.fetchall():
            book = self._build_book(conn, dict(row))
            books.append(book)

        conn.close()
        return books

    def get_book_by_id(self, book_id: int) -> Optional[CalibreBook]:
        """Get a specific book by ID."""
        conn = self._connect()

        cursor = conn.execute("""
            SELECT id, title, path, series_index
            FROM books
            WHERE id = ?
        """, (book_id,))

        row = cursor.fetchone()
        if not row:
            conn.close()
            return None

        book = self._build_book(conn, dict(row))
        conn.close()
        return book

    def search_books(self, query: str, limit: int = 50) -> List[CalibreBook]:
        """
        Search books by title or author.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching CalibreBook objects
        """
        conn = self._connect()

        cursor = conn.execute("""
            SELECT DISTINCT b.id, b.title, b.path, b.series_index
            FROM books b
            LEFT JOIN books_authors_link bal ON b.id = bal.book
            LEFT JOIN authors a ON bal.author = a.id
            WHERE b.title LIKE ? OR a.name LIKE ?
            ORDER BY b.title
            LIMIT ?
        """, (f'%{query}%', f'%{query}%', limit))

        books = []
        for row in cursor.fetchall():
            book = self._build_book(conn, dict(row))
            books.append(book)

        conn.close()
        return books

    def _build_book(self, conn: sqlite3.Connection, book_row: Dict) -> CalibreBook:
        """Build a CalibreBook object with all related data."""
        book_id = book_row['id']

        # Get authors
        cursor = conn.execute("""
            SELECT a.name
            FROM authors a
            JOIN books_authors_link bal ON a.id = bal.author
            WHERE bal.book = ?
            ORDER BY a.name
        """, (book_id,))
        authors = [row['name'] for row in cursor.fetchall()]

        # Get tags
        cursor = conn.execute("""
            SELECT t.name
            FROM tags t
            JOIN books_tags_link btl ON t.id = btl.tag
            WHERE btl.book = ?
            ORDER BY t.name
        """, (book_id,))
        tags = [row['name'] for row in cursor.fetchall()]

        # Get formats
        cursor = conn.execute("""
            SELECT format
            FROM data
            WHERE book = ?
        """, (book_id,))
        formats = [row['format'] for row in cursor.fetchall()]

        # Get series
        cursor = conn.execute("""
            SELECT s.name
            FROM series s
            JOIN books_series_link bsl ON s.id = bsl.series
            WHERE bsl.book = ?
        """, (book_id,))
        series_row = cursor.fetchone()
        series = series_row['name'] if series_row else None

        return CalibreBook(
            id=book_id,
            title=book_row['title'],
            authors=authors,
            tags=tags,
            formats=formats,
            path=book_row['path'],
            series=series,
            series_index=book_row.get('series_index'),
        )

    def get_library_stats(self) -> Dict[str, int]:
        """Get library statistics."""
        conn = self._connect()

        stats = {}

        cursor = conn.execute("SELECT COUNT(*) FROM books")
        stats['total_books'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM authors")
        stats['total_authors'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(*) FROM tags")
        stats['total_tags'] = cursor.fetchone()[0]

        cursor = conn.execute("SELECT COUNT(DISTINCT format) FROM data")
        stats['total_formats'] = cursor.fetchone()[0]

        conn.close()
        return stats
