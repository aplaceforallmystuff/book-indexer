# Contributing to Book Indexer

Thanks for your interest in contributing! This document outlines how to get started.

## Getting Started

1. **Fork the repository**
   ```bash
   gh repo fork aplaceforallmystuff/book-indexer
   ```

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR-USERNAME/book-indexer.git
   cd book-indexer
   ```

3. **Install in development mode**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development

### Project Structure

```
book-indexer/
├── src/book_indexer/
│   ├── cli.py          # Click CLI commands
│   ├── processor.py    # Document text extraction
│   ├── indexer.py      # ChromaDB operations
│   └── calibre.py      # Calibre library integration
├── pyproject.toml      # Package configuration
└── README.md
```

### Running Locally

```bash
# Run CLI commands directly
book-indexer --help

# Or run as module
python -m book_indexer --help
```

### Testing with ChromaDB

Start a local ChromaDB instance:
```bash
docker run -d --name chromadb -p 8000:8000 chromadb/chroma:latest
```

## Adding Features

### New CLI Commands

Add commands in `cli.py` using Click decorators:

```python
@cli.command()
@click.argument("query")
@click.option("--limit", default=10)
def my_command(query: str, limit: int):
    """Description of what this command does."""
    # Implementation
```

### New Document Formats

Extend `processor.py` to support additional formats:

1. Add format detection in `_get_format()`
2. Implement extraction in `_extract_[format]()`
3. Update supported formats list in README

## Code Style

- Use type hints for function signatures
- Follow PEP 8 conventions
- Keep functions focused and testable
- Add docstrings for public functions

## Submitting Changes

1. **Commit your changes**
   ```bash
   git add -A
   git commit -m "feat: add your feature description"
   ```

2. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

3. **Create a Pull Request**
   - Go to the original repository
   - Click "New Pull Request"
   - Select your branch
   - Describe your changes

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code restructuring
- `chore:` - Maintenance tasks

## Questions?

Open an issue for bugs, feature requests, or questions.
