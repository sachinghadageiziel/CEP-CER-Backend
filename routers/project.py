from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models.project_model import Project
from db.schemas.project_schema import ProjectCreate
from datetime import date
import os

router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"]
)


# =====================================================
# DB SESSION
# =====================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# CREATE PROJECT (POST)
# =====================================================
@router.post("/addProject")
def create_project(
    title: str = Form(...),
    start_date: date | None = Form(None),
    end_date: date | None = Form(None),
    ifu_pdf: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    # 1️ Create project FIRST
    project = Project(
        title=title,
        start_date=start_date,
        end_date=end_date,
        status="Active"
    )

    db.add(project)
    db.commit()
    db.refresh(project)  # project.id is now available

    # 2️ Save IFU under database/projects/{project_id}/IFU.pdf
    if ifu_pdf:
        if not ifu_pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="IFU must be a PDF")

        project_folder = f"database/projects/{project.id}"
        os.makedirs(project_folder, exist_ok=True)

        ifu_path = f"{project_folder}/IFU.pdf"

        with open(ifu_path, "wb") as f:
            f.write(ifu_pdf.file.read())

        # 3️ Update project with IFU info
        project.ifu_file_path = ifu_path
        project.ifu_file_name = "IFU.pdf"

        db.commit()
        db.refresh(project)

    return {
        "id": project.id,
        "title": project.title,
        "ifu_file": project.ifu_file_name,
        "status": project.status
    }

# =====================================================
# GET ALL PROJECTS (GET)
# =====================================================
@router.get("/existing")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.id.desc()).all()

    return [
        {
            "id": p.id,
            "title": p.title,
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.status
        }
        for p in projects
    ]
