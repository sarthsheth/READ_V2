"""
Generator utility for creating physical, valid sample EPUB and PDF books on disk.
These files can be opened in external readers (Apple Books, Calibre, Chrome, Edge, Adobe Reader)
and are used to test metadata extraction and reading engines.
"""

import os
import sys
import zipfile
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.epub_parser import parse_epub
from services.pdf_parser import parse_pdf

# 1x1 Red Pixel Valid JFIF JPEG Binary
SAMPLE_COVER_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x01, 0x00, 0x48,
    0x00, 0x48, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08,
    0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
    0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20,
    0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27,
    0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F,
    0x00, 0xBF, 0x00, 0xFF, 0xD9
])


def generate_sample_epub(output_path: Path) -> Path:
    """Creates a valid, complete EPUB 3 document with two readable chapters and cover art."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with zipfile.ZipFile(output_path, "w") as z:
        # 1. mimetype (first file, uncompressed per EPUB specification)
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF/container.xml
        container_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '    <rootfiles>\n'
            '        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
            '    </rootfiles>\n'
            '</container>'
        )
        z.writestr("META-INF/container.xml", container_xml)

        # 3. Cover art
        z.writestr("OEBPS/images/cover.jpg", SAMPLE_COVER_JPEG)

        # 4. Stylesheet
        css_content = (
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\n"
            "       line-height: 1.6; margin: 4%; color: #2d3748; background-color: #fdfdfd; }\n"
            "h1 { color: #1a365d; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 20px; }\n"
            "h2 { color: #2b6cb0; margin-top: 24px; }\n"
            "p { margin-bottom: 16px; font-size: 1.05rem; }\n"
            ".meta { font-style: italic; color: #718096; margin-bottom: 24px; font-size: 0.95rem; }\n"
            "code { background-color: #edf2f7; padding: 2px 6px; border-radius: 4px; font-family: monospace; }\n"
        )
        z.writestr("OEBPS/styles.css", css_content)

        # 5. Chapter 1 XHTML
        ch1_xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '<head>\n'
            '    <title>Chapter 1: The Cloud-Synced Reader</title>\n'
            '    <link rel="stylesheet" type="text/css" href="styles.css"/>\n'
            '</head>\n'
            '<body>\n'
            '    <h1>Chapter 1: The Cloud-Synced Reader</h1>\n'
            '    <p class="meta">By Sarth Sheth</p>\n'
            '    <p>Welcome to <strong>READ_V2</strong>, a serverless, cloud-synchronized reader built for desktop and mobile reading.</p>\n'
            '    <p>Unlike traditional web applications where large binaries are routed through application servers, READ_V2 leverages '
            '    <strong>direct-to-client transport</strong> via Google Cloud Storage v4 Signed URLs.</p>\n'
            '    <p>This allows files to be streamed directly to the browser viewport without paying for compute proxying or double network egress.</p>\n'
            '</body>\n'
            '</html>'
        )
        z.writestr("OEBPS/chapter1.xhtml", ch1_xhtml)

        # 6. Chapter 2 XHTML
        ch2_xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            '<head>\n'
            '    <title>Chapter 2: Understanding EPUB CFIs</title>\n'
            '    <link rel="stylesheet" type="text/css" href="styles.css"/>\n'
            '</head>\n'
            '<body>\n'
            '    <h1>Chapter 2: Understanding EPUB CFIs</h1>\n'
            '    <p>An EPUB Canonical Fragment Identifier (<code>epubcfi</code>) is a standardized W3C notation.</p>\n'
            '    <p>Because EPUB files are reflowable XHTML packages, physical page numbers change based on font size and display resolution.</p>\n'
            '    <p>A CFI points to the exact DOM element and character offset inside this XHTML document, ensuring your reading position stays identical whether you read on a phone or laptop.</p>\n'
            '</body>\n'
            '</html>'
        )
        z.writestr("OEBPS/chapter2.xhtml", ch2_xhtml)

        # 7. Table of Contents (toc.ncx)
        toc_ncx = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
            '    <head><meta name="dtb:uid" content="urn:uuid:readv2-sample-book"/></head>\n'
            '    <docTitle><text>The Cloud Architecture Handbook</text></docTitle>\n'
            '    <navMap>\n'
            '        <navPoint id="navPoint-1" playOrder="1">\n'
            '            <navLabel><text>Chapter 1: The Cloud-Synced Reader</text></navLabel>\n'
            '            <content src="chapter1.xhtml"/>\n'
            '        </navPoint>\n'
            '        <navPoint id="navPoint-2" playOrder="2">\n'
            '            <navLabel><text>Chapter 2: Understanding EPUB CFIs</text></navLabel>\n'
            '            <content src="chapter2.xhtml"/>\n'
            '        </navPoint>\n'
            '    </navMap>\n'
            '</ncx>'
        )
        z.writestr("OEBPS/toc.ncx", toc_ncx)

        # 8. Package Manifest (OEBPS/content.opf)
        content_opf = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">\n'
            '    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '        <dc:identifier id="BookId">urn:uuid:readv2-sample-book</dc:identifier>\n'
            '        <dc:title>The Cloud Architecture Handbook</dc:title>\n'
            '        <dc:creator>Sarth Sheth</dc:creator>\n'
            '        <dc:language>en</dc:language>\n'
            '        <meta name="cover" content="cover-image"/>\n'
            '    </metadata>\n'
            '    <manifest>\n'
            '        <item id="cover-image" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>\n'
            '        <item id="css" href="styles.css" media-type="text/css"/>\n'
            '        <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>\n'
            '        <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>\n'
            '        <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
            '    </manifest>\n'
            '    <spine toc="ncx">\n'
            '        <itemref idref="ch1"/>\n'
            '        <itemref idref="ch2"/>\n'
            '    </spine>\n'
            '</package>'
        )
        z.writestr("OEBPS/content.opf", content_opf)

    return output_path


def generate_sample_pdf(output_path: Path) -> Path:
    """Creates a valid, complete 3-page PDF document with styled text and metadata."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    pages_text = [
        (
            "The Cloud Architecture Handbook\n"
            "Author: Sarth Sheth\n\n"
            "Page 1: Architecture Overview\n"
            "READ_V2 is a serverless reader designed for zero base monthly cost.\n"
            "Files are delivered directly from Cloud Storage to browser viewports.\n"
            "FastAPI serves strictly as the control plane for metadata and auth."
        ),
        (
            "Page 2: Progress Synchronization Strategy\n\n"
            "In PDF files, pages are fixed geometry. Progress is stored as an integer ('42').\n"
            "The client reader debounces progress updates to every 15 seconds.\n"
            "Immediate flushing occurs on reader close or browser visibility change."
        ),
        (
            "Page 3: Google Cloud Platform Always-Free Tier\n\n"
            "All resources are pinned strictly to us-central1 (Iowa).\n"
            "Cloud Storage: 5 GB Standard Storage.\n"
            "Cloud Firestore: 50,000 document reads, 20,000 document writes per day.\n"
            "Cloud Run: Scales to zero instances when idle ($0 base recurring cost)."
        ),
    ]
    
    title = "The Cloud Architecture Handbook"
    author = "Sarth Sheth"
    
    header = b"%PDF-1.4\n"
    objs = []
    
    # 1: Catalog
    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    
    # 2: Pages container
    kids_str = " ".join(f"{i + 3} 0 R" for i in range(len(pages_text)))
    objs.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(pages_text)} >>\nendobj\n".encode("latin-1"))
    
    content_obj_start = 3 + len(pages_text)
    font_obj_id = content_obj_start + len(pages_text)
    info_obj_id = font_obj_id + 1
    
    # Page objects
    for i in range(len(pages_text)):
        page_id = 3 + i
        cont_id = content_obj_start + i
        objs.append(
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {cont_id} 0 R "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> >>\nendobj\n".encode("latin-1")
        )
        
    # Content stream objects
    for i, txt in enumerate(pages_text):
        cont_id = content_obj_start + i
        lines = txt.split("\n")
        stream_body = b"BT /F1 14 Tf 50 720 Td "
        for line in lines:
            safe_line = line.replace("(", "\\(").replace(")", "\\)")
            stream_body += f"({safe_line}) Tj 0 -22 Td ".encode("latin-1")
        stream_body += b"ET\n"
        objs.append(
            f"{cont_id} 0 obj\n<< /Length {len(stream_body)} >>\nstream\n".encode("latin-1")
            + stream_body
            + b"endstream\nendobj\n"
        )
        
    # Font definition
    objs.append(f"{font_obj_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode("latin-1"))
    
    # Document Info Dictionary
    objs.append(f"{info_obj_id} 0 obj\n<< /Title ({title}) /Author ({author}) /Creator (READ_V2 Generator) >>\nendobj\n".encode("latin-1"))
    
    # Compute byte offsets for exact xref table
    offsets = [0]
    curr = len(header)
    for obj in objs:
        offsets.append(curr)
        curr += len(obj)
        
    startxref = curr
    xref = f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets[1:]:
        xref += f"{off:010d} 00000 n \n".encode("latin-1")
        
    trailer = f"trailer\n<< /Size {len(offsets)} /Root 1 0 R /Info {info_obj_id} 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode("latin-1")
    
    with open(output_path, "wb") as f:
        f.write(header + b"".join(objs) + xref + trailer)
        
    return output_path


def main():
    print("=== Generating Sample EPUB and PDF Files on Disk ===")
    
    sample_dir = Path(__file__).resolve().parent.parent / "sample_books"
    sample_dir.mkdir(parents=True, exist_ok=True)
    
    epub_path = sample_dir / "sample.epub"
    pdf_path = sample_dir / "sample.pdf"
    
    # 1. Generate files
    generate_sample_epub(epub_path)
    generate_sample_pdf(pdf_path)
    
    print(f"\n[Created EPUB]: {epub_path} ({epub_path.stat().st_size} bytes)")
    print(f"[Created PDF] : {pdf_path} ({pdf_path.stat().st_size} bytes)")
    
    # 2. Parse using our services to verify
    print("\n--- Verifying EPUB Parser on Disk File ---")
    parsed_epub = parse_epub(epub_path)
    print(f"Title       : {parsed_epub.title}")
    print(f"Author      : {parsed_epub.author}")
    print(f"Language    : {parsed_epub.language}")
    print(f"Format      : {parsed_epub.format}")
    print(f"SHA-256     : {parsed_epub.sha256_hash}")
    print(f"Cover Art   : {len(parsed_epub.cover_image_bytes) if parsed_epub.cover_image_bytes else 0} bytes")
    
    print("\n--- Verifying PDF Parser on Disk File ---")
    parsed_pdf = parse_pdf(pdf_path)
    print(f"Title       : {parsed_pdf.title}")
    print(f"Author      : {parsed_pdf.author}")
    print(f"Format      : {parsed_pdf.format}")
    print(f"Total Pages : {parsed_pdf.total_pages}")
    print(f"SHA-256     : {parsed_pdf.sha256_hash}")
    
    print("\n[SUCCESS] Sample books created! You can now open them directly on your machine.")


if __name__ == "__main__":
    main()

