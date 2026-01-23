from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
 
from db.database import SessionLocal
from db.models.project_model import Project
from db.schemas.project_schema import ProjectCreate
from datetime import date
import os
from fastapi.responses import StreamingResponse
import io
 
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
@router.post("/project")
def create_project(
    title: str = Form(...),
    owner: str = Form(...),              
    start_date: date | None = Form(None),
    end_date: date | None = Form(None),
    primary_criteria: str | None = Form(None),
    secondary_criteria: str | None = Form(None),
    ifu_pdf: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    if not title.strip():
        raise HTTPException(status_code=400, detail="Title is required")
 
    if not owner.strip():
        raise HTTPException(status_code=400, detail="Owner is required")
 
    project = Project(
        title=title,
        owner=owner,                
        start_date=start_date,
        end_date=end_date,
        primary_criteria=primary_criteria,
        secondary_criteria=secondary_criteria,
        status="Active"
    )
 
    if ifu_pdf:
        if not ifu_pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="IFU must be a PDF")
 
        pdf_bytes = ifu_pdf.file.read()
        project.ifu_file_data = pdf_bytes
        project.ifu_file_name = ifu_pdf.filename
        project.ifu_content_type = ifu_pdf.content_type
 
    db.add(project)
    db.commit()
    db.refresh(project)
 
    return {
        "id": project.id,
        "title": project.title,
        "owner": project.owner,              
        "ifu_uploaded": bool(project.ifu_file_data),
        "status": project.status
    }
 
 
# =====================================================
# GET ALL PROJECTS (GET)
# =====================================================
@router.get("/projects")
def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.id.desc()).all()
 
    return [
        {
            "id": p.id,
            "title": p.title,
            "owner": p.owner,            
            "start_date": p.start_date,
            "end_date": p.end_date,
            "status": p.status
        }
        for p in projects
    ]
 
 
@router.get("/{project_id}/ifu")
def download_ifu(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
 
    if not project or not project.ifu_file_data:
        raise HTTPException(404, "IFU not found")
 
    return StreamingResponse(
        io.BytesIO(project.ifu_file_data),
        media_type=project.ifu_content_type,
        headers={
            "Content-Disposition": f"attachment; filename={project.ifu_file_name}"
        }
    )
 
# =====================================================
# UPDATE PROJECT (PUT)
# =====================================================
@router.put("/{project_id}")
def update_project(
    project_id: int,
    title: str | None = Form(None),
    start_date: date | None = Form(None),
    end_date: date | None = Form(None),
    status: str | None = Form(None),
    primary_criteria: str | None = Form(None),
    secondary_criteria: str | None = Form(None),
    ifu_pdf: UploadFile | None = File(None),
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
 
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
 
    # Update simple fields
    if title is not None:
        if not title.strip():
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        project.title = title
 
    if start_date is not None:
        project.start_date = start_date
 
    if end_date is not None:
        project.end_date = end_date
 
    if status is not None:
        project.status = status
 
    if primary_criteria is not None:
        project.primary_criteria = primary_criteria
 
    if secondary_criteria is not None:
        project.secondary_criteria = secondary_criteria
 
    # Update IFU if provided
    if ifu_pdf:
        if not ifu_pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="IFU must be a PDF")
 
        pdf_bytes = ifu_pdf.file.read()
        project.ifu_file_data = pdf_bytes
        project.ifu_file_name = ifu_pdf.filename
        project.ifu_content_type = ifu_pdf.content_type
 
    db.commit()
    db.refresh(project)
 
    return {
        "status": "success",
        "project_id": project.id,
        "title": project.title,
        "ifu_uploaded": bool(project.ifu_file_data),
        "project_status": project.status
    }
# =====================================================
# DELETE PROJECT (DELETE)
# =====================================================
@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db)
):
    project = db.query(Project).filter(Project.id == project_id).first()
 
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
 
    db.delete(project)
    db.commit()
 
    return {
        "status": "success",
        "message": "Project deleted successfully",
        "project_id": project_id
    }


@router.get("/{project_id}/ifu")
def download_ifu(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()

    if not project or not project.ifu_file_data:
        raise HTTPException(404, "IFU not found")

    return StreamingResponse(
        io.BytesIO(project.ifu_file_data),
        media_type=project.ifu_content_type,
        headers={
            "Content-Disposition": f"attachment; filename={project.ifu_file_name}"
        }
    )
