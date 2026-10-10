"""
Unit and integration tests for EPUB and PDF metadata extraction services.
Directly tests against the physical sample books in sample_books/ on disk
as well as synthetic and corrupted test cases.
Can be executed via pytest or directly with python tests/test_parsers.py.
"""

import hashlib
import io
import os
import sys
import zipfile
from pathlib import Path
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.book import BookFormat
from services.epub_parser import parse_epub, EpubParserError
from services.pdf_parser import parse_pdf, PdfParserError
from scripts.generate_sample_books import generate_sample_epub, generate_sample_pdf

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_books"
SAMPLE_EPUB_PATH = SAMPLE_DIR / "sample.epub"
SAMPLE_PDF_PATH = SAMPLE_DIR / "sample.pdf"


@pytest.fixture(scope="session", autouse=True)
def ensure_sample_books_exist():
    """Guarantees that physical sample books exist on disk before running tests."""
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    if not SAMPLE_EPUB_PATH.exists():
        generate_sample_epub(SAMPLE_EPUB_PATH)
    if not SAMPLE_PDF_PATH.exists():
        generate_sample_pdf(SAMPLE_PDF_PATH)


def test_real_sample_epub_from_disk():
    """Verify parsing against the physical sample.epub book on disk."""
    if not SAMPLE_EPUB_PATH.exists():
        generate_sample_epub(SAMPLE_EPUB_PATH)

    parsed = parse_epub(SAMPLE_EPUB_PATH)

    assert parsed.title == "The Cloud Architecture Handbook"
    assert parsed.author == "Sarth Sheth"
    assert parsed.language == "en"
    assert parsed.format == BookFormat.EPUB
    assert parsed.file_size_bytes == SAMPLE_EPUB_PATH.stat().st_size
    assert parsed.cover_image_bytes is not None
    assert parsed.cover_image_mime == "image/jpeg"
    assert len(parsed.sha256_hash) == 64

    # Verify SHA-256 matches actual file bytes
    with open(SAMPLE_EPUB_PATH, "rb") as f:
        expected_hash = hashlib.sha256(f.read()).hexdigest()
    assert parsed.sha256_hash == expected_hash


def test_real_sample_pdf_from_disk():
    """Verify parsing against the physical sample.pdf book on disk."""
    if not SAMPLE_PDF_PATH.exists():
        generate_sample_pdf(SAMPLE_PDF_PATH)

    parsed = parse_pdf(SAMPLE_PDF_PATH)

    assert parsed.title == "The Cloud Architecture Handbook"
    assert parsed.author == "Sarth Sheth"
    assert parsed.format == BookFormat.PDF
    assert parsed.total_pages == 3
    assert parsed.file_size_bytes == SAMPLE_PDF_PATH.stat().st_size
    assert len(parsed.sha256_hash) == 64

    # Verify SHA-256 matches actual file bytes
    with open(SAMPLE_PDF_PATH, "rb") as f:
        expected_hash = hashlib.sha256(f.read()).hexdigest()
    assert parsed.sha256_hash == expected_hash


def test_epub_parser_fallback_defaults():
    """Verify default fallback handling when an EPUB lacks metadata tags."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            """<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>""",
        )
        z.writestr("content.opf", """<package xmlns="http://www.idpf.org/2007/opf"><metadata/><manifest/><spine/></package>""")

    parsed = parse_epub(buf.getvalue(), fallback_title="Fallback Book Title")
    assert parsed.title == "Fallback Book Title"
    assert parsed.author == "Unknown Author"
    assert parsed.language == "en"
    assert parsed.cover_image_bytes is None


def test_epub_parser_corrupted_payload():
    """Verify that malformed bytes raise EpubParserError."""
    with pytest.raises(EpubParserError):
        parse_epub(b"not a valid zip or epub binary")


def test_pdf_parser_fallback_defaults():
    """Verify PDF parser fallback when metadata dictionary is empty."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)

    parsed = parse_pdf(buf.getvalue(), fallback_title="My Default Document")
    assert parsed.title == "My Default Document"
    assert parsed.author == "Unknown Author"
    assert parsed.total_pages == 1


def test_pdf_parser_corrupted_payload():
    """Verify that corrupt PDF data raises PdfParserError."""
    with pytest.raises(PdfParserError):
        parse_pdf(b"corrupted pdf bytes")


def test_sha256_reproducibility():
    """Verify that SHA-256 hash calculation is deterministic and identical to hashlib."""
    sample_data = b"Testing SHA-256 reproducibility across runs"
    expected = hashlib.sha256(sample_data).hexdigest()

    from services.epub_parser import _calculate_sha256_and_bytes as epub_hasher
    from services.pdf_parser import _calculate_sha256_and_bytes as pdf_hasher

    _, hash1, size1 = epub_hasher(sample_data)
    _, hash2, size2 = pdf_hasher(sample_data)

    assert hash1 == expected
    assert hash2 == expected
    assert size1 == len(sample_data)
    assert size2 == len(sample_data)


if __name__ == "__main__":
    print("--- Running tests/test_parsers.py directly on Sample Books ---")
    
    # Ensure samples exist
    if not SAMPLE_EPUB_PATH.exists():
        generate_sample_epub(SAMPLE_EPUB_PATH)
    if not SAMPLE_PDF_PATH.exists():
        generate_sample_pdf(SAMPLE_PDF_PATH)

    test_real_sample_epub_from_disk()
    print("[OK] test_real_sample_epub_from_disk passed")

    test_real_sample_pdf_from_disk()
    print("[OK] test_real_sample_pdf_from_disk passed")

    test_epub_parser_fallback_defaults()
    print("[OK] test_epub_parser_fallback_defaults passed")

    test_epub_parser_corrupted_payload()
    print("[OK] test_epub_parser_corrupted_payload passed")

    test_pdf_parser_fallback_defaults()
    print("[OK] test_pdf_parser_fallback_defaults passed")

    test_pdf_parser_corrupted_payload()
    print("[OK] test_pdf_parser_corrupted_payload passed")

    test_sha256_reproducibility()
    print("[OK] test_sha256_reproducibility passed")

    print("\n[ALL PARSER TESTS PASSED]")
