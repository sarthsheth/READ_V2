"""
Firestore Native Mode repository service for books and reading progress.
Implements bounded queries, atomic dot-notation updates, and dual-mode execution
(in-memory mock when offline, live Google Cloud Firestore when credentials are set).
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import get_settings
from models.book import BookDocument, BookFormat, LocatorType, ProgressData, ProgressUpdatePayload


class FirestoreServiceError(Exception):
    """Base exception for Firestore service failures."""
    pass


class MockFirestoreClient:
    """
    In-memory Firestore emulator for local offline testing.
    Mirrors collections, documents, atomic dot-notation updates, and server timestamps.
    """

    def __init__(self):
        self._collections: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def collection(self, col_name: str):
        return MockCollectionReference(self._collections.setdefault(col_name, {}))


class MockDocumentSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]]):
        self.id = doc_id
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class MockDocumentReference:
    def __init__(self, doc_id: str, store: Dict[str, Dict[str, Any]]):
        self.id = doc_id
        self._store = store

    def get(self) -> MockDocumentSnapshot:
        data = self._store.get(self.id)
        return MockDocumentSnapshot(self.id, data)

    def set(self, data: Dict[str, Any], merge: bool = False):
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)

    def update(self, field_updates: Dict[str, Any]):
        if self.id not in self._store:
            raise FirestoreServiceError(f"Document '{self.id}' not found for update.")
        
        doc = self._store[self.id]
        for key, value in field_updates.items():
            # Handle dot notation updates e.g. "progress.locator_value"
            parts = key.split(".")
            curr = doc
            for part in parts[:-1]:
                if part not in curr or not isinstance(curr[part], dict):
                    curr[part] = {}
                curr = curr[part]
            
            # Replace SERVER_TIMESTAMP with UTC now
            if getattr(value, "__name__", "") == "SERVER_TIMESTAMP" or str(value) == "SERVER_TIMESTAMP":
                curr[parts[-1]] = datetime.now(timezone.utc).isoformat()
            else:
                curr[parts[-1]] = value.isoformat() if isinstance(value, datetime) else value

    def delete(self):
        self._store.pop(self.id, None)


class MockCollectionReference:
    def __init__(self, store: Dict[str, Dict[str, Any]], limit_count: Optional[int] = None):
        self._store = store
        self._limit_count = limit_count

    def document(self, doc_id: str) -> MockDocumentReference:
        return MockDocumentReference(doc_id, self._store)

    def limit(self, count: int):
        return MockCollectionReference(self._store, limit_count=count)

    def stream(self):
        items = list(self._store.items())
        if self._limit_count is not None:
            items = items[:self._limit_count]
        for doc_id, data in items:
            yield MockDocumentSnapshot(doc_id, data)


class FirestoreService:
    """
    Data access layer for collection: 'books'.
    Enforces single-document operations to preserve GCP Always-Free tier allowances.
    """

    COLLECTION_NAME = "books"

    def __init__(self, client=None):
        self.settings = get_settings()
        
        if client is not None:
            self.client = client
        elif self.settings.mock_gcp:
            self.client = MockFirestoreClient()
        else:
            try:
                from google.cloud import firestore
                self.client = firestore.Client(project=self.settings.gcp_project_id)
            except Exception as e:
                # If credentials are not set locally, fallback gracefully with a warning
                print(f"[WARN] Live Firestore client initialization failed: {e}. Falling back to MockFirestoreClient.")
                self.client = MockFirestoreClient()

    def _col_ref(self):
        return self.client.collection(self.COLLECTION_NAME)

    def create_or_get_book(self, book_doc: BookDocument) -> Tuple[BookDocument, bool]:
        """
        Idempotently inserts a book document. If already exists (matching SHA-256),
        returns existing document without overwriting reading progress.
        Returns: (BookDocument, created_flag)
        """
        doc_ref = self._col_ref().document(book_doc.book_id)
        snapshot = doc_ref.get()

        if snapshot.exists:
            existing_data = snapshot.to_dict()
            return BookDocument.model_validate(existing_data), False

        # Convert Pydantic model to dictionary with ISO strings for datetime
        payload = book_doc.model_dump(mode="json")
        doc_ref.set(payload)
        return book_doc, True

    def get_book(self, book_id: str) -> Optional[BookDocument]:
        """Fetches a single book document by SHA-256 hash."""
        doc_ref = self._col_ref().document(book_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        return BookDocument.model_validate(snapshot.to_dict())

    def list_books(self, limit: int = 50) -> List[BookDocument]:
        """
        Lists books in library with reading progress.
        Enforces a hard limit to prevent full-collection scans and conserve Firestore free reads.
        """
        books = []
        for snapshot in self._col_ref().limit(limit).stream():
            data = snapshot.to_dict()
            if data:
                books.append(BookDocument.model_validate(data))
        return books

    def update_progress(self, book_id: str, progress: ProgressUpdatePayload) -> bool:
        """
        Atomically updates reading progress using dot notation.
        Cost: Exactly 1 Firestore write operation.
        """
        doc_ref = self._col_ref().document(book_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False

        # Live firestore vs Mock timestamp
        timestamp_value = (
            datetime.now(timezone.utc).isoformat()
            if isinstance(self.client, MockFirestoreClient)
            else "SERVER_TIMESTAMP"
        )
        try:
            from google.cloud import firestore
            if not isinstance(self.client, MockFirestoreClient):
                timestamp_value = firestore.SERVER_TIMESTAMP
        except ImportError:
            pass

        field_updates = {
            "progress.locator_type": progress.locator_type.value,
            "progress.locator_value": progress.locator_value,
            "progress.percentage": progress.percentage,
            "progress.last_read_at": timestamp_value,
            "updated_at": timestamp_value,
        }
        if progress.device_info:
            field_updates["progress.device_info"] = progress.device_info

        doc_ref.update(field_updates)
        return True

    def delete_book(self, book_id: str) -> bool:
        """Deletes a book record from Firestore."""
        doc_ref = self._col_ref().document(book_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        doc_ref.delete()
        return True


if __name__ == "__main__":
    print("--- Running services/firestore_service.py Self-Test ---")
    
    # Initialize service (runs in Mock mode unless configured otherwise)
    service = FirestoreService()
    print(f"Firestore Client: {type(service.client).__name__}")
    
    # Use real hash from our generated sample.epub book
    sample_hash = "1d52562507ad3abaed88bf407f4389f00b7d1022b02942e8a7502f607773097c"
    
    initial_doc = BookDocument(
        book_id=sample_hash,
        filename="sample.epub",
        format=BookFormat.EPUB,
        file_size_bytes=5219,
        storage_path=f"books/{sample_hash}.epub",
        cover_image_path=f"covers/{sample_hash}.jpg",
        title="The Cloud Architecture Handbook",
        author="Sarth Sheth",
        language="en",
        progress=ProgressData(
            locator_type=LocatorType.EPUB_CFI,
            locator_value="epubcfi(/6/2[ch1]!/4/2/10:0)",
            percentage=0.10,
            last_read_at=datetime.now(timezone.utc),
            device_info="Self-Test Desktop Client"
        )
    )
    
    # 1. Test create_or_get_book
    created_doc, was_created = service.create_or_get_book(initial_doc)
    assert was_created is True, "Document should be marked as newly created"
    assert created_doc.book_id == sample_hash
    print(f"[OK] Created book: '{created_doc.title}' (ID: {sample_hash[:12]}...)")
    
    # 2. Test idempotent duplicate insertion
    duplicate_doc, was_created = service.create_or_get_book(initial_doc)
    assert was_created is False, "Duplicate hash must NOT overwrite existing document"
    print("[OK] Idempotent creation verified (duplicate avoided)")
    
    # 3. Test get_book
    retrieved = service.get_book(sample_hash)
    assert retrieved is not None
    assert retrieved.title == "The Cloud Architecture Handbook"
    assert retrieved.progress.percentage == 0.10
    print("[OK] Retrieved book document verified")
    
    # 4. Test atomic progress update
    update_payload = ProgressUpdatePayload(
        locator_type=LocatorType.EPUB_CFI,
        locator_value="epubcfi(/6/4[ch2]!/4/2/25:0)",
        percentage=0.45,
        device_info="Updated Mobile Client"
    )
    success = service.update_progress(sample_hash, update_payload)
    assert success is True, "Progress update should succeed"
    
    # Verify updated values
    updated_book = service.get_book(sample_hash)
    assert updated_book is not None
    assert updated_book.progress.percentage == 0.45
    assert updated_book.progress.locator_value == "epubcfi(/6/4[ch2]!/4/2/25:0)"
    assert updated_book.progress.device_info == "Updated Mobile Client"
    print(f"[OK] Atomic progress update verified (New Progress: {updated_book.progress.percentage * 100}%)")
    
    # 5. Test list_books
    library = service.list_books(limit=10)
    assert len(library) >= 1
    assert any(b.book_id == sample_hash for b in library)
    print(f"[OK] Library listing verified ({len(library)} books returned)")
    
    print("\n[ALL FIRESTORE SERVICE TESTS PASSED]")
