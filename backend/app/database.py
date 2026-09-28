import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# We default to DATABASE_URL if available, otherwise test with SQLite fallback
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/agentflow")

from sqlalchemy import create_engine, event

try:
    if "sqlite" in SQLALCHEMY_DATABASE_URL:
        engine = create_engine(
            SQLALCHEMY_DATABASE_URL,
            connect_args={"check_same_thread": False, "timeout": 30}
        )
    else:
        # Try creating engine with short timeout to detect if Postgres is alive
        engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            pass
except Exception:
    # Fallback to local SQLite database when Postgres is not running
    SQLALCHEMY_DATABASE_URL = "sqlite:///./agentflow.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 30}
    )

# Optimize SQLite for multi-threaded concurrency and eliminate lock timeouts
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        try:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
        except Exception:
            pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

