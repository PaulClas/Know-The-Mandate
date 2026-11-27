from sqlalchemy import create_engine, pool

from alembic import context
from kym import config, db

target_metadata = db.Base.metadata


def run_migrations_online() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or config.DATABASE_URL
    config.ensure_dirs()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
