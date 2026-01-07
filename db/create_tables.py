
from db.database import engine, Base

#  IMPORT ALL MODELS HERE (VERY IMPORTANT)
from db.models.project_model import Project
from db.models.literature_keywords_model import LiteratureKeyword
from db.models.literature_results_model import LiteratureRecord


def create_tables():
    Base.metadata.create_all(bind=engine)
    print(" All tables created successfully")


if __name__ == "__main__":
    create_tables()

