from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base


class SecondaryScreening(Base):
    __tablename__ = "secondary_screening"

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

    summary = Column(Text)
    study_type = Column(Text)
    device = Column(Text)
    sample_size = Column(Text)

    appropriate_device = Column(Text)
    appropriate_device_application = Column(Text)
    appropriate_patient_group = Column(Text)
    acceptable_report = Column(Text)

    suitability_score = Column(Integer)
    data_contribution_score = Column(Integer)

    data_source_type = Column(Text)
    outcome_measures = Column(Text)
    follow_up = Column(Text)
    statistical_significance = Column(Text)
    clinical_significance = Column(Text)

    number_of_males = Column(Integer)
    number_of_females = Column(Integer)
    mean_age = Column(String)

    result = Column(String)
    rationale = Column(Text)

    #  ORM relationship
    literature = relationship(
        "Literature",
        back_populates="secondary_screening",
        passive_deletes=True
    )
