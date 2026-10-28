from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


class PostgresProbe:
    def __init__(self, url: str):
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
            pool_timeout=3,
            hide_parameters=True,
        )

    def ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SET LOCAL statement_timeout = '3000ms'"))
                return bool(
                    connection.execute(
                        text("""
                    SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')
                    AND EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '0006')
                    AND to_regclass('public.workspaces') IS NOT NULL
                    AND to_regclass('public.jobs') IS NOT NULL
                    AND to_regclass('public.document_versions') IS NOT NULL
                    AND to_regclass('public.timeline_alignment_edges') IS NOT NULL
                """)
                    ).scalar_one()
                )
        except SQLAlchemyError:
            return False

    def close(self) -> None:
        self.engine.dispose()
