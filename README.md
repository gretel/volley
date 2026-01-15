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
@[sender] [emoji] HH:MM:SSZ, diff:Xms, snr:XdB, hops:N, trace:a1.b2.c3, Xkm
```

**Direct messages:**
```
[emoji] HH:MM:SSZ, diff:Xms, snr:XdB, direct, Xkm
```

A random sports ball emoji is selected for each response: 🏉🏀🎾🏈⚽️🎱🥎⚾️🏐

Fields are omitted if unavailable (e.g., `diff` requires message timestamp).

## Trigger Words

Responds to messages containing: `ping`, `test`, `pink`, `echo` (case insensitive)

## Installation

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

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
```

## Requirements

- Python 3.14+
- meshcore>=2.2.5

## License

See LICENSE file.
