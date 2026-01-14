from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.authRoute import router as auth_router
from db.database import engine, Base

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