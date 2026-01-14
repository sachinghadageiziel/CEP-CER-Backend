from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from db.database import Base


class PdfDownloadStatus(Base):
    __tablename__ = "pdf_download_status"

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

    pmcid = Column(String, index=True)
    pdf_url = Column(Text)

    status = Column(
        String,
        nullable=False,
        default="pending"  # pending | downloaded | not_found | failed
    )

    file_path = Column(Text)
    error_message = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    literature = relationship(
        "Literature",
        backref="pdf_download_status",
        lazy="joined"
    )
