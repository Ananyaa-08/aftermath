import argparse
import sys

from pydantic import ValidationError

from aftermath.adapters.persistence.database import PostgresProbe
from aftermath.application.health import validate_runtime
from aftermath.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AFTERMATH experiment foundation; no experiments run"
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate environment configuration and database readiness",
    )
    args = parser.parse_args()
    if not args.validate_config:
        parser.print_help()
        return
    try:
        settings = Settings()
    except ValidationError:
        sys.exit("Invalid configuration; check AFTERMATH_ variables (values suppressed)")
    database = PostgresProbe(settings.database_url.get_secret_value())
    try:
        validate_runtime(database)
        print("Configuration and database valid. Experiment execution is not implemented.")
    except RuntimeError as error:
        sys.exit(str(error))
    finally:
        database.close()


if __name__ == "__main__":
    main()
