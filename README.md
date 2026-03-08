# Undermine Exchange Price Monitor

A Python-based price monitor that watches the [Undermine Exchange](https://undermine.exchange) -- a World of Warcraft auction house tracking site -- for new all-time-high prices on configured items and sends Discord webhook notifications when they occur.

## Features

- **All-time-high detection** -- Tracks the highest recorded price for each item/realm pair and alerts only when a new peak is reached.
- **Discord webhook alerts** -- Sends rich embed notifications with previous high, new high, percentage increase, available quantity, realm, and a direct link to the item page.
- **Configurable watchlist** -- Define items to monitor via a simple YAML configuration file. Each entry can be individually enabled or disabled.
- **Persistent price history** -- Stores every recorded high in a local SQLite database so state survives restarts.
- **Configurable poll interval** -- Defaults to every 15 minutes; adjustable in `config/items.yaml`.
- **Automatic retries with exponential backoff** -- Failed scrape attempts are retried (default: 3 attempts) with increasing delays.
- **Docker-ready** -- Ships with a `Dockerfile` and `docker-compose.yml` for single-command deployment.

## How It Works

The monitor uses [Playwright](https://playwright.dev/python/) with headless Chromium to load Undermine Exchange item pages (which rely on client-side JavaScript rendering). It parses the gold/silver/copper price from the DOM, compares it against the stored historical high in SQLite, and dispatches a Discord webhook embed when a new record price is detected.

## Project Structure

```
Undermine-Scraper/
├── src/
│   ├── __init__.py
│   ├── __main__.py       # Allows running with `python -m src`
│   ├── main.py           # Entry point and polling loop
│   ├── scraper.py        # Playwright: loads pages, parses price data
│   ├── notifier.py       # Discord webhook embed construction and delivery
│   ├── storage.py        # SQLite: tracks highest recorded prices
│   └── config.py         # YAML + Pydantic config loading with env var substitution
├── config/
│   └── items.yaml        # Watchlist and scraper/discord configuration
├── data/                 # SQLite database directory (Docker volume mount)
├── .env.example          # Template for required environment variables
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Prerequisites

- **Python 3.12+**
- **Chromium** (installed automatically via Playwright)
- **A Discord webhook URL** ([how to create one](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks))

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/Undermine-Scraper.git
cd Undermine-Scraper
```

### 2. Configure environment variables

Copy the example env file and set your Discord webhook URL:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
LOG_LEVEL=INFO
```

| Variable | Required | Description |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | Yes | Full Discord webhook URL for price alert delivery |
| `LOG_LEVEL` | No | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |

### 3. Configure items to watch

Edit `config/items.yaml` to add the items you want to monitor. See the [Configuration](#configuration) section below for the full format.

### 4. Run locally

```bash
pip install -r requirements.txt
playwright install chromium
python -m src.main
```

### 5. Run with Docker (recommended)

```bash
docker compose up -d
```

Docker Compose mounts `./config` (read-only) and `./data` (read-write) as volumes, so the SQLite database persists across container restarts and you can edit the watchlist without rebuilding the image.

## Configuration

All configuration lives in `config/items.yaml`. String values support environment variable substitution using `${VAR_NAME}` syntax.

```yaml
# Items to monitor
items:
  - name: "Odd Glob of Wax"       # Display name shown in Discord alerts
    item_id: 242787                # Numeric item ID on Undermine Exchange
    realm: "us-dalaran"            # Realm slug (e.g. "us-dalaran", "eu-ravencrest")
    enabled: true                  # Set to false to skip without removing the entry

  - name: "Another Item"
    item_id: 123456
    realm: "eu-ravencrest"
    enabled: false

# Scraper behaviour
scraper:
  poll_interval_minutes: 15        # How often to check prices (default: 15)
  timeout_seconds: 30              # Max wait for page elements to load (default: 30)
  retry_attempts: 3                # Number of retries per item on failure (default: 3)

# Discord integration
discord:
  webhook_url: "${DISCORD_WEBHOOK_URL}"  # Resolved from environment variable
```

### Finding the item ID and realm slug

Navigate to an item on [undermine.exchange](https://undermine.exchange). The URL hash contains both values:

```
https://undermine.exchange/#us-dalaran/242787
                             ^^^^^^^^^^ ^^^^^^
                             realm slug item ID
```

## Discord Notifications

When a new all-time-high price is detected, the bot sends a rich embed to your configured Discord channel containing:

| Field | Description |
|---|---|
| **Previous High** | The last recorded highest price (gold/silver/copper) |
| **New High** | The newly detected highest price |
| **% Increase** | Percentage change from the previous high |
| **Available** | Number of auctions currently listed |
| **Realm** | The realm being monitored |

The embed title links directly to the item's page on the Undermine Exchange. Prices are displayed in WoW's gold/silver/copper format (e.g., `1,234g 56s 78c`).

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Browser automation | Playwright 1.48 (headless Chromium) |
| Configuration | PyYAML + Pydantic v2 for validation |
| Notifications | discord-webhook |
| Persistence | SQLite (via Python stdlib `sqlite3`) |
| Environment | python-dotenv |
| Deployment | Docker (Playwright official image) |
