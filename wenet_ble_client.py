import argparse
import asyncio
import signal
import sys
import struct
import json
import datetime
import wenet_ble_udp as udp

import bleak
from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic

# UUIDs to filter on
WENET_SERVICE_UUID = "fb63feb8-31ad-451d-a587-9fc20f9c8add"
service_uuids = [WENET_SERVICE_UUID]
WENET_SENSOR_CHAR = "3d235f0e-61f8-4455-89c6-2f7d73c33178"

# Queue for packets to send to the UDP server after processing into a JSON frame
packet_queue = asyncio.Queue(50)
# Queue for JSON packets to send to the UDP server
json_queue = asyncio.Queue(50)
# Queue for devices found by the scanner
device_queue = asyncio.Queue(50)
# Event to signal when the scanner has found a device
scanner_event = asyncio.Event()

def build_wenet_single_packet(data: bytearray):
    # Total size: 23 bytes
    header = data[0:3]
    payload = data[3:].ljust(16, b'\xff')
    cur_time = datetime.datetime.now(datetime.timezone.utc)
    cur_time = cur_time.hour * 3600 + cur_time.minute * 60 + (cur_time.microsecond // 1000)
    cur_time = struct.pack('<I', cur_time)
    return header + cur_time + payload

def decode_packet(data: bytearray):
    header = '<BH'
    payload_len = len(data) - struct.calcsize(header)
    struct_format = f"{header}{payload_len}s"
    payload_id, sequence_num, payload = struct.unpack(struct_format, data)
    return f"{payload_id}, {sequence_num}, {payload}\n".encode()

def signal_handler(sig, frame):
    print('Got CTRL-C, cleaning up and shutting down...')
    sys.exit(0)

last_value = 0
def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    global last_value
    sequence_num = struct.unpack('<BH4s', data)[1]
    packet_queue.put_nowait(build_wenet_single_packet(data))
    if(last_value == 0):
       last_value = sequence_num
    else:
        if(sequence_num != (last_value + 1)):
            print("Sequence error")
        last_value = sequence_num
    # print(decode_packet(data))

async def scanner():
    while True:
        async with BleakScanner() as scanner:
            print("Scanner started...")
            async for (device, adv_data) in scanner.advertisement_data():
                scanner_event.clear()
                if(adv_data.rssi < -100):
                    continue
                if(WENET_SERVICE_UUID in adv_data.service_uuids):
                    print(f"Found {device}, rssi: {adv_data.rssi}")
                    device_queue.put_nowait(device)
                    break
        print("Scanner stopped")
        await scanner_event.wait()

async def connect_device():
    event = asyncio.Event()
    def disconnected(client):
        print(f"Disconnected {client}")
        event.set()
    while True:
        event.clear()
        device = await device_queue.get()
        await asyncio.sleep(1)
        print(f"Connecting to {device}")
        try:
            async with BleakClient(device, timeout=10, disconnected_callback=disconnected) as client:
                print("Connected")
                await client.start_notify(WENET_SENSOR_CHAR, notification_handler)
                scanner_event.set()
                await event.wait()
        except(TimeoutError):
            print("Timed out connecting")
        except(bleak.exc.BleakError):
            print("Bleak error")
        finally:
            scanner_event.set()

async def process_json(timeout):
    while True:
        payload = bytearray()
        try:
            async with asyncio.timeout(timeout):
                for i in range(11):
                    payload = payload + await packet_queue.get()
        except asyncio.TimeoutError:
            # Timeout, send whatever we have
            if(len(payload) == 0):
                # Got nothing, go back to waiting
                continue

        assert(len(payload) % 23 == 0)
        # Calculate the number of packets
        num_packets = len(payload) // 23

        # Build the binary payload
        payload = payload.ljust(253, b'\x00')
        assert(len(payload) == 253)
        binary_payload = struct.pack('>B', num_packets) + payload
        assert(len(binary_payload) == 254)

        # Send the payload to the UDP server
        json_frame = json.dumps({'type': 'WENET_TX_SEC_PAYLOAD', 'id': 55, 'repeats': 1, 'packet': list(binary_payload)})
        json_queue.put_nowait(json_frame.encode())
        
async def main(args: argparse.Namespace):
    tasks = []
    tasks.append(asyncio.create_task(scanner()))
    tasks.append(asyncio.create_task(connect_device()))
    tasks.append(asyncio.create_task(connect_device()))
    tasks.append(asyncio.create_task(connect_device()))
    tasks.append(asyncio.create_task(process_json(5)))
    tasks.append(asyncio.create_task(udp.run_client(json_queue, 8888)))
    await asyncio.gather(*(tasks))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    asyncio.run(main(args))
