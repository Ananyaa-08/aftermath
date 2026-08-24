import argparse
import signal
import sys
from threading import Event
from types import FrameType

from pydantic import ValidationError

from aftermath.adapters.persistence.database import PostgresProbe
from aftermath.application.health import validate_runtime
from aftermath.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AFTERMATH idle foundation worker; no job execution"
    )
    parser.add_argument(
        "--check", action="store_true", help="Validate configuration and DB, then exit"
    )
    args = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        sys.exit("Invalid configuration; check AFTERMATH_ variables (values suppressed)")
    database = PostgresProbe(settings.database_url.get_secret_value())
    stopped = Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        validate_runtime(database)
        print("Worker ready; foundation idle mode (job execution unimplemented)", flush=True)
        if not args.check:
            stopped.wait()
        print("Worker stopped cleanly", flush=True)
    except RuntimeError as error:
        sys.exit(str(error))
    finally:
        database.close()


if __name__ == "__main__":
    main()
