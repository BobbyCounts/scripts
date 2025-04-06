import argparse
import asyncio
import logging

from bleak import BleakClient, BleakScanner, uuids
from bleak.backends.characteristic import BleakGATTCharacteristic

UUID_ESS = 0x181a
UUID_CUD = 0x2901



def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    """Simple notification handler which prints the data received."""
    print(f"{characteristic.description} {data}")


async def main(args: argparse.Namespace):
    print("starting scan...")

    if args.address:
        device = await BleakScanner.find_device_by_address(
            args.address, cb=dict(use_bdaddr=args.macos_use_bdaddr)
        )
        if device is None:
            print("could not find device with address '%s'", args.address)
            return
    else:
        device = await BleakScanner.find_device_by_name(
            args.name, cb=dict(use_bdaddr=args.macos_use_bdaddr)
        )
        if device is None:
            print("could not find device with name '%s'", args.name)
            return

    print("connecting to device...")

    async with BleakClient(
        device,
        services=args.services,
    ) as client:
        print("connected")
        # Find the ESS Service
        for service in client.services:
            # print(service.uuid)
            if(service.uuid == uuids.normalize_uuid_16(UUID_ESS)):
                print("Found ESS Service")
                for char in service.characteristics:
                    type = char.description
                    user_label_descriptor = char.get_descriptor(uuids.normalize_uuid_16(UUID_CUD))
                    user_label = "None"
                    notify = False
                    if(user_label_descriptor):
                       user_label = await client.read_gatt_descriptor(user_label_descriptor.handle)
                       user_label = user_label.decode('utf-8')

                    # Enable notification
                    if("notify" in char.properties):
                        notify = True
                        await client.start_notify(char.handle, notification_handler)
                    print(f"Found Characteristic Type: {type} | with user description: {user_label} | Notify: {notify}")
        
        await asyncio.sleep(30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    device_group = parser.add_mutually_exclusive_group(required=True)

    device_group.add_argument(
        "--name",
        metavar="<name>",
        help="the name of the bluetooth device to connect to",
    )
    device_group.add_argument(
        "--address",
        metavar="<address>",
        help="the address of the bluetooth device to connect to",
    )
    parser.add_argument(
        "--services",
        nargs="+",
        metavar="<uuid>",
        help="if provided, only enumerate matching service(s)",
    )

    parser.add_argument(
        "--macos-use-bdaddr",
        action="store_true",
        help="when true use Bluetooth address instead of UUID on macOS",
    )
    args = parser.parse_args()

    asyncio.run(main(args))
