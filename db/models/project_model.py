from sqlalchemy import Column, Integer, String, Date, Text, LargeBinary
from sqlalchemy.orm import relationship
from db.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)

    owner = Column(String, nullable=False) 

    start_date = Column(Date)
    end_date = Column(Date)

    status = Column(String, default="Active")

    primary_criteria = Column(Text)
    secondary_criteria = Column(Text)

    # IFU (single source of truth)
    ifu_file_data = Column(LargeBinary, nullable=True)
    ifu_file_name = Column(String, nullable=True)
    ifu_content_type = Column(String, nullable=True)

    #  ORM relationships
    literature = relationship(
        "Literature",
        back_populates="project",
        cascade="all, delete-orphan"
    )

    # primary_screenings = relationship(
    #     "PrimaryScreening",
    #     cascade="all, delete-orphan"
    # )

    # secondary_screenings = relationship(
    #     "SecondaryScreening",
    #     cascade="all, delete-orphan"
    # )
