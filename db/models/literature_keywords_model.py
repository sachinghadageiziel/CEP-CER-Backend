from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from db.database import Base


class LiteratureKeyword(Base):
    __tablename__ = "literature_keywords"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(String, index=True)

    keyword_no = Column(String)
    keyword = Column(String)
    filters = Column(String)
    date_range = Column(String)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
