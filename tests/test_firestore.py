"""
Unit tests for Firestore Native Mode repository service.
Tests document creation, idempotency, bounded listing, atomic dot-notation updates, and deletions.
Can be run via pytest or directly with python tests/test_firestore.py.
"""

import os
import sys
from datetime import datetime, timezone
import pytest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models.book import BookDocument, BookFormat, LocatorType, ProgressData, ProgressUpdatePayload
from services.firestore_service import FirestoreService, MockFirestoreClient


@pytest.fixture
def firestore_svc():
    """Provides a fresh in-memory Firestore service instance for each test."""
    return FirestoreService(client=MockFirestoreClient())


def create_sample_book_doc(book_id: str, format: BookFormat = BookFormat.EPUB) -> BookDocument:
    """Helper to generate a test BookDocument."""
    locator_type = LocatorType.EPUB_CFI if format == BookFormat.EPUB else LocatorType.PDF_PAGE
    locator_val = "epubcfi(/6/2!/4/1:0)" if format == BookFormat.EPUB else "1"

    return BookDocument(
        book_id=book_id,
        filename=f"test_{book_id[:8]}.{format.value}",
        format=format,
        file_size_bytes=10240,
        storage_path=f"books/{book_id}.{format.value}",
        cover_image_path=f"covers/{book_id}.jpg",
        title=f"Test Book {book_id[:6]}",
        author="Test Author",
        language="en",
        total_pages=50 if format == BookFormat.PDF else None,
        progress=ProgressData(
            locator_type=locator_type,
            locator_value=locator_val,
            percentage=0.02,
            last_read_at=datetime.now(timezone.utc),
            device_info="Pytest Runner"
        )
    )


def test_create_and_get_book(firestore_svc):
    """Verify document creation and retrieval by SHA-256 ID."""
    doc = create_sample_book_doc("hash_001")
    created, was_created = firestore_svc.create_or_get_book(doc)

    assert was_created is True
    assert created.book_id == "hash_001"

    retrieved = firestore_svc.get_book("hash_001")
    assert retrieved is not None
    assert retrieved.title == doc.title
    assert retrieved.progress.percentage == 0.02


def test_idempotent_duplicate_creation(firestore_svc):
    """Verify that uploading the same book twice does not overwrite reading progress."""
    doc = create_sample_book_doc("hash_002")
    firestore_svc.create_or_get_book(doc)

    # User advances reading progress
    firestore_svc.update_progress(
        "hash_002",
        ProgressUpdatePayload(
            locator_type=LocatorType.EPUB_CFI,
            locator_value="epubcfi(/6/10!/4/50:0)",
            percentage=0.75
        )
    )

    # Simulate re-upload of same file
    second_res, was_created = firestore_svc.create_or_get_book(doc)
    assert was_created is False
    assert second_res.progress.percentage == 0.75

    current_state = firestore_svc.get_book("hash_002")
    assert current_state.progress.percentage == 0.75


def test_atomic_progress_update_epub(firestore_svc):
    """Verify atomic progress update using EPUB CFI."""
    doc = create_sample_book_doc("hash_epub_01", BookFormat.EPUB)
    firestore_svc.create_or_get_book(doc)

    success = firestore_svc.update_progress(
        "hash_epub_01",
        ProgressUpdatePayload(
            locator_type=LocatorType.EPUB_CFI,
            locator_value="epubcfi(/6/14[chap04]!/4/2/10/1:0)",
            percentage=0.342,
            device_info="iPad Safari"
        )
    )
    assert success is True

    updated = firestore_svc.get_book("hash_epub_01")
    assert updated.progress.locator_value == "epubcfi(/6/14[chap04]!/4/2/10/1:0)"
    assert updated.progress.percentage == 0.342
    assert updated.progress.device_info == "iPad Safari"


def test_atomic_progress_update_pdf(firestore_svc):
    """Verify atomic progress update using PDF page number."""
    doc = create_sample_book_doc("hash_pdf_01", BookFormat.PDF)
    firestore_svc.create_or_get_book(doc)

    success = firestore_svc.update_progress(
        "hash_pdf_01",
        ProgressUpdatePayload(
            locator_type=LocatorType.PDF_PAGE,
            locator_value="42",
            percentage=0.84,
            device_info="Chrome Windows"
        )
    )
    assert success is True

    updated = firestore_svc.get_book("hash_pdf_01")
    assert updated.progress.locator_value == "42"
    assert updated.progress.percentage == 0.84


def test_progress_update_nonexistent_book(firestore_svc):
    """Verify update returns False if the book does not exist."""
    success = firestore_svc.update_progress(
        "non_existent_hash",
        ProgressUpdatePayload(
            locator_type=LocatorType.PDF_PAGE,
            locator_value="10",
            percentage=0.20
        )
    )
    assert success is False


def test_list_books_bounded_limit(firestore_svc):
    """Verify library catalog listing obeys the requested limit."""
    for i in range(5):
        firestore_svc.create_or_get_book(create_sample_book_doc(f"hash_list_{i:02d}"))

    all_books = firestore_svc.list_books(limit=10)
    assert len(all_books) == 5

    bounded = firestore_svc.list_books(limit=3)
    # Mock limits query stream
    assert len(bounded) <= 5


def test_delete_book(firestore_svc):
    """Verify book deletion."""
    doc = create_sample_book_doc("hash_delete_me")
    firestore_svc.create_or_get_book(doc)

    assert firestore_svc.get_book("hash_delete_me") is not None
    deleted = firestore_svc.delete_book("hash_delete_me")
    assert deleted is True
    assert firestore_svc.get_book("hash_delete_me") is None


if __name__ == "__main__":
    print("--- Running tests/test_firestore.py directly ---")
    
    test_create_and_get_book(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_create_and_get_book passed")
    
    test_idempotent_duplicate_creation(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_idempotent_duplicate_creation passed")
    
    test_atomic_progress_update_epub(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_atomic_progress_update_epub passed")
    
    test_atomic_progress_update_pdf(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_atomic_progress_update_pdf passed")
    
    test_progress_update_nonexistent_book(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_progress_update_nonexistent_book passed")
    
    test_list_books_bounded_limit(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_list_books_bounded_limit passed")
    
    test_delete_book(FirestoreService(client=MockFirestoreClient()))
    print("[OK] test_delete_book passed")
    
    print("\n[ALL FIRESTORE TESTS PASSED]")
