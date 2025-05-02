import argparse
import asyncio
import signal
import sys
import struct

import bleak
from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic

UUID_CUD = 0x2901

# UUIDs to filter on
WENET_SERVICE_UUID = "fb63feb8-31ad-451d-a587-9fc20f9c8add"
service_uuids = [WENET_SERVICE_UUID]

WENET_SENSOR_CHAR = "3d235f0e-61f8-4455-89c6-2f7d73c33178"

device_queue = asyncio.Queue(50)
scanner_event = asyncio.Event()

def signal_handler(sig, frame):
    print('Got CTRL-C, cleaning up and shutting down...')
    sys.exit(0)

last_value = 0
def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    global last_value
    sequence_num = struct.unpack('<ch4s', data)[1] 
    if(last_value == 0):
       last_value = sequence_num
    else:
        if(sequence_num != (last_value + 1)):
            print("Sequence error")
        last_value = sequence_num
    # print(sequence_num)

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

async def main(args: argparse.Namespace):
    tasks = []
    tasks.append(asyncio.create_task(scanner()))
    tasks.append(asyncio.create_task(connect_device()))
    tasks.append(asyncio.create_task(connect_device()))
    tasks.append(asyncio.create_task(connect_device()))
    await asyncio.gather(*(tasks))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    asyncio.run(main(args))
