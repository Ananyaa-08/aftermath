from aftermath.ports.interfaces import DatabaseProbe


def readiness(database: DatabaseProbe) -> bool:
    return database.ready()


def validate_runtime(database: DatabaseProbe) -> None:
    if not readiness(database):
        raise RuntimeError("Database unavailable, pgvector missing, or migrations not current")
