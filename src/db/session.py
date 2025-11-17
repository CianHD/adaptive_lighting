from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.config import settings

# Convert postgresql:// URL to postgresql+psycopg:// for psycopg3 support
database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Configure engine with suitable settings for SQLite for running tests
engine_kwargs = {"pool_pre_ping": True}

# Create a config suitable for PostgreSQL for production/development
if not database_url.startswith("sqlite"):
    engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
    engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW

engine = create_engine(database_url, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    """
    Database dependency for FastAPI endpoints.
    
    Creates a new SQLAlchemy database session for each request and
    ensures it's properly closed after the request completes.
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
