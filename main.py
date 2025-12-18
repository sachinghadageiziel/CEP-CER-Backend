from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.project import router as project_router
from routers.literature import router as literature_router
from routers.primary import router as primary_router
from routers.secondary import router as secondary_router 

app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ROUTERS
app.include_router(project_router)
app.include_router(literature_router)
app.include_router(primary_router)
app.include_router(secondary_router)

@app.get("/")
def health():
    return {"status": "OK"}
