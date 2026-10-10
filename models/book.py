"""
Domain models and Pydantic schemas for books, metadata, and reading progress.
Designed to align directly with Firestore Native Mode schema specifications.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class BookFormat(str, Enum):
    """Supported book format extensions."""
    EPUB = "epub"
    PDF = "pdf"


class LocatorType(str, Enum):
    """Reading position locator mechanism."""
    EPUB_CFI = "epub_cfi"
    PDF_PAGE = "pdf_page"


class ProgressData(BaseModel):
    """Embedded reading progress object inside a book document."""
    locator_type: LocatorType = Field(description="Locator type: epub_cfi or pdf_page")
    locator_value: str = Field(description="Canonical Fragment Identifier or stringified page number")
    percentage: float = Field(default=0.0, ge=0.0, le=1.0, description="Reading progress from 0.0 to 1.0")
    last_read_at: Optional[datetime] = Field(default=None, description="Timestamp of the last read interaction")
    device_info: Optional[str] = Field(default=None, description="Client user agent or device identifier")

    model_config = ConfigDict(extra="ignore")


class ProgressUpdatePayload(BaseModel):
    """Payload sent by client during debounced progress synchronization."""
    locator_type: LocatorType
    locator_value: str
    percentage: float = Field(ge=0.0, le=1.0)
    device_info: Optional[str] = None


class ParsedBookMetadata(BaseModel):
    """In-memory metadata extracted from an EPUB or PDF binary before storage."""
    title: str = Field(default="Untitled")
    author: Optional[str] = Field(default="Unknown Author")
    language: Optional[str] = Field(default="en")
    format: BookFormat
    file_size_bytes: int = Field(ge=0)
    sha256_hash: str = Field(description="SHA-256 content hash of the original binary")
    total_pages: Optional[int] = Field(default=None, description="Total pages for PDF files")
    cover_image_bytes: Optional[bytes] = Field(default=None, description="Raw bytes of extracted cover art thumbnail")
    cover_image_mime: Optional[str] = Field(default=None, description="MIME type of cover image (e.g. image/jpeg)")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BookDocument(BaseModel):
    """Firestore document schema for collection: books/{book_id}."""
    book_id: str = Field(description="SHA-256 content hash of the book binary")
    filename: str = Field(description="Original filename uploaded by the user")
    format: BookFormat = Field(description="Format (epub or pdf)")
    file_size_bytes: int = Field(ge=0)
    storage_path: str = Field(description="GCS object path: books/{sha256}.{ext}")
    cover_image_path: Optional[str] = Field(default=None, description="GCS path for cover thumbnail: covers/{sha256}.jpg")
    title: str = Field(default="Untitled")
    author: Optional[str] = Field(default="Unknown Author")
    language: Optional[str] = Field(default="en")
    total_pages: Optional[int] = Field(default=None)
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    progress: ProgressData = Field(description="Embedded reading progress")

    model_config = ConfigDict(extra="ignore")


if __name__ == "__main__":
    print("--- Running models/book.py Self-Test ---")
    
    # 1. Test ProgressData
    progress = ProgressData(
        locator_type=LocatorType.EPUB_CFI,
        locator_value="epubcfi(/6/14[chap04]!/4/2/10/1:0)",
        percentage=0.342,
        last_read_at=datetime.now(timezone.utc),
        device_info="Test Browser"
    )
    assert progress.percentage == 0.342
    print("[OK] ProgressData model validated")

    # 2. Test BookDocument
    dummy_hash = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    book_doc = BookDocument(
        book_id=dummy_hash,
        filename="Designing_Data_Intensive_Applications.epub",
        format=BookFormat.EPUB,
        file_size_bytes=14582910,
        storage_path=f"books/{dummy_hash}.epub",
        cover_image_path=f"covers/{dummy_hash}.jpg",
        title="Designing Data-Intensive Applications",
        author="Martin Kleppmann",
        progress=progress
    )
    assert book_doc.book_id == dummy_hash
    assert book_doc.progress.locator_type == LocatorType.EPUB_CFI
    
    # Verify JSON serialization & deserialization
    json_data = book_doc.model_dump_json()
    reconstructed = BookDocument.model_validate_json(json_data)
    assert reconstructed.title == "Designing Data-Intensive Applications"
    print("[OK] BookDocument serialization and deserialization validated")
    
    # 3. Test ProgressUpdatePayload validation
    valid_payload = ProgressUpdatePayload(
        locator_type=LocatorType.PDF_PAGE,
        locator_value="42",
        percentage=0.25
    )
    assert valid_payload.percentage == 0.25
    print("[OK] ProgressUpdatePayload validated")
    
    print("\n[ALL MODELS TESTS PASSED]")

