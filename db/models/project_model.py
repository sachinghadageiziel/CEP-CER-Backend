from sqlalchemy import Column, String, Text
from db.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    duration = Column(String)
    description = Column(Text)
    owner = Column(String)
    status = Column(String, default="Active")
