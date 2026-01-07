from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from db.database import Base


class LiteratureResult(Base):
    __tablename__ = "literature_results"

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(String, index=True, nullable=False)
    keyword_id = Column(Integer, ForeignKey("literature_keywords.id"), nullable=False)

    pmid = Column(String, index=True, nullable=True)
    title = Column(Text)
    abstract = Column(Text)
    journal = Column(String)
    publication_year = Column(String)
    authors = Column(Text)
    source = Column(String, default="PubMed")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
