import logging
import os

from fastapi import FastAPI
from workers.gpu import gpu_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Lucy-Edit-Dev on Runpod Flash",
    description="Video editing API powered by decart-ai/Lucy-Edit-Dev",
    version="0.1.0",
)

app.include_router(gpu_router, prefix="/gpu", tags=["Lucy GPU Worker"])


@app.get("/")
def home() -> dict:
    return {
        "message": "Lucy-Edit-Dev Flash API",
        "docs": "/docs",
        "endpoints": {
            "edit_video": "POST /gpu/edit",
            "health": "GET /health",
        },
    }


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("FLASH_HOST", "localhost")
    port = int(os.getenv("FLASH_PORT", 8000))
    logger.info(f"Starting Flash server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
