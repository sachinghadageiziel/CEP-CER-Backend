from sqlalchemy import (
    Column, Integer, String, Text, Boolean,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from db.database import Base


class Literature(Base):
    __tablename__ = "literature"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(String, nullable=False)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    keyword_id = Column(Integer)
    source = Column(String, nullable=False)

    title = Column(Text)
    abstract = Column(Text)
    journal = Column(String)
    publication_year = Column(Integer)
    author = Column(Text)
    publication_type = Column(String)
    doi = Column(String)
    article_url = Column(String)

    is_unique = Column(Boolean, default=True)

    # __table_args__ = (
    #     UniqueConstraint("project_id", "article_id", name="uq_project_article"),
    # )

    #  ORM relationships
    project = relationship(
        "Project",
        back_populates="literature"
    )

    primary_screening = relationship(
        "PrimaryScreening",
        uselist=False,
        back_populates="literature",
        cascade="all, delete-orphan"
    )

    secondary_screening = relationship(
        "SecondaryScreening",
        uselist=False,
        back_populates="literature",
        cascade="all, delete-orphan"
    )
