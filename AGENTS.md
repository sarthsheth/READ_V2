# Agent Guidelines & Project Rulebook: Cloud-Synced Personal Reader (READ_V2)

## 1. Project Overview & Philosophy
READ_V2 is a lightweight, serverless cloud-synced reader for EPUB and PDF files built for a single user.
- **Full Architecture Spec**: Refer to [`DESIGN.md`](./DESIGN.md) for detailed contracts and rationale.
- **Core Directive**: The system must operate with **zero recurring base monthly cost** by staying strictly within Google Cloud Platform's permanent Always-Free tier allowances.

---

## 2. Inviolable Architectural Invariants (DO NOT BREAK)

### 2.1 GCP Always-Free Tier & Region Pinning
* **Region Lock**: ALL GCP resources (Cloud Run, Cloud Storage, Cloud Firestore) **MUST** be deployed in `us-central1` (Iowa) or `us-east1`.
  * *Never deploy to non-free-tier regions* (e.g., `asia-south1`, `europe-west1`), as GCP charges for storage from byte 1 in those regions.
* **Storage Class**: Cloud Storage buckets must use `STANDARD` storage class with Uniform Bucket-Level Access. Do not set lifecycle rules transitioning to `NEARLINE` or `COLDLINE` (which incur retrieval fees and forfeit free credits).
* **Cloud Run Config**:
  * `min-instances: 0` (scale-to-zero when idle is mandatory).
  * `max-instances: 2` (cost safety cap).
  * Memory: `512MiB`, vCPU: `1`.
* **Artifact Registry Budget**: Total container image size must stay under **200 MB** (uncompressed) to stay well within the 0.5 GB-month free image storage limit. Always use `python:3.12-slim` with `--no-cache-dir`.

### 2.2 Direct-to-Client File Transport (No Compute Proxying)
* **Never stream or proxy book binaries (`.epub`, `.pdf`) through FastAPI / Cloud Run.**
* The FastAPI backend is solely the control plane.
* File downloads and uploads must use **Google Cloud Storage v4 Signed URLs** with short TTLs (15–30 minutes). The browser downloads directly from and uploads directly to GCS using byte-range requests (`Partial Content 206`).

### 2.3 Single-User Security Perimeter
* **Authentication**: Google Identity Services (GIS) / OAuth 2.0 Client ID in "Testing" mode.
* **Backend Enforcement**: Every protected endpoint MUST enforce the `verify_user` dependency:
  1. Cryptographically verify the Google Bearer ID token against Google's public certs (`google.oauth2.id_token.verify_oauth2_token`).
  2. Validate audience matches `GOOGLE_CLIENT_ID`.
  3. Strict email check: `idinfo["email"] == os.environ["ALLOWED_EMAIL"]`. Reject any unauthorized account with `403 Forbidden`.

### 2.4 Firestore Native Mode Schema & Quota Discipline
* **Database Mode**: Cloud Firestore in **Native Mode** (not Datastore mode).
* **Single Collection**: Store books and reading state in a single collection: `books`.
* **Document ID**: Primary key is the **SHA-256 content hash** of the book binary (`books/{sha256_hash}`).
* **Denormalized Progress**: The `progress` map is embedded directly inside the `books/{book_id}` document. Never separate reading progress into a second collection for single-user mode (avoids double document reads).
* **Atomic Updates**: Update progress using dot notation: `doc_ref.update({"progress.locator_value": ..., "progress.last_read_at": firestore.SERVER_TIMESTAMP})`.
* **No Full-Collection Scans**: Firestore pricing is per document operation. Never perform unbounded queries.

### 2.5 Progress Locators (EPUB vs PDF)
* **EPUB**: Must use **EPUB CFI (Canonical Fragment Identifier)** strings (e.g., `epubcfi(/6/14[chap04]!/4/2/10/1:0)`) generated via `epub.js`. *Never use page numbers for EPUBs* (font scaling and screen sizes invalidate page numbers).
* **PDF**: Must use integer page numbers as strings (e.g., `"42"`) generated via `pdf.js`.

### 2.6 Client Progress Debouncing
* The frontend reader must debounce progress synchronization to the backend to every **15 seconds** during continuous reading.
* Immediate sync must be triggered only on:
  * Reader close / return to library catalog.
  * Browser visibility change (`document.visibilityState === 'hidden'`).
  * Page unload (`beforeunload`).

---

## 3. Tech Stack Conventions

| Layer | Technology | Key Libraries / Rules |
| :--- | :--- | :--- |
| **Backend** | Python 3.12 | `fastapi`, `pydantic-v2`, `uvicorn`, `google-cloud-storage`, `google-cloud-firestore`, `google-auth` |
| **Ingestion / Metadata** | Python | Standard library `zipfile` / `xml.etree` for EPUB OPF parsing; lightweight PDF metadata extractor |
| **Container** | Docker | Base image `python:3.12-slim`, non-root user, lean build |
| **Frontend** | Modern Web SPA | Vanilla JS / Svelte / React + Tailwind CSS; `epub.js` for EPUBs, `pdf.js` for PDFs; IndexedDB for offline cache |
| **Infrastructure** | GCP (Serverless) | Cloud Run, Cloud Storage, Firestore Native, Artifact Registry |

---

## 4. Environment Variables

```bash
GOOGLE_CLIENT_ID="<your-oauth-client-id>.apps.googleusercontent.com"
ALLOWED_EMAIL="yourname@gmail.com"
GCS_BUCKET_NAME="my-reader-library-us-central1"
GCP_PROJECT_ID="personal-reader-app"
```

---

## 5. Coding & Workflow Standards

1. **Follow the Skills**: Consult installed skills in [`.agents/skills/`](./.agents/skills/):
   - [`fastapi-pro`](./.agents/skills/fastapi-pro/SKILL.md) for async routes and Pydantic schemas.
   - [`frontend-design`](./.agents/skills/frontend-design/SKILL.md) for reader UI, typography, and palette.
   - [`gcp-cloud-run`](./.agents/skills/gcp-cloud-run/SKILL.md) & [`mastering-gcloud-commands`](./.agents/skills/mastering-gcloud-commands/SKILL.md) for cloud deployments.
   - [`security-and-hardening`](./.agents/skills/security-and-hardening/SKILL.md) for auth token and input verification.
   - [`test-driven-development`](./.agents/skills/test-driven-development/SKILL.md) for endpoint test coverage.
2. **Type Safety & Validation**: All backend functions and routes must have strict Python type hints and Pydantic request/response models.
3. **Error Handling**: Return clean HTTP exceptions (`400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`) with actionable error messages.
4. **Documentation**: Keep comments concise; maintain docstrings on API route handlers explaining query parameters and expected headers.

