from fastapi import APIRouter, Form, Depends
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models.project_model import Project

router = APIRouter(prefix="/api/projects", tags=["Projects"])


# =====================================================
# DB SESSION DEPENDENCY
# =====================================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================
# CREATE NEW PROJECT
# =====================================================
@router.post("/create")
def create_project(
    title: str = Form(...),
    duration: str = Form(""),
    description: str = Form(""),
    owner: str = Form(""),
    db: Session = Depends(get_db)
):
    # Count existing projects
    count = db.query(Project).count()

    # Generate project ID → PRJ-001, PRJ-002 ...
    project_id = f"PRJ-{count + 1:03d}"

    project = Project(
        id=project_id,
        title=title,
        duration=duration,
        description=description,
        owner=owner,
        status="Active"
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "status": "success",
        "project": {
            "id": project.id,
            "title": project.title,
            "duration": project.duration,
            "description": project.description,
            "owner": project.owner,
            "status": project.status
        }
    }


# =====================================================
# GET LIST OF PROJECTS
# =====================================================
@router.get("/list")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()

    return {
        "projects": [
            {
                "id": p.id,
                "title": p.title,
                "duration": p.duration,
                "description": p.description,
                "owner": p.owner,
                "status": p.status
            }
            for p in projects
        ]
    }
