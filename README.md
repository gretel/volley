# Volley

> A volley in tennis is a shot where the ball is struck before it bounces on the ground

Ping responder for MeshCore networks!

## Features

- Responds to "ping" messages on channel and direct messages
- Compact, low-airtime response format
- GPS distance calculation for direct messages
- Statistics tracking (pings received, pongs sent, max distance)
- Auto-reconnect on connection loss for 24/7 operation
- Rate limiting to prevent abuse
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
```

## Trigger Words

Responds to messages containing: `ping`, `test`, `pink`, `echo` (case insensitive)

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
```

## Requirements

- Python 3.14+
- meshcore>=2.2.5

## License

See LICENSE file.
