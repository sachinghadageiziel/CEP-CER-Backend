from pydantic import BaseModel
from datetime import date
from typing import Optional


class ProjectCreate(BaseModel):
    title: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
