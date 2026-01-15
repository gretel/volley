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
import signal
import sys
from datetime import datetime, timezone
from typing import Any

from meshcore import MeshCore, EventType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("volley")

# Shutdown event for graceful termination
shutdown_event = asyncio.Event()

# Global state for tracking latest SNR and path info
latest_snr: float | None = None
latest_path_info: dict[str, Any] = {}

# Telemetry tracking
telemetry = {
    "pings_received": 0,
    "pongs_sent": 0,
    "max_distance_km": 0.0,
    "max_distance_contact": None,
}


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


def format_compact_path(path_nodes: list[str]) -> str:
    """Format path nodes compactly with colon separators.

    Example: ['a1', 'b2', 'c3'] -> 'a1:b2:c3'
    """
    if not path_nodes:
        return ""
    return ":".join(path_nodes)


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
                       distance_km: float | None = None, time_diff_ms: int | None = None) -> str:
    """Build compact pong response message.

    Format (channel): @[sender] 🏐 HH:MM:SSZ, snr:XdB, hops:N, trace:a1.b2.c3
    Format (direct): 🏐 HH:MM:SSZ, snr:XdB, direct
    Omits fields that are unavailable.
    Special case: 255 hops means "direct" (no routing).
    """
    # Build the main parts (everything after @mention)
    parts = []

    # Randomly select a sports ball emoji
    emoji = random.choice(['🏉', '🏀', '🎾', '🏈', '⚽️', '🎱', '🥎', '⚾️', '🏐'])

    # Add emoji with space and timestamp
    now = datetime.now(timezone.utc)
    time_str = now.strftime("%H:%M:%SZ")
    parts.append(f"{emoji} {time_str}")

    # Add time difference if available
    if time_diff_ms is not None:
        parts.append(f"diff:{time_diff_ms}ms")

    # Add SNR if available
    if snr is not None:
        parts.append(f"snr:{snr:.0f}dB")

    # Add hop count if available
    # 255 hops is a special value meaning "direct" (no routing)
    if path_len is not None:
        if path_len == 255:
            parts.append("direct")
        else:
            parts.append(f"hops:{path_len}")

    # Add path if available (but not for direct messages)
    # Use dots instead of colons for trace
    if path_nodes and path_len != 255:
        path_str = ".".join(path_nodes)
        if path_str:
            parts.append(f"trace:{path_str}")

    # Add distance if available
    if distance_km is not None:
        # Format distance compactly
        if distance_km < 1:
            # Less than 1km, show in meters
            parts.append(f"{int(distance_km * 1000)}m")
        elif distance_km < 10:
            # Less than 10km, show with 1 decimal
            parts.append(f"{distance_km:.1f}km")
        else:
            # 10km or more, show as integer
            parts.append(f"{int(distance_km)}km")

    # Build final message with @mention in square brackets (MeshCore format)
    message = ", ".join(parts)
    if not is_direct:
        message = f"@[{sender}] {message}"

    return message


async def run_bot(args, device_lat: float, device_lon: float, meshcore: MeshCore):
    """Run the bot event loop with error handling."""
    global latest_snr, latest_path_info

    async def handle_rx_log_data(event):
        """Track SNR and path info from RX_LOG_DATA events."""
        try:
            global latest_snr, latest_path_info

            rx = event.payload or {}

            # Extract SNR if available
            if "snr" in rx:
                latest_snr = rx["snr"]

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
            global latest_snr, latest_path_info, telemetry

            msg = event.payload or {}
            text = msg.get("text", "")

            # Extract sender from message
            # Channel format: "sender: message"
            # Direct message: use pubkey_prefix
            if is_channel:
                sender = "unknown"
                if ":" in text:
                    sender = text.split(":", 1)[0].strip()
                chan = msg.get("channel_idx")
                logger.info(f"Channel {chan} message from {sender}: {text}")
            else:
                sender = msg.get("pubkey_prefix", "unknown")
                logger.info(f"Direct message from {sender}: {text}")

            # Check if this is a ping message (ping, test, pink, echo)
            text_lower = text.lower()
            if not any(trigger in text_lower for trigger in ["ping", "test", "pink", "echo"]):
                logger.debug("Not a trigger message, ignoring")
                return

            if is_channel:
                logger.info(f"Ping detected from {sender} on channel {chan}")
            else:
                logger.info(f"Ping detected from {sender} (direct message)")

            # Track ping received
            telemetry["pings_received"] += 1

            # Gather available data
            # Try to get SNR from message payload first, fallback to RX_LOG_DATA
            snr = msg.get("snr") if msg.get("snr") is not None else latest_snr

            # Calculate time difference if message has timestamp
            time_diff_ms = None
            msg_timestamp = msg.get("timestamp")
            if msg_timestamp:
                try:
                    # Message timestamp is in seconds, convert to milliseconds
                    now_ms = datetime.now(timezone.utc).timestamp() * 1000
                    msg_ms = msg_timestamp * 1000
                    time_diff_ms = int(now_ms - msg_ms)
                except (ValueError, TypeError):
                    pass

            # Get path info from latest RX_LOG_DATA or message payload
            path_len = msg.get("path_len")
            path_nodes = None

            if path_len is None and latest_path_info:
                path_len = latest_path_info.get("path_len")

            if latest_path_info.get("path_nodes"):
                path_nodes = latest_path_info["path_nodes"]

            # Calculate distance if we have location data
            distance_km = None
            if not is_channel:
                # For direct messages, try to get sender's location from contacts
                pubkey_prefix = msg.get("pubkey_prefix")
                if pubkey_prefix:
                    contact = meshcore.get_contact_by_key_prefix(pubkey_prefix)
                    if contact:
                        sender_lat = contact.get("adv_lat", 0.0)
                        sender_lon = contact.get("adv_lon", 0.0)
                        distance_km = calculate_distance(device_lat, device_lon, sender_lat, sender_lon)

                        # Track max distance
                        if distance_km is not None and distance_km > telemetry["max_distance_km"]:
                            telemetry["max_distance_km"] = distance_km
                            telemetry["max_distance_contact"] = contact.get("adv_name", sender)

            # Build compact response
            reply = build_pong_message(sender, snr, path_len, path_nodes,
                                       is_direct=not is_channel, distance_km=distance_km,
                                       time_diff_ms=time_diff_ms)

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
                telemetry["pongs_sent"] += 1

                # Log telemetry periodically
                if telemetry["pongs_sent"] % 10 == 0:
                    logger.info(f"Telemetry: {telemetry['pings_received']} pings, "
                               f"{telemetry['pongs_sent']} pongs sent, "
                               f"max distance: {telemetry['max_distance_km']:.1f}km "
                               f"({telemetry['max_distance_contact'] or 'N/A'})")

            # Reset tracked data after use
            latest_snr = None
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

    try:
        # Run until shutdown signal
        logger.info("Bot is running. Press Ctrl+C to stop.")
        await shutdown_event.wait()
    finally:
        # Cleanup subscriptions
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

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Connect to MeshCore device
    meshcore = None
    try:
        if args.serial:
            logger.info(f"Connecting to serial port: {args.serial}")
            meshcore = await MeshCore.create_serial(args.serial, debug=args.verbose)
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
            meshcore = await MeshCore.create_tcp(host, port, debug=args.verbose)
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
        # Print final telemetry
        logger.info("=" * 50)
        logger.info("Final Telemetry:")
        logger.info(f"  Pings received: {telemetry['pings_received']}")
        logger.info(f"  Pongs sent: {telemetry['pongs_sent']}")
        if telemetry['max_distance_km'] > 0:
            logger.info(f"  Max distance: {telemetry['max_distance_km']:.1f}km "
                       f"({telemetry['max_distance_contact'] or 'N/A'})")
        logger.info("=" * 50)

        # Cleanup
        await meshcore.stop_auto_message_fetching()
        await meshcore.disconnect()
        logger.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
