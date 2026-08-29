"""SQLAlchemy 2.0 engine, session factory and declarative base."""
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    """SQLite does not enforce foreign keys unless asked."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Add columns that exist in the models but not yet in the database.

    create_all() creates missing TABLES but never alters existing ones, so a
    database made before a column was added keeps working until something
    selects that column and SQLite raises "no such column". There is no
    migration tool here on purpose -- one table needing one nullable column
    does not justify Alembic -- but silently breaking an existing install does
    not either.

    Additive only: never drops or retypes anything, so it cannot lose data. A
    column that needs backfilling still needs doing by hand.
    """
    from sqlalchemy import text

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info('{table.name}')"))
            }
            if not existing:
                continue  # table not created yet; create_all will handle it
            for column in table.columns:
                if column.name in existing or not column.nullable and column.default is None:
                    continue
                ddl = column.type.compile(engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}')
                )


def init_db() -> None:
    """Create all tables. Imported for side effects: models must be registered."""
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
