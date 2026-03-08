"""Allow running the package with ``python -m src``."""

from src.main import main

if __name__ == "__main__":
    import asyncio
    import logging
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Interrupted by user; exiting")
        sys.exit(0)
