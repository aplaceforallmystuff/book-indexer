# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.2.0] - 2025-12-06

### Added
- **ePub support** - Native parsing via zipfile + XML (no external dependencies)
- **MOBI/AZW3/AZW support** - Via Calibre's ebook-convert tool
- **Calibre integration** - New `CalibreLibrary` class for reading Calibre SQLite database
- **New CLI commands:**
  - `calibre-stats` - Show library statistics
  - `calibre-tags` - List all tags with book counts
  - `calibre-search` - Search Calibre library by title/author
  - `calibre-sync` - Sync books with specific tag to ChromaDB
- **`--batch-size` flag** - Control memory usage for large documents (default: 50)
- **`--dry-run` flag** - Preview what would be synced without indexing

### Fixed
- **Memory issues (OOM)** - Implemented batch processing for ChromaDB adds (50 chunks per batch)
- **Infinite loop bug** - Fixed `_chunk_text()` where sentence boundary search could cause start position to go backwards

### Changed
- Improved error messages for unsupported file types

## [0.1.0] - 2025-12-02

### Added
- Initial release
- PDF text extraction via PyMuPDF
- ChromaDB integration with sentence-transformer embeddings
- CLI commands: `add`, `add-dir`, `remove`, `list`, `search`
- Deduplication via file hash
- Rich terminal output with progress bars
