"""
Alembic environment.

Wired to the application rather than to alembic.ini: the URL comes from
`app.db.session.get_database_url()` so migrations and the running app can never
disagree about which database they mean, and the metadata comes from the models
so autogenerate stays honest.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# `alembic` runs from backend/, but not necessarily with backend/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import get_database_url  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Env wins over the ini placeholder — one resolution path, shared with the app.
config.set_main_option("sqlalchemy.url", get_database_url())


def include_object(obj, name, type_, reflected, compare_to):
    """Keep Alembic's hands off tables it does not own.

    Keycloak has its own database here, but a shared one is a common
    deployment; without this filter an autogenerate run there would cheerfully
    propose dropping every Keycloak table.
    """
    if type_ == "table" and name.startswith(("keycloak_", "kc_")):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # pgvector must exist before a migration references the vector type.
        # Doing it here means `alembic upgrade head` works on a bare database.
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
