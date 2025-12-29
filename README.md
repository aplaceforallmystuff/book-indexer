# Book Indexer

[![PyPI version](https://img.shields.io/pypi/v/book-indexer.svg)](https://pypi.org/project/book-indexer/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

CLI tool to index books and PDFs into ChromaDB for semantic search. Built for use with Claude Code agents.

## Features

- **Multi-format support** - PDF, ePub, MOBI, AZW3
- **Calibre integration** - Sync books by tag from your Calibre library
- **Semantic search** - Query your book collection with natural language
- **Chunked indexing** - Smart text chunking with configurable overlap
- **Deduplication** - File hashing prevents duplicate entries
- **Rich CLI** - Progress bars and formatted output

## Installation

```bash
pip install book-indexer
```

Or install from source:

```bash
git clone https://github.com/aplaceforallmystuff/book-indexer.git
cd book-indexer
pip install -e .
```

## Requirements

- Python 3.9+
- ChromaDB instance (Docker recommended)
- Calibre (optional, for library integration)

## Quick Start

### 1. Start ChromaDB

```bash
docker run -d \
  --name chromadb \
  -p 8000:8000 \
  -v chroma-data:/chroma/chroma \
  chromadb/chroma:latest
```

### 2. Index some books

```bash
# Add a single file
book-indexer add ~/Documents/my-book.pdf

# Add all PDFs in a directory
book-indexer add-dir ~/Documents/Books --pattern "*.pdf"

# Sync books with a specific tag from Calibre
book-indexer calibre-sync --tag "AI" --library ~/calibre_library
```

### 3. Search your collection

```bash
book-indexer search "machine learning algorithms" --limit 5
```

## Commands

### Document Management

| Command | Description |
|---------|-------------|
| `add FILE` | Index a single file |
| `add-dir DIR` | Index all matching files in directory |
| `remove TITLE` | Remove a document from the index |
| `list` | List all indexed documents |
| `search QUERY` | Semantic search across all documents |

### Calibre Integration

| Command | Description |
|---------|-------------|
| `calibre-stats` | Show library statistics |
| `calibre-tags` | List all tags with book counts |
| `calibre-search QUERY` | Search Calibre by title/author |
| `calibre-sync` | Sync books with specific tag to ChromaDB |

## Configuration

Default settings connect to `localhost:8000`. Override with environment variables or CLI options:

```bash
# Environment variables
export CHROMA_HOST="your-server.local"
export CHROMA_PORT="8000"
export CHROMA_COLLECTION="books"

# Or use CLI options
book-indexer search "privacy" --host your-server.local --port 8000
```

## Using with Claude Code

This tool was built to power book-backed Claude Code agents. Create an agent that searches your indexed library:

```markdown
---
name: librarian
description: Research librarian with access to your book collection
tools: Bash, Read
model: sonnet
---

<available_tools>
<tool name="book search">
Search indexed books semantically.

\`\`\`bash
book-indexer search "your query" --limit 10
\`\`\`
</tool>
</available_tools>
```

## Architecture

```
book-indexer/
├── cli.py          # Command-line interface
├── processor.py    # PDF/ePub/MOBI text extraction and chunking
├── indexer.py      # ChromaDB operations
└── calibre.py      # Calibre library integration
```

**Processing pipeline:**
1. Extract text from document (per page/chapter)
2. Chunk text (~500 chars with 50 char overlap)
3. Generate embeddings (sentence-transformers via ChromaDB)
4. Store in ChromaDB with metadata

**Metadata stored:**
- Title, Author, Filename
- Page/chapter number, Chunk index
- File hash (for deduplication)

## License

MIT
