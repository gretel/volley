# Volley

> A volley in tennis is a shot where the ball is struck before it bounces on the ground

Ping responder for MeshCore networks!

## Features

- Responds to "ping" messages on channel and direct messages
- Compact, low-airtime response format
- GPS distance calculation for direct messages
- Telemetry tracking (pings received, pongs sent, max distance)
- Robust error handling for 24/7 operation
- Python 3.14 optimized with modern type hints

## Response Format

**Channel messages:**
```
@[sender] [emoji] HH:MM:SSZ, snr:XdB, hops:N, trace:a1.b2.c3, Xkm
```

**Direct messages:**
```
[emoji] HH:MM:SSZ, snr:XdB, direct, Xkm
```

A random sports ball emoji is selected for each response: 🏉🏀🎾🏈⚽️🎱🥎⚾️🏐

Fields are omitted if unavailable.

## Trigger Words

Responds to messages containing: `ping`, `test`, `pink`, `echo` (case insensitive)

## Telemetry Requests

Send a direct message containing `stats` or `telemetry` to request bot statistics. Only authorized public keys can retrieve telemetry data.

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

# TCP connection
uv run main.py -t 192.168.1.100:4000

# Specify channel (default: 1)
uv run main.py -s /dev/ttyUSB0 -c 1

# Enable verbose logging
uv run main.py -s /dev/ttyUSB0 -v

# Authorize specific public keys for telemetry requests
uv run main.py -s /dev/ttyUSB0 --telemetry-auth 6be9724012b0

# Multiple authorized keys
uv run main.py -s /dev/ttyUSB0 --telemetry-auth 6be9724012b0 --telemetry-auth abc123def456
```

**Telemetry Response Format:**
```
📊 Telemetry: X pings, Y pongs, max dist: Z.Zkm (contact_name)
```

## Requirements

- Python 3.14+
- meshcore>=2.2.5

## License

See LICENSE file.
