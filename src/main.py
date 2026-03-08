"""Entry point for the Undermine Exchange price monitoring scraper.

Runs a continuous polling loop that scrapes tracked items, detects
new all-time-high prices, records them, and sends Discord alerts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from src.config import AppConfig, load_config
from src.notifier import DiscordNotifier, format_price
from src.scraper import UndermineScraper
from src.storage import PriceStorage

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up root logging based on the ``LOG_LEVEL`` environment variable."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


async def check_items(
    config: AppConfig,
    scraper: UndermineScraper,
    storage: PriceStorage,
    notifier: DiscordNotifier,
) -> None:
    """Iterate over enabled items, scrape prices, and alert on new highs.

    For each enabled item the scraper is invoked with exponential-backoff
    retries.  When a price exceeds the previously recorded highest, a
    Discord notification is dispatched and the price is persisted.

    Args:
        config: The validated application configuration.
        scraper: An initialised (started) scraper instance.
        storage: The price history storage backend.
        notifier: The Discord notifier instance.
    """
    enabled_items = [item for item in config.items if item.enabled]
    logger.info("Checking %d enabled item(s)", len(enabled_items))

    for item in enabled_items:
        result: dict | None = None

        for attempt in range(1, config.scraper.retry_attempts + 1):
            result = await scraper.scrape_item(item.item_id, item.realm)
            if result is not None:
                break

            if attempt < config.scraper.retry_attempts:
                backoff = 2 ** attempt  # 2, 4, 8, ...
                logger.warning(
                    "Scrape attempt %d/%d failed for %s (item %d on %s); "
                    "retrying in %ds",
                    attempt,
                    config.scraper.retry_attempts,
                    item.name,
                    item.item_id,
                    item.realm,
                    backoff,
                )
                await asyncio.sleep(backoff)

        if result is None:
            logger.warning(
                "All %d scrape attempts failed for %s (item %d on %s); skipping",
                config.scraper.retry_attempts,
                item.name,
                item.item_id,
                item.realm,
            )
            continue

        current_price = result["current_price_copper"]
        available = result["available"]
        highest_price = storage.get_highest_price(item.item_id, item.realm)

        if highest_price is None or current_price > highest_price:
            logger.info(
                "New highest price for %s (item %d on %s): %s (was %s)",
                item.name,
                item.item_id,
                item.realm,
                format_price(current_price),
                format_price(highest_price) if highest_price else "N/A",
            )

            notifier.send_price_alert(
                item_name=item.name,
                item_id=item.item_id,
                realm=item.realm,
                old_price_copper=highest_price,
                new_price_copper=current_price,
                available=available,
            )

            storage.record_price(item.item_id, item.realm, current_price)
        else:
            logger.info(
                "Price for %s (item %d on %s) is %s, "
                "below recorded high of %s; no alert",
                item.name,
                item.item_id,
                item.realm,
                format_price(current_price),
                format_price(highest_price),
            )


async def main() -> None:
    """Load configuration and run the polling loop indefinitely."""
    _configure_logging()

    logger.info("Starting Undermine Exchange price monitor")

    config = load_config()
    storage = PriceStorage()
    notifier = DiscordNotifier(webhook_url=config.discord.webhook_url)

    logger.info(
        "Monitoring %d item(s), poll interval: %d minute(s)",
        len([i for i in config.items if i.enabled]),
        config.scraper.poll_interval_minutes,
    )

    async with UndermineScraper(
        timeout_seconds=config.scraper.timeout_seconds
    ) as scraper:
        while True:
            try:
                await check_items(config, scraper, storage, notifier)
            except Exception:
                logger.exception("Unexpected error during check cycle")

            sleep_seconds = config.scraper.poll_interval_minutes * 60
            logger.info("Sleeping for %d seconds until next poll", sleep_seconds)

            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                logger.info("Sleep cancelled; shutting down")
                break

    storage.close()
    logger.info("Undermine Exchange price monitor stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user; exiting")
        sys.exit(0)
