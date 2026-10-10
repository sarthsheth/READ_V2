"""
EPUB metadata extraction service.
Extracts Dublin Core metadata, cover art, and computes SHA-256 hash using
standard library zipfile and xml.etree (no heavy third-party dependencies).
"""

import hashlib
import io
import os
import posixpath
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import BinaryIO, Optional, Tuple, Union

# Ensure project root is in sys.path when executed directly as a script
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.book import BookFormat, ParsedBookMetadata

# Standard XML namespaces found in EPUB packages
NAMESPACES = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class EpubParserError(Exception):
    """Raised when an EPUB file is invalid or cannot be parsed."""
    pass


def _calculate_sha256_and_bytes(source: Union[str, Path, bytes, BinaryIO]) -> Tuple[bytes, str, int]:
    """
    Reads source payload into bytes and calculates SHA-256 hash.
    Returns: (raw_bytes, sha256_hex, size_in_bytes)
    """
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


def _find_opf_path(archive: zipfile.ZipFile) -> str:
    """Finds the relative path to the OPF package document via META-INF/container.xml."""
    try:
        container_xml = archive.read("META-INF/container.xml")
    except KeyError:
        raise EpubParserError("Invalid EPUB: Missing 'META-INF/container.xml'.")

    try:
        root = ET.fromstring(container_xml)
        # Search with and without namespace
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            rootfile = root.find(".//rootfile")
        if rootfile is None or "full-path" not in rootfile.attrib:
            raise EpubParserError("Invalid EPUB: 'container.xml' does not define a rootfile full-path.")
        return rootfile.attrib["full-path"]
    except ET.ParseError as e:
        raise EpubParserError(f"XML parse error in 'container.xml': {str(e)}")


def _find_elem(parent: ET.Element, tag_with_ns: str, tag_bare: str) -> Optional[ET.Element]:
    """Finds an element by tag with namespace, falling back to bare tag without testing truthiness."""
    el = parent.find(tag_with_ns)
    if el is not None:
        return el
    return parent.find(tag_bare)


def _extract_cover_image(
    archive: zipfile.ZipFile,
    opf_tree: ET.Element,
    opf_dir: str
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Attempts to locate and extract the cover image thumbnail from the manifest.
    Supports EPUB 3 (properties='cover-image') and EPUB 2 (<meta name='cover'>).
    """
    manifest = _find_elem(opf_tree, "{http://www.idpf.org/2007/opf}manifest", "manifest")
    if manifest is None:
        return None, None

    items = manifest.findall("{http://www.idpf.org/2007/opf}item")
    if not items:
        items = manifest.findall("item")

    item_by_id = {item.attrib.get("id"): item for item in items if "id" in item.attrib}

    cover_href = None
    cover_mime = None

    # Strategy 1: EPUB 3 properties="cover-image"
    for item in items:
        props = item.attrib.get("properties", "").split()
        if "cover-image" in props:
            cover_href = item.attrib.get("href")
            cover_mime = item.attrib.get("media-type")
            break

    # Strategy 2: EPUB 2 <meta name="cover" content="item_id"/>
    if not cover_href:
        metadata = _find_elem(opf_tree, "{http://www.idpf.org/2007/opf}metadata", "metadata")
        if metadata is not None:
            metas = metadata.findall("{http://www.idpf.org/2007/opf}meta")
            if not metas:
                metas = metadata.findall("meta")
            for meta in metas:
                if meta.attrib.get("name") == "cover":
                    cover_id = meta.attrib.get("content")
                    if cover_id in item_by_id:
                        item = item_by_id[cover_id]
                        cover_href = item.attrib.get("href")
                        cover_mime = item.attrib.get("media-type")
                        break

    # Strategy 3: Fallback by searching id or href with 'cover' and image media-type
    if not cover_href:
        for item in items:
            media_type = item.attrib.get("media-type", "")
            item_id = item.attrib.get("id", "").lower()
            href = item.attrib.get("href", "").lower()
            if media_type.startswith("image/") and ("cover" in item_id or "cover" in href):
                cover_href = item.attrib.get("href")
                cover_mime = media_type
                break

    if not cover_href:
        return None, None

    # Resolve href relative to OPF directory inside zip
    normalized_path = posixpath.normpath(posixpath.join(opf_dir, cover_href)) if opf_dir else cover_href

    try:
        cover_bytes = archive.read(normalized_path)
        return cover_bytes, cover_mime or "image/jpeg"
    except KeyError:
        return None, None


def parse_epub(
    source: Union[str, Path, bytes, BinaryIO],
    fallback_title: str = "Untitled"
) -> ParsedBookMetadata:
    """
    Parses an EPUB package and returns extracted metadata.
    """
    raw_bytes, sha256_hash, file_size = _calculate_sha256_and_bytes(source)

    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as archive:
            opf_path = _find_opf_path(archive)
            opf_dir = posixpath.dirname(opf_path)
            
            try:
                opf_content = archive.read(opf_path)
            except KeyError:
                raise EpubParserError(f"Invalid EPUB: OPF rootfile not found at '{opf_path}'.")

            try:
                opf_root = ET.fromstring(opf_content)
            except ET.ParseError as e:
                raise EpubParserError(f"Invalid XML in OPF package: {str(e)}")

            # Extract Metadata
            metadata_el = _find_elem(opf_root, "{http://www.idpf.org/2007/opf}metadata", "metadata")

            title = fallback_title
            author = "Unknown Author"
            language = "en"

            if metadata_el is not None:
                # Extract title
                title_el = _find_elem(metadata_el, "{http://purl.org/dc/elements/1.1/}title", "title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()

                # Extract author
                creator_el = _find_elem(metadata_el, "{http://purl.org/dc/elements/1.1/}creator", "creator")
                if creator_el is not None and creator_el.text:
                    author = creator_el.text.strip()

                # Extract language
                lang_el = _find_elem(metadata_el, "{http://purl.org/dc/elements/1.1/}language", "language")
                if lang_el is not None and lang_el.text:
                    language = lang_el.text.strip()

            # Extract Cover Art
            cover_bytes, cover_mime = _extract_cover_image(archive, opf_root, opf_dir)

            return ParsedBookMetadata(
                title=title,
                author=author,
                language=language,
                format=BookFormat.EPUB,
                file_size_bytes=file_size,
                sha256_hash=sha256_hash,
                total_pages=None,
                cover_image_bytes=cover_bytes,
                cover_image_mime=cover_mime,
            )

    except zipfile.BadZipFile:
        raise EpubParserError("Invalid file: Not a valid ZIP / EPUB archive.")


if __name__ == "__main__":
    print("--- Running services/epub_parser.py on Sample Book ---")
    
    sample_disk_path = Path(__file__).resolve().parent.parent / "sample_books" / "sample.epub"
    if not sample_disk_path.exists():
        from scripts.generate_sample_books import generate_sample_epub
        print(f"Sample book not found, generating at: {sample_disk_path}")
        generate_sample_epub(sample_disk_path)

    print(f"Parsing physical book file: {sample_disk_path}")
    parsed = parse_epub(sample_disk_path)

    print(f"Title            : {parsed.title}")
    print(f"Author           : {parsed.author}")
    print(f"Language         : {parsed.language}")
    print(f"Format           : {parsed.format.value}")
    print(f"File Size        : {parsed.file_size_bytes} bytes")
    print(f"SHA-256 Hash     : {parsed.sha256_hash}")
    print(f"Cover Image Size : {len(parsed.cover_image_bytes) if parsed.cover_image_bytes else 0} bytes")
    print(f"Cover MIME       : {parsed.cover_image_mime}")

    assert parsed.title == "The Cloud Architecture Handbook"
    assert parsed.author == "Sarth Sheth"
    assert parsed.language == "en"
    assert parsed.format == BookFormat.EPUB
    assert parsed.cover_image_bytes is not None
    assert parsed.cover_image_mime == "image/jpeg"
    assert len(parsed.sha256_hash) == 64
    
    print("\n[OK] EPUB Parser self-test passed on physical sample.epub!")