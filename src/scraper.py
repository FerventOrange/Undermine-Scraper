"""Playwright-based scraper for the Undermine Exchange auction house site.

Navigates to item detail pages rendered via hash-based routing and
extracts current price and availability data from the dynamically
loaded DOM.
"""

from __future__ import annotations

import asyncio
import logging
from types import TracebackType

from playwright.async_api import Page, async_playwright

logger = logging.getLogger(__name__)

_BASE_URL = "https://undermine.exchange"


async def parse_price_element(page: Page, td_element: object) -> int:
    """Extract a copper-denominated price from a table cell element.

    The cell is expected to contain a ``<span class="coins">`` wrapper
    with child spans for ``.gold``, ``.silver``, and ``.copper``.

    Args:
        page: The active Playwright page (used for JS evaluation).
        td_element: An ElementHandle for the ``<td>`` containing the price.

    Returns:
        The total price converted to copper.
    """
    result = await page.evaluate(
        """(td) => {
            const coins = td.querySelector('.coins');
            if (!coins) return { gold: 0, silver: 0, copper: 0 };
            const goldEl = coins.querySelector('.gold');
            const silverEl = coins.querySelector('.silver');
            const copperEl = coins.querySelector('.copper');
            return {
                gold: goldEl ? parseInt(goldEl.textContent.replace(/,/g, ''), 10) || 0 : 0,
                silver: silverEl ? parseInt(silverEl.textContent.replace(/,/g, ''), 10) || 0 : 0,
                copper: copperEl ? parseInt(copperEl.textContent.replace(/,/g, ''), 10) || 0 : 0,
            };
        }""",
        td_element,
    )
    total = result["gold"] * 10_000 + result["silver"] * 100 + result["copper"]
    logger.debug(
        "Parsed price: %dg %ds %dc = %d copper",
        result["gold"],
        result["silver"],
        result["copper"],
        total,
    )
    return total


class UndermineScraper:
    """Async scraper for the Undermine Exchange item detail pages.

    Uses Playwright with headless Chromium to render the JS-heavy site
    and extract pricing information from the DOM.

    Args:
        timeout_seconds: Maximum time to wait for page elements to appear.
    """

    def __init__(self, timeout_seconds: int = 30) -> None:
        self._timeout_ms = timeout_seconds * 1000
        self._playwright: object | None = None
        self._browser: object | None = None
        self._context: object | None = None

    async def start(self) -> None:
        """Launch the headless Chromium browser."""
        logger.info("Starting Playwright browser (headless Chromium)")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        await self._context.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        logger.info("Browser started")

    async def stop(self) -> None:
        """Close the browser and release Playwright resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
            logger.info("Browser closed")
        if self._playwright:
            await self._playwright.stop()
            logger.info("Playwright stopped")
        self._context = None
        self._browser = None
        self._playwright = None

    async def scrape_item(self, item_id: int, realm: str) -> dict | None:
        """Scrape current price and availability for a single item.

        Args:
            item_id: The numeric item identifier on Undermine Exchange.
            realm: The realm slug (e.g. ``"us-dalaran"``).

        Returns:
            A dict with ``current_price_copper`` (int) and ``available``
            (int), or ``None`` if scraping fails.
        """
        url = f"{_BASE_URL}/#{realm}/{item_id}"
        logger.info("Scraping item %d on %s: %s", item_id, realm, url)

        if not self._browser:
            logger.error("Browser not started; call start() first")
            return None

        page: Page | None = None
        try:
            page = await self._context.new_page()
            await page.goto(url, wait_until="domcontentloaded")

            # Wait for the base-stats container to appear, indicating data
            # has been fetched and rendered.
            await page.wait_for_selector(
                ".base-stats", timeout=self._timeout_ms
            )

            # Allow a short grace period for child elements to finish
            # rendering after the container appears.
            await asyncio.sleep(2)

            # --- Extract data from the base-stats table ---
            rows = await page.query_selector_all(".base-stats.framed table tr")

            current_price_copper: int | None = None
            available: int | None = None

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                label = (await page.evaluate("(el) => el.textContent.trim()", cells[0])).strip()

                if label == "Current":
                    current_price_copper = await parse_price_element(page, cells[1])
                elif label == "Available":
                    raw_available = await page.evaluate(
                        "(el) => el.textContent.trim()", cells[1]
                    )
                    # Available is a plain number, strip commas.
                    try:
                        available = int(raw_available.replace(",", ""))
                    except ValueError:
                        logger.warning(
                            "Could not parse availability value: %s",
                            raw_available,
                        )
                        available = 0

            if current_price_copper is None:
                logger.warning(
                    "Could not find 'Current' price row for item %d on %s",
                    item_id,
                    realm,
                )
                return None

            result = {
                "current_price_copper": current_price_copper,
                "available": available if available is not None else 0,
            }
            logger.info(
                "Scraped item %d on %s: price=%d copper, available=%d",
                item_id,
                realm,
                result["current_price_copper"],
                result["available"],
            )
            return result

        except Exception:
            logger.exception(
                "Error scraping item %d on %s", item_id, realm
            )
            return None
        finally:
            if page:
                await page.close()

    # --- Context manager support ---

    async def __aenter__(self) -> UndermineScraper:
        """Enter the async context manager and start the browser."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and stop the browser."""
        await self.stop()
