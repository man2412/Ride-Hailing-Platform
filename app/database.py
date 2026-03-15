#sqlalchemy is library for interacting with databases using ob
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

#async engine — the object that talks to the database and manages a connection pool.
engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    echo=(settings.env == "development"),
)

#factory that creates sessions, each session represents a single database transaction
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False, #don't expire the session after the transaction is committed, keep the session open for the next transaction
    autoflush=False, #don't flush the session after each commit, wait until the session is closed
    autocommit=False,
)

#Base class for all models, provides metadata for the models
class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
