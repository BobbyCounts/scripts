# Wenet BLE Scripts
Scripts for recieving BLE sensor data and forwarding to a Wenet Telemetry UDP listener for downlinking.

## Raspberry Pi3/Zero Instructions
The RPi 3 and RPi Zero only have two uarts, the second (miniuart) being much weaker than the primary. By default, the BLE chip uses the primary UART. For the Wenet modeum to work a full speed, the miniuart should be assigned to BLE so Wenet can use the primary UART.

Add to config.txt in bootfs
```
dtoverlay=disable-bt
core_freq=250
```
