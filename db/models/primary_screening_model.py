from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base


class PrimaryScreening(Base):
    __tablename__ = "primary_screening"

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True
    )

    literature_id = Column(
        Integer,
        ForeignKey("literature.id", ondelete="CASCADE"),
        primary_key=True
    )

    decision = Column(String, nullable=False)
    exclusion_criteria = Column(Text)
    rationale = Column(Text)

    #  ORM relationship
    literature = relationship(
        "Literature",
        back_populates="primary_screening"
    )
