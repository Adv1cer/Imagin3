import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

from imagin.db import Base
from imagin import models  # noqa: F401  (registers tables on Base.metadata)

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

x_args = context.get_x_argument(as_dictionary=True)
db_url = x_args.get("db_url") or os.environ["DATABASE_URL"]
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
