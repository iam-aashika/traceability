from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.api.routes import ingestion, documents, sections, selections, generation, retrieval

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema
    init_db()
    yield

app = FastAPI(
    title="CT-200 Document Traceability & AI-Powered QA Test Generation API",
    description=(
        "Production backend system for medical device manual processing, "
        "hierarchical versioned document browsing, version-pinned requirement selection, "
        "LLM QA test generation, and retrieval-time staleness impact detection."
    ),
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(ingestion.router)
app.include_router(documents.router)
app.include_router(sections.router)
app.include_router(selections.router)
app.include_router(generation.router)
app.include_router(retrieval.router)

@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "CT-200 Document Traceability Platform",
        "version": "1.0.0",
        "llm_provider": settings.LLM_PROVIDER
    }
