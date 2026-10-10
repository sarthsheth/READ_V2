"""
PDF metadata extraction service.
Extracts title, author, total page count, first-page cover art, and computes
SHA-256 hash using lightweight pypdf.
"""

import hashlib
import io
import sys
from pathlib import Path
from typing import BinaryIO, Optional, Tuple, Union

# Ensure project root is in sys.path when executed directly as a script
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from models.book import BookFormat, ParsedBookMetadata


class PdfParserError(Exception):
    """Raised when a PDF file is corrupt or cannot be parsed."""
    pass


def _calculate_sha256_and_bytes(source: Union[str, Path, bytes, BinaryIO]) -> Tuple[bytes, str, int]:
    """Reads source payload into bytes and calculates SHA-256 hash."""
    if isinstance(source, (str, Path)):
        with open(source, "rb") as f:
            data = f.read()
    elif isinstance(source, bytes):
        data = source
    elif hasattr(source, "read"):
        data = source.read()
    else:
        raise ValueError(f"Unsupported source type: {type(source)}")

    sha256_hash = hashlib.sha256(data).hexdigest()
    return data, sha256_hash, len(data)


def _extract_page1_image(reader: PdfReader) -> Tuple[Optional[bytes], Optional[str]]:
    """Attempts to extract the primary cover image from page 1 if embedded."""
    if not reader.pages:
        return None, None

    try:
        page = reader.pages[0]
        if hasattr(page, "images") and page.images:
            for img in page.images:
                ext = Path(img.name).suffix.lower()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                return img.data, mime
    except Exception:
        # Graceful fallback: some PDFs have non-standard inline image streams
        return None, None

    return None, None


def parse_pdf(
    source: Union[str, Path, bytes, BinaryIO],
    fallback_title: str = "Untitled"
) -> ParsedBookMetadata:
    """
    Parses a PDF document and extracts metadata, page count, and page 1 thumbnail.
    """
    raw_bytes, sha256_hash, file_size = _calculate_sha256_and_bytes(source)

    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        total_pages = len(reader.pages)

        # Extract metadata
        meta = reader.metadata
        title = fallback_title
        author = "Unknown Author"

        if meta:
            if meta.title and meta.title.strip():
                title = meta.title.strip()
            if meta.author and meta.author.strip():
                author = meta.author.strip()

        # Extract Cover Image from Page 1
        cover_bytes, cover_mime = _extract_page1_image(reader)

        return ParsedBookMetadata(
            title=title,
            author=author,
            language="en",
            format=BookFormat.PDF,
            file_size_bytes=file_size,
            sha256_hash=sha256_hash,
            total_pages=total_pages,
            cover_image_bytes=cover_bytes,
            cover_image_mime=cover_mime,
        )

    except PdfReadError as e:
        raise PdfParserError(f"Invalid or corrupted PDF file: {str(e)}")
    except Exception as e:
        raise PdfParserError(f"Failed to parse PDF document: {str(e)}")


if __name__ == "__main__":
    print("--- Running services/pdf_parser.py on Sample Book ---")
    
    sample_disk_path = Path(__file__).resolve().parent.parent / "sample_books" / "sample.pdf"
    if not sample_disk_path.exists():
        from scripts.generate_sample_books import generate_sample_pdf
        print(f"Sample book not found, generating at: {sample_disk_path}")
        generate_sample_pdf(sample_disk_path)

    print(f"Parsing physical book file: {sample_disk_path}")
    parsed = parse_pdf(sample_disk_path)

    print(f"Title        : {parsed.title}")
    print(f"Author       : {parsed.author}")
    print(f"Format       : {parsed.format.value}")
    print(f"Total Pages  : {parsed.total_pages}")
    print(f"File Size    : {parsed.file_size_bytes} bytes")
    print(f"SHA-256 Hash : {parsed.sha256_hash}")

    assert parsed.title == "The Cloud Architecture Handbook"
    assert parsed.author == "Sarth Sheth"
    assert parsed.format == BookFormat.PDF
    assert parsed.total_pages == 3
    assert len(parsed.sha256_hash) == 64

    print("\n[OK] PDF Parser self-test passed on physical sample.pdf!")

