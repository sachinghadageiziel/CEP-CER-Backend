# from sqlalchemy.orm import Session
# from db.models.project_model import Project

# def get_all_projects(db: Session):
#     return db.query(Project).all()


# def get_next_project_id(db: Session):
#     count = db.query(Project).count()
#     return f"PRJ-{count + 1:03d}"


# def create_project(db: Session, project_data: dict):
#     project = Project(**project_data)
#     db.add(project)
#     db.commit()
#     db.refresh(project)
#     return project
