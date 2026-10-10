# Architecture & Code Review Learning Guide: Cloud-Synced Personal Reader (READ_V2)

## Purpose of this Guide
This document bridges the gap between enterprise data engineering (Hive, Oracle SQL, Spark, DDL, ACID transactions) and modern serverless web application engineering (FastAPI, Cloud Firestore NoSQL, Cloud Storage v4 Signed URLs, `epub.js`, `pdf.js`, and Google OAuth 2.0).

Review this guide to understand the underlying mechanics, architectural trade-offs, and code patterns you will encounter during implementation and code reviews.

---

## 1. Control Plane vs. Data Plane (Direct-to-Client File Transport)

### The Conceptual Shift
In traditional enterprise applications, the backend server acts as a proxy: it reads the binary from disk/S3 and streams it over HTTP to the client. In our serverless architecture, **FastAPI never handles book files**. Doing so would exhaust Cloud Run's 512 MiB memory cap, keep CPU instances active (wasting free tier minutes), and double network egress bandwidth.

Instead:
* **FastAPI (Control Plane)** handles metadata, mints temporary credentials, and saves reading progress.
* **Cloud Storage (Data Plane)** transfers files directly to and from the browser.

```
┌────────────────────────────────────────────────────────────────────────┐
│ CONTROL PLANE (FastAPI on Cloud Run)                                   │
│  - Mint short-lived v4 Signed URLs                                     │
│  - Verify Google OAuth JWT ID tokens                                   │
│  - Update reading progress in Firestore                                │
└───────────────────────┬────────────────────────────────────────────────┘
                        │ Returns JSON with Signed URL
                        ▼
┌──────────────────┐  HTTP GET (Byte Range)  ┌───────────────────────────┐
│ Browser (Client) │ ◄──────────────────────►│ Cloud Storage (GCS Bucket)│
└──────────────────┘                         └───────────────────────────┘
```

### Key Topics to Understand
1. **GCS v4 Signed URLs**: 
   * A URL with an embedded query string containing an HMAC-SHA256 signature generated using a service account private key.
   * Grants limited, time-bound (15–30 min) access to download (`GET`) or upload (`PUT`) a private GCS object without making the bucket public.
2. **HTTP 206 Partial Content (Byte-Range Requests)**:
   * Header: `Range: bytes=0-1048575`.
   * GCS responds with `206 Partial Content` and only the requested bytes. E-readers use this to stream 50 MB PDFs page-by-page without downloading the full document upfront.
3. **CORS (Cross-Origin Resource Sharing)**:
   * Because your web page lives on `localhost:8000` or `reader-app.a.run.app` and file bytes come from `storage.googleapis.com`, GCS must return `Access-Control-Allow-Origin` headers or the browser will block the download.

### Recommended Sources
* 📖 [Google Cloud Storage: Signed URLs Overview](https://cloud.google.com/storage/docs/access-control/signed-urls) — Official guide on how v4 signed URLs work.
* 📖 [MDN Web Docs: HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests) — How byte-range chunking works over HTTP.
* 📖 [Google Cloud Storage: Configuring CORS on a Bucket](https://cloud.google.com/storage/docs/using-cors) — Configuring XML/JSON CORS policies on GCS.

---

## 2. E-Reader Mechanics & Progress Locators (EPUB vs. PDF)

### The Conceptual Shift
In database terms, you might expect reading progress to be an integer `page_number`. For PDFs, this works because PDFs have fixed page geometries. For EPUBs, it fails completely: EPUBs are reflowable XHTML packages. Changing the font family, font size, margin, or screen size alters the number of visual screens.

```
┌─────────────────────────────────┬─────────────────────────────────┐
│ PDF: Fixed Layout               │ EPUB: Reflowable Layout         │
├─────────────────────────────────┼─────────────────────────────────┤
│ Page 42 on Desktop is identical │ Page 42 on Desktop might be     │
│ to Page 42 on Mobile.           │ Page 118 on Mobile.             │
│ Locator: Integer string ("42")  │ Locator: EPUB CFI String        │
│ Rendering: HTML5 <canvas>       │ Rendering: Nested <iframe>      │
└─────────────────────────────────┴─────────────────────────────────┘
```

### Key Topics to Understand
1. **EPUB CFI (Canonical Fragment Identifier)**:
   * A standardized W3C notation (e.g., `epubcfi(/6/14[chap04]!/4/2/10/1:0)`).
   * It indexes into the OPF package spine (`/6`), chapter document (`/14`), DOM elements (`/4/2/10`), and character offsets (`1:0`).
   * When restoring position, `epub.js` navigates to that exact DOM node regardless of font size or screen resolution.
2. **Rendering Libraries**:
   * **`epub.js`**: Renders EPUB content inside a sandboxed `<iframe>`, calculates locations, and emits CFI change events.
   * **`pdf.js` (Mozilla)**: Parses the PDF binary, handles font rendering, and draws pages onto HTML5 `<canvas>` elements.
3. **Client-Side Debouncing & Lifecycle Hooks**:
   * If a user flips 30 pages quickly, we must not send 30 API requests to Firestore (which wastes daily write quotas).
   * The client waits **15 seconds** after the last page turn before syncing to the backend.
   * An immediate sync is triggered using `document.visibilityState === 'hidden'` (tab switch/close) or `beforeunload`.
4. **IndexedDB**:
   * The browser's transactional key-value / document database. Used to cache downloaded book binaries locally for offline reading.

### Recommended Sources
* 📖 [W3C EPUB Canonical Fragment Identifier (epubcfi) Specification](https://idpf.org/epub/linking/cfi/epub-cfi.html) — Standard specification for EPUB CFIs.
* 📖 [Futurepress `epub.js` Official Documentation & Examples](https://github.com/futurepress/epub.js/) — Quick-start and API guide for `epub.js`.
* 📖 [Mozilla `pdf.js` Getting Started](https://mozilla.github.io/pdf.js/) — Architecture and canvas rendering patterns for `pdf.js`.
* 📖 [MDN Web Docs: Document `visibilitychange` Event](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event) — Best practice for reliable client-state flushing.
* 📖 [MDN Web Docs: Working with IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB) — Client-side storage fundamentals.

---

## 3. Firestore Native NoSQL (Bridging from Hive & Oracle SQL)

### Mental Model Translation

| Relational / Hive Concept | Firestore Native Equivalent | Crucial Behavioral Difference |
| :--- | :--- | :--- |
| **Database Schema** | **Database Instance** | Schemaless documents inside named collections. |
| **Table** | **Collection** (`books`) | Documents inside a collection can have varied keys. |
| **Row** | **Document** (`books/{id}`) | Semi-structured JSON object (up to 1 MiB max). |
| **Primary Key** | **Document ID** | Content SHA-256 hash: `books/9f86d081...` |
| **Full Table Scan (FTS)** | **Prohibited by Design** | Firestore rejects queries without an supporting index; there is no scan fallback. |
| **`JOIN`** | **Denormalization** | Cross-document joins do not exist. Related data is embedded to reduce document reads. |
| **ACID Multi-row Locks** | **Atomic Field Updates** | Single-document updates using dot notation are atomic and cost 1 write operation. |

### Key Topics to Understand
1. **Firestore Pricing & Quota Discipline**:
   * Firestore charges **per document operation**, not per byte or query execution time.
   * Free tier: **50,000 reads/day** and **20,000 writes/day**.
   * Normalizing reading progress into a separate table (`reading_progress`) would double reads (50 books = 100 reads). Denormalizing `progress` inside `books/{book_id}` keeps it to 50 reads.
2. **Atomic Dot-Notation Updates**:
   * Instead of overwriting the entire book document on every page turn:
     ```python
     # Atomic subfield update (touches only progress without reading or overwriting book metadata)
     doc_ref.update({
         "progress.locator_value": cfi,
         "progress.percentage": 0.42,
         "progress.last_read_at": firestore.SERVER_TIMESTAMP
     })
     ```
3. **Server Timestamps**:
   * Always use `firestore.SERVER_TIMESTAMP` instead of client timestamps to prevent clocks out-of-sync across desktop and mobile devices.

### Recommended Sources
* 📖 [Google Cloud Firestore: Data Model](https://cloud.google.com/firestore/docs/data-model) — Collections, documents, and subcollections.
* 📖 [Google Cloud Firestore: Updating Data & Dot Notation](https://cloud.google.com/firestore/docs/manage-data/add-data#update_fields_in_nested_objects) — Updating nested fields.
* 🎥 [Google Cloud / Firebase: Cloud Firestore Data Modeling Series (YouTube)](https://www.youtube.com/watch?v=haMOUb3KVSo) — Excellent video series on SQL to NoSQL translation and denormalization.

---

## 4. Backend Architecture: FastAPI & Pydantic v2

### The Conceptual Shift
In data engineering, Python code is often script-based (PySpark jobs, Airflow DAGs) running sequentially or in workers. FastAPI is an asynchronous, event-loop-driven ASGI framework built on top of Starlette and Pydantic.

```python
# Declarative Route Contract with Dependency Injection
@app.get("/api/books/{book_id}/read-url", response_model=ReadUrlResponse)
async def get_read_url(
    book_id: str,
    user: dict = Depends(verify_user)  # Auth Guard executed before handler runs
):
    ...
```

### Key Topics to Understand
1. **FastAPI Dependency Injection (`Depends`)**:
   * A declarative way to extract cross-cutting concerns (authentication, database sessions, configuration) into reusable functions.
   * If `verify_user` raises an `HTTPException(401)`, the route handler code is never executed.
2. **Pydantic v2 Schema Validation**:
   * Uses Python type hints (`str`, `int`, `Optional[float]`, `BaseModel`) to validate incoming JSON bodies and serialize outgoing responses.
   * Validates data at the boundary and rejects malformed payloads with automatic `422 Unprocessable Entity` responses.
3. **Async / Await (`async def`)**:
   * Cooperative multitasking. While an I/O operation (e.g., Firestore API network round-trip) is awaiting a response, the single Python process handles other incoming HTTP requests.

### Recommended Sources
* 📖 [FastAPI Official Tutorial: First Steps](https://fastapi.tiangolo.com/tutorial/) — Core overview of routes, path parameters, and query parameters.
* 📖 [FastAPI Tutorial: Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) — Essential for understanding the auth injection pipeline.
* 📖 [Pydantic v2 Documentation: Models](https://docs.pydantic.dev/latest/concepts/models/) — Data validation and schema definition.

---

## 5. Security & Authentication: Google Identity Services (GIS)

### The Conceptual Shift
Instead of implementing custom username/password tables, salt/hashing, session cookies, and refresh token rotation, we delegate authentication to Google Identity Platform. Because this is a single-user system, we configure Google OAuth in **Testing Mode**.

```
┌─────────────────────────────────┐
│ 1. User signs in with Google    │
│    (GIS Button in Browser)      │
└────────────────┬────────────────┘
                 │ Returns signed JWT ID Token
                 ▼
┌─────────────────────────────────┐
│ 2. Browser sends Bearer Token   │
│    Headers: Authorization: ...  │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│ 3. FastAPI backend verifies:    │
│    - Cryptographic signature    │
│    - aud == GOOGLE_CLIENT_ID    │
│    - email == ALLOWED_EMAIL     │
└─────────────────────────────────┘
```

### Key Topics to Understand
1. **JSON Web Token (JWT) Anatomy**:
   * Three Base64Url-encoded segments: `Header.Payload.Signature`.
   * The payload contains standard OpenID claims:
     * `sub`: Google's immutable user ID.
     * `email`: User's Gmail address.
     * `aud`: The OAuth Client ID the token was minted for.
     * `exp`: Expiration timestamp (typically 1 hour).
2. **Cryptographic Signature Verification**:
   * Google publishes its public signing certificates at a well-known URL.
   * The backend library (`google-auth`) caches these certs and verifies the signature locally without calling Google's API on every single request.
3. **Single-User Perimeter Enforcement**:
   * Checking that the token is valid is not enough (any Google user could sign in).
   * The backend strictly compares `idinfo["email"] == os.environ["ALLOWED_EMAIL"]`. If they don't match, it raises `403 Forbidden`.

### Recommended Sources
* 📖 [Google Identity Services: Sign In With Google for Web](https://developers.google.com/identity/gsi/web/guides/overview) — Client-side GIS overview.
* 📖 [Google Developers: Verify Google ID Tokens in Python](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token) — Backend cryptographic verification guide.
* 📖 [Introduction to JSON Web Tokens (jwt.io)](https://jwt.io/introduction) — Visual explanation of JWT structure and claims.

---

## 6. Serverless Compute & Containerization (Cloud Run & Docker)

### The Conceptual Shift
In traditional infrastructure, a virtual machine or container runs 24/7, consuming budget every minute even when idle. Cloud Run is a fully managed serverless container runtime that scales down to **zero instances** when there are no requests.

```
Request arrives ──► Spin up container (~1.5s cold start) ──► Handle request ──► Idle 15 min ──► Scale to 0 ($0/mo)
```

### Key Topics to Understand
1. **Scale-to-Zero & Cold Starts**:
   * Setting `--min-instances 0` ensures zero idle costs.
   * The first request after idle incurs a small latency ("cold start") while the container pulls and starts.
   * We optimize cold starts by keeping the Docker image small and deferring heavy library imports.
2. **Docker Layer Optimization & Artifact Registry Quotas**:
   * GCP provides **0.5 GB-months** of free container image storage in Artifact Registry.
   * Standard Python base images (`python:3.12`) are ~1.0 GB and instantly trigger recurring storage charges.
   * We use `python:3.12-slim` (< 150 MB) and structure the Dockerfile so dependencies are cached in early layers:
     ```dockerfile
     FROM python:3.12-slim
     WORKDIR /app
     COPY requirements.txt .
     RUN pip install --no-cache-dir -r requirements.txt
     COPY . .
     ```
3. **GCP Region Locking (`us-central1`)**:
   * The GCP Always-Free tier only applies to specific regions (`us-central1`, `us-east1`, `us-west1`).
   * Deploying storage or compute to regions like `asia-south1` incurs charges from byte 1.

### Recommended Sources
* 📖 [Google Cloud Run: What is Cloud Run?](https://cloud.google.com/run/docs/overview/what-is-cloud-run) — Core concepts and lifecycle.
* 📖 [Google Cloud Run: Container Runtime Contract](https://cloud.google.com/run/docs/reference/container-contract) — Port binding (`PORT=8080`), memory, and process signals.
* 📖 [Docker Documentation: Best Practices for Writing Dockerfiles](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/) — Layer ordering and size optimization.
* 📖 [Google Cloud: Always-Free Tier Products and Limits](https://cloud.google.com/free/docs/free-cloud-features#always-free-products) — The exact limits for Cloud Run, GCS, and Firestore.

---

## Summary: Fast-Track Reading Checklist

Before diving into PR reviews, spend 15–20 minutes reviewing these three high-impact references:
1. [ ] **FastAPI Dependencies**: [FastAPI Tutorial - Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
2. [ ] **GCS Signed URLs**: [GCS v4 Signed URLs](https://cloud.google.com/storage/docs/access-control/signed-urls)
3. [ ] **EPUB CFI Concept**: [W3C EPUB CFI Specification](https://idpf.org/epub/linking/cfi/epub-cfi.html)

