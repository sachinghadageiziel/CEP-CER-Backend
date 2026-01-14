from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --------------------------------------
# DATABASE CONFIG
# --------------------------------------
# Update password if different
DATABASE_URL = "postgresql+psycopg2://postgres:root@localhost:5432/cepcer"

# Engine
engine = create_engine(
    DATABASE_URL,
    echo=True,           # shows SQL queries in terminal
    future=True          # SQLAlchemy 2.x mode
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True
)

# Base class for models
Base = declarative_base()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()