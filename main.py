#!/usr/bin/env python3
"""
Volley - KISS style ping responder for low airtime usage.

Responds to messages containing 'ping' on a specified channel with compact
information: sender, time (UTC), SNR, hop count, and abbreviated path.
"""
import asyncio
import argparse
import logging
import math
import random
import re
import signal
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meshcore import MeshCore, EventType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("volley")

# Shutdown event for graceful termination
shutdown_event = asyncio.Event()

# Global state for tracking latest SNR, RSSI and path info
latest_snr: float | None = None
latest_rssi: float | None = None
latest_path_info: dict[str, Any] = {}

# Statistics tracking
stats = {
    "pings_received": 0,
    "pongs_sent": 0,
    "max_distance_km": 0.0,
    "max_distance_contact": None,
}

# Rate limiting: track timestamps of requests per public key
# Key: pubkey_prefix, Value: list of request timestamps (unix time)
rate_limit_tracker: dict[str, list[float]] = {}

# ============================================================================
# Configuration Constants
# ============================================================================

# Rate limiting configuration
RATE_LIMIT_REQUESTS = 3  # Maximum number of requests
RATE_LIMIT_WINDOW = 360  # Time window in seconds (6 minutes)

# Response emoji pool (randomly selected for each response)
RESPONSE_EMOJIS = ['🏉', '🏀', '🎾', '🏈', '⚽️', '🎱', '🥎', '⚾️', '🏐']

# Trigger words that activate ping responses (case insensitive)
TRIGGER_WORDS = ["ping", "test", "pink", "echo"]

# Info trigger words that return bot information
INFO_WORDS = ["info", "help", "?"]

# Zipcode pattern for distance calculation (5 digits for German zipcodes)
ZIPCODE_PATTERN = r"^\d{5}$"

# Phone prefix pattern (3-5 digits starting with 0)
PREFIX_PATTERN = r"^0\d{2,4}$"

# Database path for zipcode/prefix lookups
DB_PATH = Path(__file__).parent / "zipcodes.db"

# Optional repeater configuration (set via command line or leave None)
# When configured, responses will be routed via this repeater for better reliability
PREFERRED_REPEATER_KEY: str | None = None  # Set to repeater's public key prefix


def parse_rx_log_data(payload: Any) -> dict[str, Any]:
    """Parse RX_LOG event payload to extract LoRa packet details.

    Expected format (hex):
      byte0: header
      byte1: path_len
      next path_len bytes: path nodes
      next byte: channel_hash (optional)
    """
    result: dict[str, Any] = {}

    try:
        hex_str = None

        if isinstance(payload, dict):
            hex_str = payload.get("payload") or payload.get("raw_hex")
        elif isinstance(payload, (str, bytes)):
            hex_str = payload

        if not hex_str:
            return result

        if isinstance(hex_str, bytes):
            hex_str = hex_str.hex()

        hex_str = str(hex_str).lower().replace(" ", "").replace("\n", "").replace("\r", "")

        if len(hex_str) < 4:
            return result

        result["header"] = hex_str[0:2]

        try:
            path_len = int(hex_str[2:4], 16)
            result["path_len"] = path_len
        except ValueError:
            return {}

        path_start = 4
        path_end = path_start + (path_len * 2)

        if len(hex_str) < path_end:
            return {}

        path_hex = hex_str[path_start:path_end]
        result["path"] = path_hex
        result["path_nodes"] = [path_hex[i:i + 2] for i in range(0, len(path_hex), 2)]

        if len(hex_str) >= path_end + 2:
            result["channel_hash"] = hex_str[path_end:path_end + 2]

    except Exception as ex:
        logger.debug(f"Error parsing RX_LOG data: {ex}")

    return result


def zipcode_to_coords(zipcode: str) -> tuple[float, float] | None:
    """Convert German zipcode to coordinates using local database.

    Returns (latitude, longitude) or None if lookup fails.
    Uses offline SQLite database with pre-computed coordinates.
    """
    try:
        if not DB_PATH.exists():
            logger.warning(f"Database not found: {DB_PATH}")
            return None

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Look up coordinates in database
        cursor.execute(
            "SELECT latitude, longitude FROM zipcodes WHERE zipcode = ?",
            (zipcode,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            lat, lon = result
            if lat is not None and lon is not None:
                logger.debug(f"Zipcode {zipcode} -> coords: {lat:.4f}, {lon:.4f}")
                return (float(lat), float(lon))

        logger.debug(f"No coordinates found for zipcode {zipcode}")
        return None
    except Exception as e:
        logger.debug(f"Error looking up zipcode {zipcode}: {e}")
        return None


def prefix_to_zipcode(prefix: str) -> tuple[str, str] | None:
    """Convert phone prefix to zipcode and city name using local database.

    Returns (zipcode, city) or None if lookup fails.
    If multiple cities have the same prefix, returns the first one.
    """
    try:
        if not DB_PATH.exists():
            logger.warning(f"Database not found: {DB_PATH}")
            return None

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Look up prefix in database (get first result)
        cursor.execute(
            "SELECT zipcode, city FROM zipcodes WHERE prefix = ? LIMIT 1",
            (prefix,)
        )
        result = cursor.fetchone()
        conn.close()

        if result:
            zipcode, city = result
            logger.debug(f"Prefix {prefix} -> {city} ({zipcode})")
            return (zipcode, city)

        logger.debug(f"No zipcode found for prefix {prefix}")
        return None
    except Exception as e:
        logger.debug(f"Error looking up prefix {prefix}: {e}")
        return None


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    """Calculate great-circle distance between two GPS coordinates in kilometers.

    Uses the haversine formula.
    Returns None if coordinates are invalid (0, 0).
    """
    # Check if either coordinate is (0, 0) - typically means no GPS data
    if (lat1 == 0 and lon1 == 0) or (lat2 == 0 and lon2 == 0):
        return None

    # Earth's radius in kilometers
    R = 6371.0

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (math.sin(dLat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(dLon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return distance


def build_pong_message(sender: str, snr: float | None, path_len: int | None,
                       path_nodes: list[str] | None, is_direct: bool = False,
                       distance_km: float | None = None, rssi: float | None = None,
                       via_repeater: bool = False) -> str:
    """Build compact pong response message.

    Format (channel): @[sender] 🏐 HH:MM:SSZ,snr:X.XdB,rssi:X.XdBm,hops:N,route:a1.b2.c3
    Format (direct): 🏐 HH:MM:SSZ,snr:X.XdB,rssi:X.XdBm,direct
    Omits fields that are unavailable.
    Special case: 255 hops means "direct" (no routing).
    """
    # Build the main parts (everything after @mention)
    parts = []

    # Randomly select a sports ball emoji
    emoji = random.choice(RESPONSE_EMOJIS)

    # Add emoji with space and timestamp
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M:%SZ")
    parts.append(f"{emoji} {time_str}")

    # Add SNR if available
    if snr is not None:
        parts.append(f"snr:{snr:.1f}dB")

    # Add RSSI if available
    if rssi is not None:
        parts.append(f"rssi:{rssi:.1f}dBm")

    # Add hop count if available
    # 255 hops is a special value meaning "direct" (no routing)
    if path_len is not None:
        if path_len == 255:
            parts.append("direct")
        else:
            parts.append(f"hops:{path_len}")

    # Add path if available (but not for direct messages)
    # Use dots instead of colons for route
    if path_nodes and path_len != 255:
        path_str = ".".join(path_nodes)
        if path_str:
            # Check if message came via configured repeater
            route_label = "route"
            if via_repeater and PREFERRED_REPEATER_KEY:
                # Check if repeater is in the path
                if PREFERRED_REPEATER_KEY in path_nodes:
                    route_label = "via"
            parts.append(f"{route_label}:{path_str}")

    # Add distance if available
    if distance_km is not None:
        # Format distance compactly with dist: prefix
        if distance_km < 1:
            # Less than 1km, show in meters
            parts.append(f"dist:{int(distance_km * 1000)}m")
        elif distance_km < 10:
            # Less than 10km, show with 1 decimal
            parts.append(f"dist:{distance_km:.1f}km")
        else:
            # 10km or more, show as integer
            parts.append(f"dist:{int(distance_km)}km")

    # Build final message with @mention in square brackets (MeshCore format)
    message = ",".join(parts)
    if not is_direct:
        message = f"@[{sender}] {message}"

    return message


async def run_bot(args, device_lat: float, device_lon: float, meshcore: MeshCore):
    """Run the bot event loop with error handling."""
    global latest_snr, latest_rssi, latest_path_info, rate_limit_tracker

    async def handle_connected(event):
        """Handle connection events."""
        info = event.payload or {}
        if info.get('reconnected'):
            logger.info("🔄 Reconnected to device")
        else:
            logger.info("✅ Connected to device")

    async def handle_disconnected(event):
        """Handle disconnection events."""
        info = event.payload or {}
        reason = info.get('reason', 'unknown')
        logger.warning(f"❌ Disconnected: {reason}")
        if info.get('max_attempts_exceeded'):
            logger.error("⚠️  Max reconnection attempts exceeded")

    async def handle_rx_log_data(event):
        """Track SNR, RSSI and path info from RX_LOG_DATA events."""
        try:
            global latest_snr, latest_rssi, latest_path_info

            rx = event.payload or {}

            # Extract SNR if available
            if "snr" in rx:
                latest_snr = rx["snr"]

            # Extract RSSI if available
            if "rssi" in rx:
                latest_rssi = rx["rssi"]

            # Parse path information
            raw = rx.get("payload")
            if raw:
                parsed = parse_rx_log_data(raw)
                if parsed:
                    latest_path_info = parsed
        except Exception as e:
            logger.error(f"Error handling RX_LOG_DATA: {e}", exc_info=args.verbose)

    async def handle_ping_message(event, is_channel=True):
        """Handle incoming messages (channel or direct) and respond to pings."""
        try:
            global latest_snr, latest_rssi, latest_path_info, stats

            msg = event.payload or {}
            text = msg.get("text", "")

            # Debug: log the full message to see what fields are available
            logger.debug(f"Message payload keys: {list(msg.keys())}")
            if "snr" in msg:
                logger.debug(f"Message has SNR: {msg['snr']}")
            if "rssi" in msg:
                logger.debug(f"Message has RSSI: {msg['rssi']}")

            # Extract sender from message
            # Channel format: "sender: message"
            # Direct message: use pubkey_prefix
            if is_channel:
                sender = "unknown"
                if ":" in text:
                    sender = text.split(":", 1)[0].strip()
                chan = msg.get("channel_idx")
                logger.debug(f"Channel {chan} message from {sender}: {text}")
            else:
                sender = msg.get("pubkey_prefix", "unknown")
                logger.debug(f"Direct message from {sender}: {text}")

            # Check if this is a ping message (trigger words must be at start)
            # For channel messages, check after the "sender: " prefix
            check_text = text
            if is_channel and ":" in text:
                # Skip the "sender: " prefix for channel messages
                check_text = text.split(":", 1)[1].strip()

            text_lower = check_text.lower()

            # Check if this is an info request
            is_info = any(text_lower.startswith(info_word) for info_word in INFO_WORDS)

            if is_info:
                # Send info response with usage instructions
                info_reply = "Volley ping bot. Send: ping, zipcode (22767), or prefix (040). https://github.com/gretel/volley 73 DO2THX"
                logger.info(f"Info request from {sender}")

                if is_channel:
                    await meshcore.commands.send_chan_msg(chan, info_reply)
                else:
                    pubkey_prefix = msg.get("pubkey_prefix")
                    if pubkey_prefix:
                        contact = meshcore.get_contact_by_key_prefix(pubkey_prefix)
                        if contact:
                            await meshcore.commands.send_msg(contact, info_reply)
                return

            # Check if message is a zipcode (5 digits)
            is_zipcode = re.match(ZIPCODE_PATTERN, check_text.strip())

            # Check if message is a phone prefix (0XXXX or 0XXX)
            is_prefix = re.match(PREFIX_PATTERN, check_text.strip())

            # Check if message starts with any trigger word
            if not any(text_lower.startswith(trigger) for trigger in TRIGGER_WORDS) and not is_zipcode and not is_prefix:
                logger.debug("Not a trigger message, zipcode, or phone prefix, ignoring")
                return

            # Rate limiting check
            now = datetime.now(timezone.utc).timestamp()
            requester_key = sender if is_channel else msg.get("pubkey_prefix", sender)

            # Initialize tracker for this key if needed
            if requester_key not in rate_limit_tracker:
                rate_limit_tracker[requester_key] = []

            # Remove timestamps older than the rate limit window
            rate_limit_tracker[requester_key] = [
                ts for ts in rate_limit_tracker[requester_key]
                if now - ts < RATE_LIMIT_WINDOW
            ]

            # Check if rate limit exceeded
            if len(rate_limit_tracker[requester_key]) >= RATE_LIMIT_REQUESTS:
                logger.info(f"Rate limit exceeded for {requester_key}, ignoring ping")
                return

            # Add current request to tracker
            rate_limit_tracker[requester_key].append(now)

            if is_zipcode:
                zipcode = check_text.strip()
                logger.info(f"Zipcode ping {zipcode} from {sender}" + (f" on channel {chan}" if is_channel else " (direct message)"))
            elif is_prefix:
                prefix = check_text.strip()
                logger.info(f"Phone prefix ping {prefix} from {sender}" + (f" on channel {chan}" if is_channel else " (direct message)"))
            else:
                if is_channel:
                    logger.info(f"Ping detected from {sender} on channel {chan}")
                else:
                    logger.info(f"Ping detected from {sender} (direct message)")

            # Track ping received
            stats["pings_received"] += 1

            # Gather available data
            # Try to get SNR from message payload first, fallback to RX_LOG_DATA
            snr = msg.get("snr") if msg.get("snr") is not None else latest_snr

            # Try to get RSSI from message payload first, fallback to RX_LOG_DATA
            rssi = msg.get("rssi") if msg.get("rssi") is not None else latest_rssi

            # Get path info from latest RX_LOG_DATA or message payload
            path_len = msg.get("path_len")
            path_nodes = None
            via_repeater = False

            logger.debug(f"Message path_len: {path_len}, latest_path_info: {latest_path_info}")

            if path_len is None and latest_path_info:
                path_len = latest_path_info.get("path_len")

            if latest_path_info and latest_path_info.get("path_nodes"):
                path_nodes = latest_path_info["path_nodes"]
                logger.debug(f"Path nodes: {path_nodes}")
                # Check if message came via configured repeater
                if PREFERRED_REPEATER_KEY and PREFERRED_REPEATER_KEY in path_nodes:
                    via_repeater = True
                    logger.debug(f"Message came via repeater {PREFERRED_REPEATER_KEY}")

            # Calculate distance if we have location data
            distance_km = None

            # Try zipcode-based distance first
            if is_zipcode:
                zipcode = check_text.strip()
                coords = zipcode_to_coords(zipcode)
                if coords:
                    zip_lat, zip_lon = coords
                    distance_km = calculate_distance(device_lat, device_lon, zip_lat, zip_lon)
                    if distance_km is not None:
                        logger.info(f"Zipcode {zipcode} distance: {distance_km:.1f}km")
                        # Track max distance
                        if distance_km > stats["max_distance_km"]:
                            stats["max_distance_km"] = distance_km
                            stats["max_distance_contact"] = f"{sender} (zip:{zipcode})"
            # Try phone prefix-based distance
            elif is_prefix:
                prefix = check_text.strip()
                result = prefix_to_zipcode(prefix)
                if result:
                    zipcode, city = result
                    coords = zipcode_to_coords(zipcode)
                    if coords:
                        zip_lat, zip_lon = coords
                        distance_km = calculate_distance(device_lat, device_lon, zip_lat, zip_lon)
                        if distance_km is not None:
                            logger.info(f"Prefix {prefix} ({city}) distance: {distance_km:.1f}km")
                            # Track max distance
                            if distance_km > stats["max_distance_km"]:
                                stats["max_distance_km"] = distance_km
                                stats["max_distance_contact"] = f"{sender} (prefix:{prefix}, {city})"
            elif not is_channel:
                # For direct messages, try to get sender's location from contacts
                pubkey_prefix = msg.get("pubkey_prefix")
                if pubkey_prefix:
                    contact = meshcore.get_contact_by_key_prefix(pubkey_prefix)
                    if contact:
                        sender_lat = contact.get("adv_lat", 0.0)
                        sender_lon = contact.get("adv_lon", 0.0)
                        distance_km = calculate_distance(device_lat, device_lon, sender_lat, sender_lon)

                        # Track max distance
                        if distance_km is not None and distance_km > stats["max_distance_km"]:
                            stats["max_distance_km"] = distance_km
                            stats["max_distance_contact"] = contact.get("adv_name", sender)

            # Build compact response
            reply = build_pong_message(sender, snr, path_len, path_nodes,
                                       is_direct=not is_channel, distance_km=distance_km,
                                       rssi=rssi, via_repeater=via_repeater)

            logger.info(f"Sending pong: {reply}")

            # Send response (channel or direct)
            if is_channel:
                result = await meshcore.commands.send_chan_msg(chan, reply)
            else:
                # For direct messages, reply to the sender
                pubkey_prefix = msg.get("pubkey_prefix")
                if pubkey_prefix:
                    # Try to find contact by prefix
                    contact = meshcore.get_contact_by_key_prefix(pubkey_prefix)
                    if contact:
                        result = await meshcore.commands.send_msg(contact, reply)
                    else:
                        # Contact not found, fetch contacts and try again
                        logger.debug(f"Contact not found for {pubkey_prefix}, refreshing contacts")
                        contacts_result = await meshcore.commands.get_contacts()
                        if contacts_result.type != EventType.ERROR:
                            # Try to find contact again after refresh
                            contact = meshcore.get_contact_by_key_prefix(pubkey_prefix)
                            if contact:
                                result = await meshcore.commands.send_msg(contact, reply)
                            else:
                                logger.error(f"Could not find contact for {pubkey_prefix} even after refresh")
                                return
                        else:
                            logger.error(f"Failed to get contacts: {contacts_result.payload}")
                            return
                else:
                    logger.error("No pubkey_prefix in direct message")
                    return

            if result.type == EventType.ERROR:
                logger.error(f"Failed to send pong: {result.payload}")
            else:
                logger.info("Pong sent successfully")
                stats["pongs_sent"] += 1

                # Log stats periodically
                if stats["pongs_sent"] % 10 == 0:
                    logger.info(f"Stats: {stats['pings_received']} pings, "
                               f"{stats['pongs_sent']} pongs sent, "
                               f"max distance: {stats['max_distance_km']:.1f}km "
                               f"({stats['max_distance_contact'] or 'N/A'})")

            # Don't reset SNR/RSSI - let them be overwritten by new RX_LOG_DATA events
            # Only reset path info as it's message-specific
            latest_path_info = {}
        except Exception as e:
            logger.error(f"Error handling ping message: {e}", exc_info=args.verbose)

    async def handle_channel_message(event):
        """Handle incoming channel messages."""
        await handle_ping_message(event, is_channel=True)

    async def handle_direct_message(event):
        """Handle incoming direct messages."""
        await handle_ping_message(event, is_channel=False)

    async def handle_new_contact(event):
        """Log when new contacts are discovered."""
        contact = event.payload or {}
        pubkey = contact.get("public_key", "unknown")
        name = contact.get("adv_name", "unknown")
        logger.debug(f"New contact discovered: {name} ({pubkey[:12]}...)")

    # Debug handlers
    async def handle_all_channel_messages(event):
        msg = event.payload or {}
        logger.debug(f"ANY channel message: channel_idx={msg.get('channel_idx')}, text={msg.get('text')}")

    async def handle_all_direct_messages(event):
        msg = event.payload or {}
        logger.debug(f"ANY direct message: pubkey_prefix={msg.get('pubkey_prefix')}, text={msg.get('text')}")

    # Subscribe to events
    sub_connected = meshcore.subscribe(EventType.CONNECTED, handle_connected)
    sub_disconnected = meshcore.subscribe(EventType.DISCONNECTED, handle_disconnected)
    sub_rx = meshcore.subscribe(EventType.RX_LOG_DATA, handle_rx_log_data)
    sub_chan = meshcore.subscribe(
        EventType.CHANNEL_MSG_RECV,
        handle_channel_message,
        attribute_filters={"channel_idx": args.channel}
    )
    sub_direct = meshcore.subscribe(EventType.CONTACT_MSG_RECV, handle_direct_message)
    sub_new_contact = meshcore.subscribe(EventType.NEW_CONTACT, handle_new_contact)
    sub_all_chan = meshcore.subscribe(EventType.CHANNEL_MSG_RECV, handle_all_channel_messages)
    sub_all_direct = meshcore.subscribe(EventType.CONTACT_MSG_RECV, handle_all_direct_messages)

    # Setup signal handlers for graceful shutdown
    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Periodic connection check task
    async def connection_watchdog():
        """Periodically check connection status and log state changes."""
        last_connected = meshcore.is_connected
        while not shutdown_event.is_set():
            try:
                await asyncio.sleep(5)  # Check every 5 seconds
                current_connected = meshcore.is_connected
                if last_connected != current_connected:
                    if current_connected:
                        logger.info("🔗 Connection restored")
                    else:
                        logger.warning("🔌 Connection lost, waiting for reconnect...")
                    last_connected = current_connected
            except Exception as e:
                logger.error(f"Error in connection watchdog: {e}")

    try:
        # Run connection watchdog in background
        watchdog_task = asyncio.create_task(connection_watchdog())

        # Run until shutdown signal
        logger.info("Bot is running. Press Ctrl+C to stop.")
        await shutdown_event.wait()

        # Cancel watchdog
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
    finally:
        # Cleanup subscriptions
        meshcore.unsubscribe(sub_connected)
        meshcore.unsubscribe(sub_disconnected)
        meshcore.unsubscribe(sub_rx)
        meshcore.unsubscribe(sub_chan)
        meshcore.unsubscribe(sub_direct)
        meshcore.unsubscribe(sub_new_contact)
        meshcore.unsubscribe(sub_all_chan)
        meshcore.unsubscribe(sub_all_direct)


async def main():
    """Main entry point for volley."""
    parser = argparse.ArgumentParser(
        description="Volley - Compact ping responder for low airtime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -s /dev/ttyUSB0
  %(prog)s -s /dev/ttyUSB0 -c 1
  %(prog)s -t 192.168.1.100:4000
  %(prog)s -t 10.0.0.5:4000 -c 0 -v
        """
    )

    conn_group = parser.add_mutually_exclusive_group(required=True)
    conn_group.add_argument(
        "-s", "--serial",
        metavar="PORT",
        help="Serial port (e.g., /dev/ttyUSB0, COM4)"
    )
    conn_group.add_argument(
        "-t", "--tcp",
        metavar="HOST:PORT",
        help="TCP connection (e.g., 192.168.1.100:4000)"
    )

    parser.add_argument(
        "-c", "--channel",
        type=int,
        default=1,
        metavar="IDX",
        help="Channel index to monitor (default: 1)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )

    parser.add_argument(
        "-r", "--via-repeater",
        metavar="KEY",
        help="Track messages via repeater (public key prefix). Shows 'via:' when messages route through this repeater."
    )

    args = parser.parse_args()

    # Set meshcore logger to WARNING by default to reduce noise
    logging.getLogger("meshcore").setLevel(logging.WARNING)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logging.getLogger("meshcore").setLevel(logging.DEBUG)

    # Configure repeater if specified
    global PREFERRED_REPEATER_KEY
    if args.via_repeater:
        PREFERRED_REPEATER_KEY = args.via_repeater
        logger.info(f"Repeater mode enabled: routing via {PREFERRED_REPEATER_KEY}")

    # Check if database exists
    if not DB_PATH.exists():
        logger.warning(f"Database not found: {DB_PATH}")
        logger.warning("Zipcode/prefix lookups will be disabled")
    else:
        logger.info(f"✅ Database ready: {DB_PATH}")

    # Connect to MeshCore device with auto-reconnect
    meshcore = None
    try:
        if args.serial:
            logger.info(f"Connecting to serial port: {args.serial}")
            meshcore = await MeshCore.create_serial(
                args.serial,
                debug=args.verbose,
                auto_reconnect=True,
                max_reconnect_attempts=sys.maxsize
            )
            logger.info(f"Connected via serial on {args.serial}")
        else:
            # Parse TCP host:port
            try:
                host, port = args.tcp.rsplit(":", 1)
                port = int(port)
            except ValueError:
                logger.error(f"Invalid TCP format: {args.tcp}. Expected HOST:PORT")
                sys.exit(1)

            logger.info(f"Connecting to TCP: {host}:{port}")
            meshcore = await MeshCore.create_tcp(
                host, port,
                debug=args.verbose,
                auto_reconnect=True,
                max_reconnect_attempts=sys.maxsize
            )
            logger.info(f"Connected via TCP to {host}:{port}")

    except Exception as e:
        logger.error(f"Failed to connect: {e}")
        sys.exit(1)

    # Get device info for debugging and location
    device_info = await meshcore.commands.send_appstart()
    device_lat = 0.0
    device_lon = 0.0
    if device_info.type != EventType.ERROR:
        payload = device_info.payload
        device_name = payload.get("adv_name", "unknown")
        pubkey = payload.get("public_key", "unknown")
        device_lat = payload.get("adv_lat", 0.0)
        device_lon = payload.get("adv_lon", 0.0)
        logger.info(f"Device: {device_name}")
        logger.info(f"Public key: {pubkey}")
        if device_lat != 0.0 or device_lon != 0.0:
            logger.info(f"Location: {device_lat:.6f}, {device_lon:.6f}")

    # Start auto-fetching messages
    await meshcore.start_auto_message_fetching()
    logger.info(f"Listening for 'ping' on channel {args.channel} and direct messages")

    try:
        # Run bot event loop
        await run_bot(args, device_lat, device_lon, meshcore)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        # Print final stats
        logger.info("=" * 50)
        logger.info("Final Statistics:")
        logger.info(f"  Pings received: {stats['pings_received']}")
        logger.info(f"  Pongs sent: {stats['pongs_sent']}")
        if stats['max_distance_km'] > 0:
            logger.info(f"  Max distance: {stats['max_distance_km']:.1f}km "
                       f"({stats['max_distance_contact'] or 'N/A'})")
        logger.info("=" * 50)

        # Cleanup
        await meshcore.stop_auto_message_fetching()
        await meshcore.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
