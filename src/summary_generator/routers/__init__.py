from fastapi import APIRouter
from summary_generator.routers import auth, summary, documents, retrieval

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(summary.router)
api_router.include_router(documents.router)
api_router.include_router(retrieval.router)
