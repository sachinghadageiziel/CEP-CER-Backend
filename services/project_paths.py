import os
import json
from pathlib import Path

BASE_DIR = Path("database")
PROJECTS_FILE = BASE_DIR / "projects.json"


def ensure_base_structure():
    BASE_DIR.mkdir(exist_ok=True)
    if not PROJECTS_FILE.exists():
        PROJECTS_FILE.write_text(json.dumps({"projects": []}, indent=4))


def ensure_project_folders(project_id: str):
    project_folder = BASE_DIR / project_id
    literature = project_folder / "literature"
    primary = project_folder / "primary"
    secondary = project_folder / "secondary"

    # Create folder hierarchy
    literature.mkdir(parents=True, exist_ok=True)
    primary.mkdir(parents=True, exist_ok=True)
    secondary.mkdir(parents=True, exist_ok=True)

    return {
        "root": str(project_folder),
        "literature": str(literature),
        "primary": str(primary),
        "secondary": str(secondary)
    }
