"""Discord webhook notifier for Undermine Exchange price alerts.

Sends rich embed messages to a Discord channel when a tracked item
reaches a new all-time-high price.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from discord_webhook import DiscordEmbed, DiscordWebhook

logger = logging.getLogger(__name__)

_BASE_URL = "https://undermine.exchange"


def format_price(copper: int) -> str:
    """Format a copper-denominated price as a human-readable gold string.

    Args:
        copper: The price expressed entirely in copper.

    Returns:
        A formatted string such as ``"123g 45s 67c"``.
    """
    gold = copper // 10_000
    silver = (copper % 10_000) // 100
    remainder = copper % 100
    return f"{gold:,}g {silver}s {remainder}c"


class DiscordNotifier:
    """Sends price-alert embeds to a Discord channel via webhook.

    Args:
        webhook_url: The full Discord webhook URL.
    """

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send_price_alert(
        self,
        item_name: str,
        item_id: int,
        realm: str,
        old_price_copper: int | None,
        new_price_copper: int,
        available: int,
    ) -> None:
        """Send a Discord embed announcing a new highest price.

        Args:
            item_name: Display name of the item.
            item_id: Numeric item identifier.
            realm: Realm slug (e.g. ``"us-dalaran"``).
            old_price_copper: Previous highest price in copper, or ``None``
                if this is the first recorded price.
            new_price_copper: The new highest price in copper.
            available: Current number of auctions available.
        """
        item_url = f"{_BASE_URL}/#{realm}/{item_id}"

        embed = DiscordEmbed(
            title="New Highest Price Alert!",
            description=item_name,
            color="00FF00",
            url=item_url,
        )

        embed.add_embed_field(
            name="Previous High",
            value=format_price(old_price_copper) if old_price_copper else "N/A",
            inline=True,
        )
        embed.add_embed_field(
            name="New High",
            value=format_price(new_price_copper),
            inline=True,
        )

        if old_price_copper and old_price_copper > 0:
            pct_increase = ((new_price_copper - old_price_copper) / old_price_copper) * 100
            embed.add_embed_field(
                name="% Increase",
                value=f"{pct_increase:+.2f}%",
                inline=True,
            )

        embed.add_embed_field(
            name="Available",
            value=str(available),
            inline=True,
        )
        embed.add_embed_field(
            name="Realm",
            value=realm,
            inline=True,
        )

        embed.set_footer(text="Undermine Exchange Monitor")
        embed.set_timestamp(datetime.now(timezone.utc).isoformat())

        webhook = DiscordWebhook(url=self._webhook_url)
        webhook.add_embed(embed)

        try:
            response = webhook.execute()
            if response and hasattr(response, "status_code"):
                if 200 <= response.status_code < 300:
                    logger.info(
                        "Price alert sent for %s (item %d) on %s",
                        item_name,
                        item_id,
                        realm,
                    )
                else:
                    logger.warning(
                        "Discord webhook returned status %d for item %d",
                        response.status_code,
                        item_id,
                    )
            else:
                logger.info(
                    "Price alert dispatched for %s (item %d) on %s",
                    item_name,
                    item_id,
                    realm,
                )
        except Exception:
            logger.exception(
                "Failed to send Discord notification for item %d on %s",
                item_id,
                realm,
            )
