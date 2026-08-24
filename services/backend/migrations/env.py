from alembic import context
from sqlalchemy import create_engine

from aftermath.config import Settings

# No URL in alembic.ini and no logging of configuration or SQL parameters.
url = Settings().database_url.get_secret_value()
if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
