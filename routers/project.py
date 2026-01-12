from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models.project_model import Project
from db.schemas.project_schema import ProjectCreate

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
@router.post("")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db)
):
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    project = Project(
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status="Active"
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "title": project.title,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "status": project.status
    }


# =====================================================
# GET ALL PROJECTS (GET)
# =====================================================
@router.get("")
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
