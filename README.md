# Volley

> A volley in tennis is a shot where the ball is struck before it bounces on the ground

Ping responder for MeshCore networks!

## Features

- Responds to "ping" messages on channel and direct messages
- Zipcode distance calculation (5-digit German zipcodes)
- Phone prefix distance calculation (German phone area codes)
- Compact, low-airtime response format
- GPS distance calculation for direct messages
- Statistics tracking (pings received, pongs sent, max distance)
- Auto-reconnect on connection loss for 24/7 operation
- Rate limiting to prevent abuse
- Offline operation with local database
- Python 3.14 optimized with modern type hints

## Response Format

**Channel messages:**
```
@[sender] [emoji] HH:MM:SSZ, snr:XdB, rssi:XdBm, hops:N, route:a1.b2.c3, Xkm
```

**Direct messages:**
```
[emoji] HH:MM:SSZ, snr:XdB, rssi:XdBm, direct, Xkm
```

Fields are omitted if unavailable.

## Configuration

The bot's behavior can be customized by editing constants in `main.py`:

```python
# Rate limiting
RATE_LIMIT_REQUESTS = 3      # Max requests per window
RATE_LIMIT_WINDOW = 360      # Window duration in seconds (6 minutes)

# Response emojis (randomly selected)
RESPONSE_EMOJIS = ['🏉', '🏀', '🎾', '🏈', '⚽️', '🎱', '🥎', '⚾️', '🏐']

# Trigger words for ping responses (case insensitive)
TRIGGER_WORDS = ["ping", "test", "pink", "echo"]

# Optional repeater for path injection (set via --via-repeater flag)
PREFERRED_REPEATER_KEY = None  # Public key prefix of nearby repeater
```

## Trigger Words

Responds to messages starting with: `ping`, `test`, `pink`, `echo` (case insensitive)

Note: Trigger words must appear at the beginning of the message to avoid responding to bot replies or messages that merely mention these words.

## Distance Calculation

The bot supports two types of location-based distance calculations:

### Zipcode Lookup

Send a 5-digit German zipcode (e.g., `22765`, `10115`) to calculate approximate distance from the bot's location.

Example:
- Send `22765` → Bot responds with distance to Hamburg, Germany
- Works for both channel and direct messages
- Uses offline database with pgeocode for fast, reliable lookups

### Phone Prefix Lookup

Send a German phone area code (e.g., `0241`, `030`) to calculate distance to that region.

Example:
- Send `0241` → Bot responds with distance to Aachen
- Send `040` → Bot responds with distance to Hamburg
- Works for both channel and direct messages
- Automatically resolves prefix to zipcode and calculates distance

## Rate Limiting

To prevent abuse, each sender is limited to 3 ping requests per 6-minute window. Requests exceeding this limit are silently ignored.

## Installation

```bash
# Install uv if not already installed
# Option 1: Using the standalone installer
curl -LsSf https://astral.sh/uv/install.sh | sh

# Option 2: Using Homebrew (macOS/Linux)
brew install uv

# Option 3: Using apt (Debian/Ubuntu)
sudo apt update && sudo apt install -y uv

# Install dependencies
uv sync
```

## Usage

```bash
# Serial connection
uv run main.py -s /dev/ttyUSB0

# TCP connection (default port: 5000)
uv run main.py -t 192.168.1.100:5000

# Specify channel (default: 1)
uv run main.py -s /dev/ttyUSB0 -c 1

# Enable verbose logging
uv run main.py -s /dev/ttyUSB0 -v

# Route via nearby repeater (path injection + tracking)
uv run main.py -s /dev/ttyUSB0 --via-repeater bd
```

## Repeater Mode

When running near a repeater, use `--via-repeater KEY` to enable:

1. **Path Injection**: All responses are routed through the specified repeater for better reliability
2. **Route Tracking**: Responses show `via:` instead of `route:` when messages came through your repeater

Example: `--via-repeater bd` (where `bd` is your repeater's public key prefix)

This improves delivery success rate and helps track network topology.

## Requirements

- Python 3.14+
- meshcore>=2.2.5
- pgeocode>=0.5.0 (for zipcode coordinate lookup)
- zipcodes.db (included, for phone prefix lookup)

## Data Sources

- **Zipcode coordinates**: [pgeocode](https://pypi.org/project/pgeocode/) - Offline geocoding library
- **German zipcodes & phone prefixes**: [German-Zip-Codes.csv](https://gist.github.com/jbspeakr/4565964) by [@jbspeakr](https://github.com/jbspeakr)

## Building the Database

The `zipcodes.db` file is included in the repository. To rebuild it from the CSV:

```bash
python3 convert_csv_to_db.py
```

This will convert `German-Zip-Codes.csv` to `zipcodes.db` with proper indexing for fast lookups.

## License

See LICENSE file.
