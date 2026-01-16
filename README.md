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
@[sender] [emoji] HH:MM:SSZ,snr:X.XdB,rssi:X.XdBm,hops:N,route:a1.b2.c3,dist:Xkm
```

**Direct messages:**
```
[emoji] HH:MM:SSZ,snr:X.XdB,rssi:X.XdBm,direct,dist:Xkm
```

**Info request (info/help/?):**

On channel:
```
Volley! Send: ріng/zipcode/prefix https://github.com/gretel/volley
```
(Note: Uses Cyrillic 'і' in ріng to avoid triggering other bots)

On direct message:
```
Volley! Send: ping, zipcode (22767), or prefix (040). https://github.com/gretel/volley 73 DO2THX
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

# Optional repeater for route tracking (set via --via-repeater flag)
PREFERRED_REPEATER_KEY = None  # Public key prefix of nearby repeater
```

## Trigger Words

**Ping responses:** `ping`, `test`, `pink`, `echo` (case insensitive)

**Info responses:** `info`, `help`, `?` (case insensitive)

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

### Option 1: Using uv (recommended)

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### Option 2: Using pip

```bash
# Create virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
# For Linux/OpenBSD/FreeBSD:
pip install -r requirements-linux.txt

# For macOS:
pip install -r requirements.txt
```

## Usage

```bash
# Serial connection
python3 main.py -s /dev/ttyUSB0
# Or with uv: uv run main.py -s /dev/ttyUSB0

# TCP connection (default port: 5000)
python3 main.py -t 192.168.1.100:5000

# Specify channel (default: 1)
python3 main.py -s /dev/ttyUSB0 -c 1

# Enable verbose logging
python3 main.py -s /dev/ttyUSB0 -v

# Track routes via nearby repeater
python3 main.py -s /dev/ttyUSB0 -r bd
# Or: python3 main.py -s /dev/ttyUSB0 --via-repeater bd
```

## Repeater Mode

When running near a repeater, use `-r KEY` (or `--via-repeater KEY`) to enable route tracking:

**Route Tracking**: Responses show `via:` instead of `route:` when messages came through your repeater

Example: `-r bd` or `--via-repeater bd` (where `bd` is your repeater's public key prefix)

This helps track network topology and understand how messages are being routed.

## Requirements

- Python 3.14+
- meshcore>=2.2.5
- zipcodes.db (included - 1MB SQLite database with coordinates)

**No heavy dependencies!** Unlike other geocoding solutions, volley uses a pre-built database with coordinates, eliminating the need for numpy/pandas (72MB+ of dependencies).

**Platform notes:**
- macOS: Includes pyobjc for Bluetooth support
- Linux/BSD: No pyobjc needed (use `requirements-linux.txt`)

## Data Sources

- **German zipcodes & phone prefixes**: [German-Zip-Codes.csv](https://gist.github.com/jbspeakr/4565964) by [@jbspeakr](https://github.com/jbspeakr)
- **Coordinates**: Pre-computed using [pgeocode](https://pypi.org/project/pgeocode/) and stored in SQLite database

## Building the Database

The `zipcodes.db` file (with coordinates) is included in the repository. To rebuild from scratch:

```bash
# Step 1: Convert CSV to SQLite
python3 convert_csv_to_db.py

# Step 2: Add coordinates (requires pgeocode temporarily)
pip install pgeocode  # Temporary: only needed for building
python3 add_coordinates.py
pip uninstall -y pgeocode numpy pandas  # Clean up heavy dependencies
```

The final database is only ~1MB and contains everything needed for offline lookups.

## License

See LICENSE file.
