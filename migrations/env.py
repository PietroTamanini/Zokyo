from logging.config import fileConfig

from flask import current_app
from alembic import context

config = context.config
fileConfig(config.config_file_name)

target_db = current_app.extensions["migrate"].db
target_metadata = target_db.metadata


def get_engine():
    try:
        return target_db.get_engine()
    except TypeError:
        return target_db.engine


def get_url():
    return str(get_engine().url).replace("%", "%%")


config.set_main_option("sqlalchemy.url", get_url())


def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
