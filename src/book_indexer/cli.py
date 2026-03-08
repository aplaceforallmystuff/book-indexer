"""Command-line interface for book-indexer."""

import os
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from .indexer import BookIndexer
from .calibre import CalibreLibrary


console = Console()

# Default Calibre library path
DEFAULT_CALIBRE_LIBRARY = os.path.expanduser("~/calibre_library")


@click.group()
@click.version_option()
def main():
    """Index books and PDFs into ChromaDB for semantic search."""
    pass


@main.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--force', is_flag=True, help='Force re-indexing if already exists')
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
@click.option('--batch-size', default=50, type=int, help='Chunks per batch (lower = less memory)')
def add(file_path: str, force: bool, host: str, port: int, collection: str, batch_size: int):
    """
    Add a document to the index.

    Example:
        book-indexer add ~/Documents/my-book.pdf
        book-indexer add ~/Documents/large-book.pdf --batch-size 25
    """
    indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

    with console.status("[bold green]Processing document..."):
        try:
            result = indexer.index_document(Path(file_path), force=force, batch_size=batch_size)

            if result['status'] == 'skipped':
                console.print(f"[yellow]⊘ Skipped: {result['reason']} - {result['file']}[/yellow]")
            elif result['status'] == 'indexed':
                console.print(f"[green]✓ Indexed:[/green] {result['file']}")
                console.print(f"  Title: {result['title']}")
                console.print(f"  Author: {result['author']}")
                console.print(f"  Chunks: {result['chunks']} ({result['pages']} pages)")
        except Exception as e:
            console.print(f"[red]✗ Error:[/red] {e}")
            raise click.Abort()


@main.command()
@click.argument('directory', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--force', is_flag=True, help='Force re-indexing if already exists')
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
@click.option('--pattern', default='*.pdf', help='File pattern to match')
@click.option('--batch-size', default=50, type=int, help='Chunks per batch (lower = less memory)')
def add_dir(directory: str, force: bool, host: str, port: int, collection: str, pattern: str, batch_size: int):
    """
    Add all documents in a directory to the index.

    Example:
        book-indexer add-dir ~/Documents/Books --pattern "*.pdf"
        book-indexer add-dir ~/Documents/Books --pattern "*.epub" --batch-size 25
    """
    indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

    # Find all matching files
    dir_path = Path(directory)
    files = list(dir_path.rglob(pattern))

    if not files:
        console.print(f"[yellow]No files found matching pattern: {pattern}[/yellow]")
        return

    console.print(f"[cyan]Found {len(files)} file(s) to process[/cyan]\n")

    # Process each file
    results = {
        'indexed': [],
        'skipped': [],
        'errors': [],
    }

    with Progress() as progress:
        task = progress.add_task("[cyan]Indexing...", total=len(files))

        for file_path in files:
            try:
                result = indexer.index_document(file_path, force=force, batch_size=batch_size)

                if result['status'] == 'indexed':
                    results['indexed'].append(result)
                    console.print(f"[green]✓[/green] {file_path.name}")
                elif result['status'] == 'skipped':
                    results['skipped'].append(result)
                    console.print(f"[yellow]⊘[/yellow] {file_path.name} ({result['reason']})")

            except Exception as e:
                results['errors'].append({'file': str(file_path), 'error': str(e)})
                console.print(f"[red]✗[/red] {file_path.name}: {e}")

            progress.update(task, advance=1)

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Indexed: [green]{len(results['indexed'])}[/green]")
    console.print(f"  Skipped: [yellow]{len(results['skipped'])}[/yellow]")
    console.print(f"  Errors: [red]{len(results['errors'])}[/red]")


@main.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
def remove(file_path: str, host: str, port: int, collection: str):
    """
    Remove a document from the index.

    Example:
        book-indexer remove ~/Documents/my-book.pdf
    """
    indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

    with console.status("[bold yellow]Removing document..."):
        result = indexer.delete_document(Path(file_path))

        if result['status'] == 'deleted':
            console.print(f"[green]✓ Deleted:[/green] {result['file']}")
            console.print(f"  Chunks removed: {result['chunks_deleted']}")
        elif result['status'] == 'not_found':
            console.print(f"[yellow]⊘ Not found in index:[/yellow] {result['file']}")


@main.command()
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
def list(host: str, port: int, collection: str):
    """
    List all indexed documents.

    Example:
        book-indexer list
    """
    indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

    with console.status("[bold cyan]Fetching documents..."):
        documents = indexer.list_documents()

    if not documents:
        console.print("[yellow]No documents indexed yet[/yellow]")
        return

    # Create table
    table = Table(title=f"Indexed Documents ({len(documents)})")
    table.add_column("Title", style="cyan")
    table.add_column("Author", style="magenta")
    table.add_column("Pages", justify="right", style="green")
    table.add_column("Filename", style="dim")

    for doc in sorted(documents, key=lambda x: x['title']):
        table.add_row(
            doc['title'],
            doc['author'],
            str(doc['pages']),
            doc['filename'],
        )

    console.print(table)


@main.command()
@click.argument('query')
@click.option('--limit', default=10, type=int, help='Number of results to return')
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
def search(query: str, limit: int, host: str, port: int, collection: str):
    """
    Search indexed documents.

    Example:
        book-indexer search "machine learning algorithms"
    """
    indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

    with console.status(f"[bold cyan]Searching for: {query}..."):
        results = indexer.search(query, n_results=limit)

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results)} result(s):[/bold]\n")

    for i, result in enumerate(results, start=1):
        metadata = result['metadata']
        console.print(f"[bold cyan]{i}. {metadata.get('title', 'Unknown')}[/bold cyan]")
        console.print(f"   Author: {metadata.get('author', 'Unknown')}")
        console.print(f"   Page: {metadata.get('page_number', '?')}")

        if result.get('distance') is not None:
            similarity = 1 - result['distance']
            console.print(f"   Similarity: {similarity:.2%}")

        console.print(f"\n   {result['text'][:300]}{'...' if len(result['text']) > 300 else ''}\n")


# ============================================================================
# Calibre Integration Commands
# ============================================================================

@main.command('calibre-stats')
@click.option('--library', default=DEFAULT_CALIBRE_LIBRARY, help='Path to Calibre library')
def calibre_stats(library: str):
    """
    Show Calibre library statistics.

    Example:
        book-indexer calibre-stats
    """
    try:
        cal = CalibreLibrary(library)
        stats = cal.get_library_stats()

        console.print("\n[bold cyan]Calibre Library Statistics[/bold cyan]\n")
        console.print(f"  Books:   [green]{stats['total_books']:,}[/green]")
        console.print(f"  Authors: [green]{stats['total_authors']:,}[/green]")
        console.print(f"  Tags:    [green]{stats['total_tags']:,}[/green]")
        console.print(f"  Formats: [green]{stats['total_formats']}[/green]")
        console.print(f"\n  Library: [dim]{library}[/dim]\n")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('calibre-tags')
@click.option('--library', default=DEFAULT_CALIBRE_LIBRARY, help='Path to Calibre library')
@click.option('--min-books', default=1, type=int, help='Only show tags with at least N books')
def calibre_tags(library: str, min_books: int):
    """
    List all Calibre tags with book counts.

    Example:
        book-indexer calibre-tags
        book-indexer calibre-tags --min-books 5
    """
    try:
        cal = CalibreLibrary(library)
        tags = cal.get_all_tags()

        # Filter by min_books
        tags = [t for t in tags if t['book_count'] >= min_books]

        if not tags:
            console.print("[yellow]No tags found matching criteria[/yellow]")
            return

        table = Table(title=f"Calibre Tags ({len(tags)} total)")
        table.add_column("Tag", style="cyan")
        table.add_column("Books", justify="right", style="green")

        # Sort by book count descending
        for tag in sorted(tags, key=lambda x: x['book_count'], reverse=True):
            # Truncate very long tag names
            name = tag['name'][:60] + '...' if len(tag['name']) > 60 else tag['name']
            table.add_row(name, str(tag['book_count']))

        console.print(table)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('calibre-search')
@click.argument('query')
@click.option('--library', default=DEFAULT_CALIBRE_LIBRARY, help='Path to Calibre library')
@click.option('--limit', default=20, type=int, help='Maximum results')
def calibre_search(query: str, library: str, limit: int):
    """
    Search Calibre library by title or author.

    Example:
        book-indexer calibre-search "science fiction"
    """
    try:
        cal = CalibreLibrary(library)
        books = cal.search_books(query, limit=limit)

        if not books:
            console.print(f"[yellow]No books found matching: {query}[/yellow]")
            return

        table = Table(title=f"Search Results ({len(books)} found)")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Author", style="magenta")
        table.add_column("Formats", style="green")
        table.add_column("Tags", style="dim")

        for book in books:
            table.add_row(
                str(book.id),
                book.title[:50] + '...' if len(book.title) > 50 else book.title,
                ', '.join(book.authors)[:30] or 'Unknown',
                ', '.join(book.formats),
                ', '.join(book.tags[:3]) + ('...' if len(book.tags) > 3 else ''),
            )

        console.print(table)

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('calibre-sync')
@click.argument('tag')
@click.option('--library', default=DEFAULT_CALIBRE_LIBRARY, help='Path to Calibre library')
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
@click.option('--batch-size', default=50, type=int, help='Chunks per batch')
@click.option('--force', is_flag=True, help='Force re-indexing')
@click.option('--dry-run', is_flag=True, help='Show what would be indexed without doing it')
def calibre_sync(
    tag: str,
    library: str,
    host: str,
    port: int,
    collection: str,
    batch_size: int,
    force: bool,
    dry_run: bool,
):
    """
    Sync all books with a specific Calibre tag to ChromaDB.

    Example:
        book-indexer calibre-sync "Claude Index" --host opus.centaur-snapper.ts.net
        book-indexer calibre-sync "To Read" --dry-run
    """
    try:
        cal = CalibreLibrary(library)
        books = cal.get_books_by_tag(tag)

        if not books:
            console.print(f"[yellow]No books found with tag: {tag}[/yellow]")
            console.print("\n[dim]Tip: Use 'calibre-tags' to see available tags[/dim]")
            return

        console.print(f"\n[cyan]Found {len(books)} book(s) with tag '{tag}'[/cyan]\n")

        if dry_run:
            table = Table(title="Books to sync (dry run)")
            table.add_column("Title", style="cyan")
            table.add_column("Author", style="magenta")
            table.add_column("Format", style="green")

            for book in books:
                best_format = book.get_best_format(Path(library))
                table.add_row(
                    book.title[:50],
                    ', '.join(book.authors)[:30] or 'Unknown',
                    best_format.suffix if best_format else '[red]No supported format[/red]',
                )

            console.print(table)
            console.print("\n[dim]Run without --dry-run to sync these books[/dim]")
            return

        # Actually sync
        indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

        results = {'indexed': [], 'skipped': [], 'errors': []}

        with Progress() as progress:
            task = progress.add_task("[cyan]Syncing...", total=len(books))

            for book in books:
                try:
                    # Get best available format
                    file_path = book.get_best_format(Path(library))

                    if not file_path:
                        results['errors'].append({
                            'title': book.title,
                            'error': 'No supported format (epub/pdf)',
                        })
                        console.print(f"[red]✗[/red] {book.title[:40]} - no supported format")
                        progress.update(task, advance=1)
                        continue

                    result = indexer.index_document(file_path, force=force, batch_size=batch_size)

                    if result['status'] == 'indexed':
                        results['indexed'].append(result)
                        console.print(f"[green]✓[/green] {book.title[:40]} ({result['chunks']} chunks)")
                    elif result['status'] == 'skipped':
                        results['skipped'].append(result)
                        console.print(f"[yellow]⊘[/yellow] {book.title[:40]} (already indexed)")

                except Exception as e:
                    results['errors'].append({'title': book.title, 'error': str(e)})
                    console.print(f"[red]✗[/red] {book.title[:40]}: {e}")

                progress.update(task, advance=1)

        # Summary
        console.print("\n[bold]Sync Summary:[/bold]")
        console.print(f"  Indexed: [green]{len(results['indexed'])}[/green]")
        console.print(f"  Skipped: [yellow]{len(results['skipped'])}[/yellow]")
        console.print(f"  Errors:  [red]{len(results['errors'])}[/red]")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


# ============================================================================
# BookLore Integration Commands
# ============================================================================

def _booklore_library(host, port, user, password, mount_map):
    """Create BookLoreLibrary with lazy import (only needed when pymysql is installed)."""
    from .booklore import BookLoreLibrary
    kwargs = {
        "host": host, "port": port, "user": user,
        "password": password, "database": "booklore",
    }
    if mount_map:
        import json
        kwargs["mount_map"] = json.loads(mount_map)
    return BookLoreLibrary(**kwargs)


# Shared options for all booklore commands
def booklore_options(f):
    """Common BookLore connection options."""
    f = click.option('--db-host', default='127.0.0.1', help='MariaDB host')(f)
    f = click.option('--db-port', default=3307, type=int, help='MariaDB port')(f)
    f = click.option('--db-user', default='booklore', help='MariaDB user')(f)
    f = click.option('--db-password', default='', help='MariaDB password (or set BOOKLORE_DB_PASSWORD env var)')(f)
    f = click.option('--mount-map', default=None, help='JSON mount map e.g. \'{\"/books\": \"/home/user/calibre\"}\'')(f)
    return f


def _get_bl_password(db_password):
    """Get password from arg or environment."""
    return db_password or os.environ.get("BOOKLORE_DB_PASSWORD", "")


@main.command('booklore-stats')
@booklore_options
def booklore_stats(db_host, db_port, db_user, db_password, mount_map):
    """
    Show BookLore library statistics.

    Example:
        book-indexer booklore-stats
    """
    try:
        bl = _booklore_library(db_host, db_port, db_user, _get_bl_password(db_password), mount_map)
        stats = bl.get_library_stats()

        console.print("\n[bold cyan]BookLore Library Statistics[/bold cyan]\n")
        console.print(f"  Books:     [green]{stats['total_books']:,}[/green]")
        console.print(f"  Authors:   [green]{stats['total_authors']:,}[/green]")
        console.print(f"  Tags:      [green]{stats['total_tags']:,}[/green]")
        console.print(f"  Formats:   [green]{stats['total_formats']}[/green]")
        console.print(f"  Libraries: [green]{stats['total_libraries']}[/green]")
        console.print(f"\n  Host: [dim]{db_host}:{db_port}[/dim]\n")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('booklore-tags')
@booklore_options
@click.option('--min-books', default=1, type=int, help='Only show tags with at least N books')
def booklore_tags(db_host, db_port, db_user, db_password, mount_map, min_books):
    """
    List all BookLore tags with book counts.

    Example:
        book-indexer booklore-tags
        book-indexer booklore-tags --min-books 5
    """
    try:
        bl = _booklore_library(db_host, db_port, db_user, _get_bl_password(db_password), mount_map)
        tags = bl.get_all_tags()

        tags = [t for t in tags if t['book_count'] >= min_books]

        if not tags:
            console.print("[yellow]No tags found matching criteria[/yellow]")
            return

        table = Table(title=f"BookLore Tags ({len(tags)} total)")
        table.add_column("Tag", style="cyan")
        table.add_column("Books", justify="right", style="green")

        for tag in sorted(tags, key=lambda x: x['book_count'], reverse=True):
            name = tag['name'][:60] + '...' if len(tag['name']) > 60 else tag['name']
            table.add_row(name, str(tag['book_count']))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('booklore-search')
@click.argument('query')
@booklore_options
@click.option('--limit', default=20, type=int, help='Maximum results')
def booklore_search(query, db_host, db_port, db_user, db_password, mount_map, limit):
    """
    Search BookLore library by title or author.

    Example:
        book-indexer booklore-search "agentic AI"
    """
    try:
        bl = _booklore_library(db_host, db_port, db_user, _get_bl_password(db_password), mount_map)
        books = bl.search_books(query, limit=limit)

        if not books:
            console.print(f"[yellow]No books found matching: {query}[/yellow]")
            return

        table = Table(title=f"Search Results ({len(books)} found)")
        table.add_column("ID", style="dim")
        table.add_column("Title", style="cyan")
        table.add_column("Author", style="magenta")
        table.add_column("Formats", style="green")
        table.add_column("Tags", style="dim")

        for book in books:
            table.add_row(
                str(book.id),
                book.title[:50] + '...' if len(book.title) > 50 else book.title,
                ', '.join(book.authors)[:30] or 'Unknown',
                ', '.join(book.formats),
                ', '.join(book.tags[:3]) + ('...' if len(book.tags) > 3 else ''),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


@main.command('booklore-sync')
@click.argument('tag')
@booklore_options
@click.option('--host', default='localhost', help='ChromaDB host')
@click.option('--port', default=8000, type=int, help='ChromaDB port')
@click.option('--collection', default='books', help='Collection name')
@click.option('--batch-size', default=50, type=int, help='Chunks per batch')
@click.option('--force', is_flag=True, help='Force re-indexing')
@click.option('--dry-run', is_flag=True, help='Show what would be indexed without doing it')
def booklore_sync(
    tag, db_host, db_port, db_user, db_password, mount_map,
    host, port, collection, batch_size, force, dry_run,
):
    """
    Sync all books with a specific BookLore tag to ChromaDB.

    Example:
        book-indexer booklore-sync "Claude Index" --host opus.centaur-snapper.ts.net
        book-indexer booklore-sync "To Read" --dry-run
    """
    try:
        bl = _booklore_library(db_host, db_port, db_user, _get_bl_password(db_password), mount_map)
        books = bl.get_books_by_tag(tag)

        if not books:
            console.print(f"[yellow]No books found with tag: {tag}[/yellow]")
            console.print("\n[dim]Tip: Use 'booklore-tags' to see available tags[/dim]")
            return

        console.print(f"\n[cyan]Found {len(books)} book(s) with tag '{tag}'[/cyan]\n")

        if dry_run:
            table = Table(title="Books to sync (dry run)")
            table.add_column("Title", style="cyan")
            table.add_column("Author", style="magenta")
            table.add_column("Format", style="green")

            for book in books:
                best = book.get_best_format()
                table.add_row(
                    book.title[:50],
                    ', '.join(book.authors)[:30] or 'Unknown',
                    best.suffix if best else '[red]No supported format[/red]',
                )

            console.print(table)
            console.print("\n[dim]Run without --dry-run to sync these books[/dim]")
            return

        indexer = BookIndexer(chroma_host=host, chroma_port=port, collection_name=collection)

        results = {'indexed': [], 'skipped': [], 'errors': []}

        with Progress() as progress:
            task = progress.add_task("[cyan]Syncing...", total=len(books))

            for book in books:
                try:
                    file_path = book.get_best_format()

                    if not file_path:
                        results['errors'].append({
                            'title': book.title,
                            'error': 'No supported format (epub/pdf)',
                        })
                        console.print(f"[red]✗[/red] {book.title[:40]} - no supported format")
                        progress.update(task, advance=1)
                        continue

                    result = indexer.index_document(file_path, force=force, batch_size=batch_size)

                    if result['status'] == 'indexed':
                        results['indexed'].append(result)
                        console.print(f"[green]✓[/green] {book.title[:40]} ({result['chunks']} chunks)")
                    elif result['status'] == 'skipped':
                        results['skipped'].append(result)
                        console.print(f"[yellow]⊘[/yellow] {book.title[:40]} (already indexed)")

                except Exception as e:
                    results['errors'].append({'title': book.title, 'error': str(e)})
                    console.print(f"[red]✗[/red] {book.title[:40]}: {e}")

                progress.update(task, advance=1)

        console.print("\n[bold]Sync Summary:[/bold]")
        console.print(f"  Indexed: [green]{len(results['indexed'])}[/green]")
        console.print(f"  Skipped: [yellow]{len(results['skipped'])}[/yellow]")
        console.print(f"  Errors:  [red]{len(results['errors'])}[/red]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


if __name__ == '__main__':
    main()
