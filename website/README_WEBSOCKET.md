# Team 7 AirFret — network visualizer

This version sends the Pico's `AIRFRET|...` messages through a Python WebSocket bridge. The Pico and bridge run on the instrument computer. Any browser on the same Wi-Fi can open the live visualizer.

## Signal path

`Pico -> USB serial -> Python bridge -> Wi-Fi WebSocket -> browser visualizer`

The bridge sends control events only. Audio remains on the AirFret speaker.

## Files to copy into the existing Vite project

Copy these into the matching locations in `part3frequencies`:

- `src/App.jsx`
- `src/App.css`
- `src/index.css`
- the complete `src/components` folder
- `package.json`
- `vite.config.js`
- the complete `bridge` folder
- `setup_bridge.bat`, `start_bridge.bat`, and `start_website.bat`

Keep the existing `src/assets` folder unchanged.

## One-time setup

1. Copy `pico/main.py` to the Raspberry Pi Pico using Thonny. Save it on the Pico as `main.py`.
2. Run it once in Thonny and confirm the Shell prints an `AIRFRET|...` line.
3. Close Thonny completely; Thonny and the bridge cannot use the same COM port simultaneously.
4. In the project folder, double-click `setup_bridge.bat`.
5. In a terminal in the project folder, run `npm install`.
6. If Windows asks about firewall access for Python or Node.js, allow access on **Private networks**.

## Start a performance

On the computer connected to the Pico:

1. Double-click `start_bridge.bat`.
2. Double-click `start_website.bat`.
3. Keep both windows open.
4. The bridge window prints a link similar to `http://192.168.1.25:5173/#/visualizer`.

On the second computer:

1. Join the same Wi-Fi network.
2. Open the exact `http://192.168...:5173/#/visualizer` address printed by the bridge.
3. Click **Connect live signal**.

## If the bridge cannot find the Pico

Check the Pico's COM number in Windows Device Manager or Thonny. Then run, replacing `COM5` with the actual port:

```bat
start_bridge.bat --port COM5
```

## Common fixes

- **COM port access denied:** close Thonny and every Serial Monitor, then restart the bridge.
- **Second computer cannot open the website:** confirm both computers are on the same non-guest Wi-Fi and allow Node.js through the Windows firewall on Private networks.
- **Website opens but will not connect:** allow Python through the firewall and confirm the bridge window says it is listening on port `8765`.
- **Pico code stops after unplugging:** make sure the updated code is saved to the Pico itself as `main.py`, not only on the computer.
- **Different network or internet connection:** this local setup does not expose the instrument publicly. Use a trusted VPN such as Tailscale or deploy a secure `wss://` relay before using it across the internet.
