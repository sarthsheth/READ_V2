"""
Main entry point for Cloud-Synced Personal Reader (READ_V2) FastAPI Backend.
Acts as the control plane for metadata, authentication, signed URLs, and reading progress.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings

settings = get_settings()

app = FastAPI(
    title="Cloud-Synced Personal Reader API",
    description="Control plane for personal EPUB & PDF cloud reading with zero base cost.",
    version="0.1.0",
)

# Enable Cross-Origin Resource Sharing (CORS) for local and Cloud Run origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint used by Cloud Run and uptime monitors."""
    return {
        "status": "ok",
        "service": "read-v2-api",
        "version": "0.1.0",
        "region": settings.gcp_region,
        "mock_gcp": settings.mock_gcp,
    }


@app.get("/", tags=["Root"])
async def root():
    """Root info endpoint."""
    return {
        "message": "Cloud-Synced Personal Reader API is running",
        "docs_url": "/docs",
        "health_url": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    print(f"Starting READ_V2 server at http://{settings.host}:{settings.port}")
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)

