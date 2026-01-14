from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.authRoute import router as auth_router
from db.database import engine, Base

from routers.project import router as project_router
from routers.literature import router as literature_router
from routers.primary import router as primary_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CEP-CER Healthcare API",
    description="Healthcare application with Microsoft Authentication",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(literature_router)
app.include_router(primary_router)

@app.get("/")
async def root():
    return {
        "message": "CEP-CER Healthcare API",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected"
    }