import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database connection URL from environment or fallback to postgresql local default
DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    "postgresql://postgres:postgres@localhost:5432/spec_driven_dev"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ConfigModel(Base):
    __tablename__ = "configs"
    
    key = Column(String(100), primary_key=True, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SpecAnalysisModel(Base):
    __tablename__ = "spec_analyses"
    
    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(50))  # "text", "pdf", "url"
    source_path = Column(String(500))
    raw_content = Column(Text)
    analyzed_stories = Column(JSON)  # List of user stories with acceptance criteria
    created_at = Column(DateTime, default=datetime.utcnow)

class JobModel(Base):
    __tablename__ = "jobs"
    
    id = Column(String(100), primary_key=True, index=True)  # UUID or custom job ID
    status = Column(String(50), default="PENDING")  # PENDING, RUNNING, SUCCESS, FAILED
    tickets = Column(JSON)  # List of tickets included in the job
    logs = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db():
    """Initializes tables in the database."""
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for retrieving database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
