from fastapi import APIRouter, Form
import os
import json
from pathlib import Path
from services.project_paths import ensure_base_structure, ensure_project_folders, PROJECTS_FILE, BASE_DIR

router = APIRouter(prefix="/api/projects", tags=["Projects"])


# =====================================================
# CREATE NEW PROJECT
# =====================================================
@router.post("/create")
def create_project(
    title: str = Form(...),
    duration: str = Form(""),
    description: str = Form(""),
    owner: str = Form("")
):
    ensure_base_structure()

    # Load existing list
    data = json.loads(Path(PROJECTS_FILE).read_text())
    existing = data["projects"]

    # Generate next project ID: PRJ-001, PRJ-002 ...
    next_num = len(existing) + 1
    project_id = f"PRJ-{next_num:03d}"

    # Create project folder structure
    paths = ensure_project_folders(project_id)

    # Save meta.json
    meta = {
        "id": project_id,
        "title": title,
        "duration": duration,
        "description": description,
        "owner": owner,
        "status": "Active"
    }

    with open(os.path.join(paths["root"], "meta.json"), "w") as f:
        json.dump(meta, f, indent=4)

    # Append to projects.json
    existing.append(meta)
    Path(PROJECTS_FILE).write_text(json.dumps({"projects": existing}, indent=4))

    return {
        "status": "success",
        "project": meta
    }


# =====================================================
# GET LIST OF PROJECTS
# =====================================================
@router.get("/list")
def list_projects():
    ensure_base_structure()

    if not PROJECTS_FILE.exists():
        return {"projects": []}

    data = json.loads(Path(PROJECTS_FILE).read_text())
    return data
