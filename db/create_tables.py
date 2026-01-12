from db.database import engine, Base

from db.models.user_model import User
from db.models.project_model import Project
from db.models.project_user_model import ProjectUser
from db.models.literature_model import Literature
from db.models.primary_screening_model import PrimaryScreening
from db.models.secondary_screening_model import SecondaryScreening  # ✅ ADD THIS


def create_tables():
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully")


if __name__ == "__main__":
    create_tables()
