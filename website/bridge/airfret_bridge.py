"""Broadcast Raspberry Pi Pico AIRFRET serial events over WebSockets."""

import argparse
import asyncio
import socket
from collections import OrderedDict

import serial
from serial.tools import list_ports
from websockets.asyncio.server import serve


CLIENTS = set()
LATEST_STATE = OrderedDict()
STATE_EVENTS = {
    "READY",
    "MODE",
    "NOTE_FX",
    "SCALE",
    "CHORD",
    "EFFECT_SELECT",
    "VOLUME",
    "GYRO_REVERSE",
}


def available_ports():
    return list(list_ports.comports())


def choose_serial_port(requested_port=None):
    if requested_port:
        return requested_port

    ports = available_ports()
    pico_words = ("pico", "rp2", "cdc", "micropython", "usb serial")
    matches = []

    for port in ports:
        description = " ".join(
            str(value or "")
            for value in (port.device, port.description, port.manufacturer, port.product)
        ).lower()
        if any(word in description for word in pico_words):
            matches.append(port.device)

    if len(matches) == 1:
        return matches[0]

    if not matches and len(ports) == 1:
        return ports[0].device

    port_list = ", ".join(
        f"{port.device} ({port.description})" for port in ports
    ) or "none"

    if len(matches) > 1:
        reason = "More than one possible Pico port was found"
    else:
        reason = "The Pico serial port could not be selected automatically"

    raise RuntimeError(
        f"{reason}. Available ports: {port_list}. "
        "Start again with --port COM5, replacing COM5 with your Pico port."
    )


def local_ip_address():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "YOUR-COMPUTER-IP"
    finally:
        probe.close()


def remember_state(line):
    pieces = line.split("|")
    if len(pieces) >= 2 and pieces[1] in STATE_EVENTS:
        LATEST_STATE[pieces[1]] = line


async def broadcast(line):
    if not CLIENTS:
        return

    client_list = tuple(CLIENTS)
    results = await asyncio.gather(
        *(client.send(line) for client in client_list),
        return_exceptions=True,
    )

    for client, result in zip(client_list, results):
        if isinstance(result, Exception):
            CLIENTS.discard(client)


async def websocket_client(client):
    CLIENTS.add(client)
    address = getattr(client, "remote_address", None)
    print(f"Website connected: {address}")

    try:
        for message in LATEST_STATE.values():
            await client.send(message)
        await client.wait_closed()
    finally:
        CLIENTS.discard(client)
        print(f"Website disconnected: {address}")


async def serial_to_websocket(args):
    while True:
        device = None
        try:
            port_name = choose_serial_port(args.port)
            print(f"Opening Pico on {port_name} at {args.baud} baud…")
            device = serial.Serial(port_name, args.baud, timeout=0.2)
            print("Pico connected. Waiting for AIRFRET events…")

            while True:
                raw_line = await asyncio.to_thread(device.readline)
                if not raw_line:
                    await asyncio.sleep(0.005)
                    continue

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("AIRFRET|"):
                    continue

                print(f"Pico → website: {line}")
                remember_state(line)
                await broadcast(line)

        except (serial.SerialException, OSError, RuntimeError) as error:
            print(f"Pico connection: {error}")
            print("Retrying in 2 seconds. Close Thonny if it still owns the COM port.")
            await asyncio.sleep(2)
        finally:
            if device and device.is_open:
                device.close()


async def run(args):
    network_ip = local_ip_address()
    print("=" * 62)
    print(" TEAM 7 AIRFRET WEBSOCKET BRIDGE")
    print("=" * 62)
    print(f"WebSocket: ws://{network_ip}:{args.ws_port}")
    print(f"Other-computer website: http://{network_ip}:5173/#/visualizer")
    print("Keep this window open during the performance.")
    print()

    async with serve(websocket_client, args.host, args.ws_port):
        await serial_to_websocket(args)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send Pico AIRFRET serial events to browser visualizers."
    )
    parser.add_argument("--port", help="Pico port such as COM5. Auto-detected when omitted.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--ws-port", type=int, default=8765)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\nAirFret bridge stopped.")
