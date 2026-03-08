"""BookLore library database access via MariaDB."""

import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import pymysql


@dataclass
class BookLoreBook:
    """Represents a book from BookLore library."""
    id: int
    title: str
    authors: List[str]
    tags: List[str]
    formats: List[str]
    files: Dict[str, Path] = field(default_factory=dict)
    series: Optional[str] = None
    series_index: Optional[float] = None

    def get_best_format(self, preferred: List[str] = None) -> Optional[Path]:
        """Get path to best available format, preferring EPUB > PDF > MOBI."""
        if preferred is None:
            preferred = ["EPUB", "PDF", "MOBI"]

        for fmt in preferred:
            if fmt in self.files:
                path = self.files[fmt]
                if path.exists():
                    return path
        return next((p for p in self.files.values() if p.exists()), None)


def _detect_mount_map() -> Dict[str, str]:
    """Auto-detect BookLore container mount mappings from Docker."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "booklore"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        mount_map = {}
        for mount in data[0].get("Mounts", []):
            dest = mount.get("Destination", "")
            source = mount.get("Source", "")
            # Strip /host_mnt prefix (Docker Desktop on macOS)
            if source.startswith("/host_mnt"):
                source = source[len("/host_mnt"):]
            if dest and source and dest != "/app/data":
                mount_map[dest] = source
        return mount_map
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return {}


class BookLoreLibrary:
    """Read-only access to BookLore's MariaDB database."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 3307,
        user: str = "booklore",
        password: str = "",
        database: str = "booklore",
        mount_map: Optional[Dict[str, str]] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.mount_map = mount_map if mount_map is not None else _detect_mount_map()

        if not self.mount_map:
            raise ConnectionError(
                "Could not detect BookLore Docker mount mappings. "
                "Pass --mount-map or ensure the booklore container is running."
            )

    def _connect(self) -> pymysql.Connection:
        """Create database connection."""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _resolve_host_path(
        self, library_path: str, file_sub_path: Optional[str], file_name: str
    ) -> Path:
        """Map container path to host filesystem using mount_map.

        library_path comes from library_path.path and may be a mount root
        like '/books' or a subdirectory like '/comics/Archie'. We find the
        longest matching mount prefix and replace it with the host path.
        """
        # Find best (longest) mount prefix match
        best_mount = None
        for mount_dest in sorted(self.mount_map, key=len, reverse=True):
            if library_path == mount_dest or library_path.startswith(mount_dest + "/"):
                best_mount = mount_dest
                break

        if not best_mount:
            raise ValueError(
                f"No mount mapping for container path '{library_path}'. "
                f"Known mounts: {list(self.mount_map.keys())}"
            )

        # Replace container prefix with host path
        host_base = self.mount_map[best_mount]
        remainder = library_path[len(best_mount):]  # e.g. "/Archie" or ""

        parts = [host_base + remainder]
        if file_sub_path:
            parts.append(file_sub_path)
        parts.append(file_name)

        return Path("/".join(parts))

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Get all tags with book counts."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.id, t.name, COUNT(tm.book_id) as book_count
                    FROM tag t
                    LEFT JOIN book_metadata_tag_mapping tm ON t.id = tm.tag_id
                    GROUP BY t.id, t.name
                    ORDER BY t.name
                """)
                return cur.fetchall()
        finally:
            conn.close()

    def get_books_by_tag(self, tag_name: str) -> List[BookLoreBook]:
        """Get all books with a specific tag."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT b.id, bm.title, bm.series_name, bm.series_number
                    FROM book b
                    JOIN book_metadata bm ON b.id = bm.book_id
                    JOIN book_metadata_tag_mapping tm ON b.id = tm.book_id
                    JOIN tag t ON tm.tag_id = t.id
                    WHERE t.name = %s AND b.deleted = 0
                    ORDER BY bm.title
                """, (tag_name,))
                rows = cur.fetchall()

            books = []
            for row in rows:
                book = self._build_book(conn, row)
                books.append(book)
            return books
        finally:
            conn.close()

    def search_books(self, query: str, limit: int = 50) -> List[BookLoreBook]:
        """Search books by title or author."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT b.id, bm.title, bm.series_name, bm.series_number
                    FROM book b
                    JOIN book_metadata bm ON b.id = bm.book_id
                    LEFT JOIN book_metadata_author_mapping am ON b.id = am.book_id
                    LEFT JOIN author a ON am.author_id = a.id
                    WHERE (bm.title LIKE %s OR a.name LIKE %s) AND b.deleted = 0
                    ORDER BY bm.title
                    LIMIT %s
                """, (f"%{query}%", f"%{query}%", limit))
                rows = cur.fetchall()

            books = []
            for row in rows:
                book = self._build_book(conn, row)
                books.append(book)
            return books
        finally:
            conn.close()

    def get_library_stats(self) -> Dict[str, int]:
        """Get library statistics."""
        conn = self._connect()
        try:
            stats = {}
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) as c FROM book WHERE deleted = 0")
                stats["total_books"] = cur.fetchone()["c"]

                cur.execute("SELECT COUNT(*) as c FROM author")
                stats["total_authors"] = cur.fetchone()["c"]

                cur.execute("SELECT COUNT(*) as c FROM tag")
                stats["total_tags"] = cur.fetchone()["c"]

                cur.execute(
                    "SELECT COUNT(DISTINCT book_type) as c FROM book_file WHERE is_book = 1"
                )
                stats["total_formats"] = cur.fetchone()["c"]

                cur.execute("SELECT COUNT(DISTINCT library_id) as c FROM book WHERE deleted = 0")
                stats["total_libraries"] = cur.fetchone()["c"]

            return stats
        finally:
            conn.close()

    def _build_book(self, conn: pymysql.Connection, book_row: Dict) -> BookLoreBook:
        """Build a BookLoreBook with all related data."""
        book_id = book_row["id"]

        with conn.cursor() as cur:
            # Authors
            cur.execute("""
                SELECT a.name
                FROM author a
                JOIN book_metadata_author_mapping am ON a.id = am.author_id
                WHERE am.book_id = %s
                ORDER BY am.sort_order
            """, (book_id,))
            authors = [r["name"] for r in cur.fetchall()]

            # Tags
            cur.execute("""
                SELECT t.name
                FROM tag t
                JOIN book_metadata_tag_mapping tm ON t.id = tm.tag_id
                WHERE tm.book_id = %s
                ORDER BY t.name
            """, (book_id,))
            tags = [r["name"] for r in cur.fetchall()]

            # Files with library path for mount resolution
            cur.execute("""
                SELECT bf.file_name, bf.file_sub_path, bf.book_type,
                       lp.path as library_path
                FROM book_file bf
                JOIN book b ON bf.book_id = b.id
                JOIN library_path lp ON b.library_path_id = lp.id
                WHERE bf.book_id = %s AND bf.is_book = 1
            """, (book_id,))
            file_rows = cur.fetchall()

        formats = []
        files = {}
        for fr in file_rows:
            fmt = fr["book_type"]
            formats.append(fmt)
            try:
                files[fmt] = self._resolve_host_path(
                    fr["library_path"], fr["file_sub_path"], fr["file_name"]
                )
            except ValueError:
                pass  # Skip files with unmapped library paths

        return BookLoreBook(
            id=book_id,
            title=book_row["title"],
            authors=authors,
            tags=tags,
            formats=formats,
            files=files,
            series=book_row.get("series_name"),
            series_index=book_row.get("series_number"),
        )
