# rTest v0.1
# Standalone Reticulum RNode Range Test System


**Reticulum Range Testing Tool with GPS Mapping**

A comprehensive range testing suite for Reticulum/LoRa networks with real-time GPS logging, signal quality tracking (RSSI/SNR), and interactive map visualization.

![Version](https://img.shields.io/badge/version-0.1-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.7+-blue)

## Features

- 📡 **Real-time Range Testing** - Continuous ping/pong testing with RTT measurement
- 🗺️ **GPS Tracking** - Automatic GPS logging via Termux API (Android) or system GPS
- 📊 **Signal Quality** - RSSI and SNR tracking from Reticulum packets
- 🌍 **Multiple Export Formats** - CSV, JSON, GeoJSON, KML, HTML
- 🛣️ **Path Visualization** - Interactive maps with path lines showing your route
- ⚙️ **JSON Configuration** - Easy customization via config files
- 🔄 **Auto-Announce** - Periodic announces to maintain network paths
- 📱 **Mobile Optimized** - Perfect for Termux on Android

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/fr33n0w/rtest.git
cd rtest

# Install Reticulum if not present
pip install rns

# For Termux (Android) - install GPS support
pkg install termux-api
```

### Basic Usage

**1. Start the base station (Raspberry Pi / PC Other // Fixed location):**
```bash
python rtest_server.py
```

Copy the server hash from the output.

**2. Start the mobile client (Android / Termux // Moving vehicle):**
```bash
# Export all formats to Downloads
python range_test_gps.py <server_hash> --exp all

# Or just HTML map
python range_test_gps.py <server_hash> --export html
```

**3. Drive around and test coverage!**

The client will:
- Ping the server every at choosen interva seconds from the config .json
- Record GPS position, RTT, RSSI, SNR
- Generate map files showing coverage
- Draw a path line showing your route

## Files

### Core Scripts

- **`rtest_gps.py`** - GPS-enabled client with full export capabilities
- **`rtest_server.py`** - Base station server with logging
- **`rtest_client.py`** - Simple client without GPS


### Configuration Files

Created automatically on first run:

**`client_config.json`:**
```json
{
  "display_name": "RangeTest-Mobile",
  "announce_interval": 180,
  "ping_interval": 5,
  "ping_delay": 0,
  "ping_timeout": 10,
  "path_establishment_wait": 10,
  "pre_ping_delay": 3,
  "base_station_hash": "your_server_hash_here",
  "log_file": "range_test.json"
}
```

**`server_config.json`:**
```json
{
  "display_name": "RangeTest-BaseStation",
  "announce_interval": 180,
  "log_file": "range_test_server.json"
}
```

## Configuration Options

### Client Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `display_name` | RangeTest-Mobile | Network display name |
| `announce_interval` | 180 | Seconds between announces (helps maintain path) |
| `ping_interval` | 5 | Seconds between pings |
| `ping_delay` | 0 | Extra delay after pong (rate limiting) |
| `ping_timeout` | 10 | Seconds to wait for pong |
| `path_establishment_wait` | 10 | Max seconds to wait for server path |
| `pre_ping_delay` | 3 | Delay before starting (path stabilization) |
| `base_station_hash` | - | Server destination hash |

### Server Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `display_name` | RangeTest-BaseStation | Network display name |
| `announce_interval` | 180 | Seconds between announces |

## Export Formats

All exports are written **incrementally** to the `export/` folder and only include entries with valid GPS data.

### CSV Export
**File:** `export/range_test.csv`

Columns: Ping, RTT_ms, Timestamp, Latitude, Longitude, Altitude, Accuracy, Speed, Bearing, RSSI_dBm, SNR_dB

Perfect for Excel analysis and custom visualizations.

### JSON Export
**File:** `export/range_test.json`

Complete data in JSON format with all fields preserved.

### GeoJSON Export
**File:** `export/range_test.geojson`

Standard GeoJSON format - upload to [geojson.io](https://geojson.io) or any GIS software.

### KML Export
**File:** `export/range_test.kml`

Google Earth compatible with:
- Color-coded markers (green/yellow/red by RTT)
- Path line showing route
- RSSI/SNR in descriptions
- Clickable placemarks with details

### HTML Map
**File:** `export/range_test.html`

Interactive Leaflet/OpenStreetMap with:
- Live path visualization
- Color-coded markers
- Click for details (RTT, RSSI, SNR, GPS)
- Signal quality legend
- Works offline once loaded

## How It Works

### Network Protocol

**App Name:** `rt` (Reticulum Transport)

**Ping Packet (Client → Server):**
```json
{
  "ping": 5,
  "from": "client_hash_hex"
}
```

**Pong Packet (Server → Client):**
```json
{
  "pong": 5
}
```

### Data Flow

1. **Path Establishment** - Client waits for server path (up to 10s)
2. **Auto-Announce** - Both announce every 3 minutes to maintain paths
3. **Ping/Pong** - Client sends ping, server replies
4. **GPS Recording** - Each successful pong with GPS is logged
5. **Signal Extraction** - RSSI/SNR extracted from Reticulum packet
6. **Incremental Export** - Files update after each GPS entry

### Signal Quality Indicators

**RTT-based (Round Trip Time):**
- 🟢 **Green** - Excellent (<500ms)
- 🟡 **Yellow** - Good (500-2000ms)
- 🔴 **Red** - Poor (>2000ms)

**RSSI-based (Received Signal Strength):**
- Stronger signal: -60 to -80 dBm
- Weak signal: -90 to -110 dBm
- Edge of range: -110 to -120 dBm

**SNR-based (Signal to Noise Ratio):**
- Excellent: >10 dB
- Good: 5-10 dB
- Poor: <5 dB

## Usage Examples

### Urban Coverage Test
```bash
# Mobile client with live HTML map
python range_test_gps.py abc123def456... --export html

# Walk or drive around
# Open export/range_test.html in browser to see real-time coverage
```

### Long Distance Test
```bash
# Increase ping interval to save airtime
# Edit client_config.json: "ping_interval": 30

python range_test_gps.py abc123def456... --exp all
```

### Multiple Simultaneous Clients
```bash
# Each client runs independently
# Server handles all clients simultaneously
# Each logs to its own directory

# Client 1
cd /sdcard/test1
python range_test_gps.py <hash> --exp html

# Client 2 (different location)
cd /sdcard/test2
python range_test_gps.py <hash> --exp html
```

### Export to Downloads
```bash
# Single format
python range_test_gps.py <hash> --export kml

# Multiple formats
python range_test_gps.py <hash> --exp csv --exp html

# All formats
python range_test_gps.py <hash> --exp all
```

On Ctrl+C, files are copied to `~/Downloads/` or `~/storage/downloads/` (Termux).

## GPS Support

### Termux (Android)
1. Install termux-api: `pkg install termux-api`
2. Install Termux:API app from F-Droid
3. Grant location permissions
4. Script auto-detects and uses `termux-location -p gps`

### Desktop (Linux/Mac/Windows)
GPS support can be added via:
- USB GPS receiver
- Bluetooth GPS
- GPSd daemon
- Custom implementation in `get_gps_termux()` function

### No GPS Available
- Script runs normally
- Pongs are received and RTT is shown
- **No data is logged to files** (GPS required for logging)
- Useful for stationary testing

## LoRa Configuration Recommendations

### Maximum Range
```
Bandwidth: 125 kHz
Spreading Factor: 10
Coding Rate: 7
TX Power: Maximum
```

**Settings:**
- `ping_interval`: 10-30s
- `ping_timeout`: 30s
- Expected RTT: 2-5 seconds

### Balanced (Recommended)
```
Bandwidth: 250 kHz
Spreading Factor: 9
Coding Rate: 7
TX Power: 17 dBm
```

**Settings:**
- `ping_interval`: 5-10s
- `ping_timeout`: 15s
- Expected RTT: 200-2000ms

### Fast/Short Range
```
Bandwidth: 500 kHz
Spreading Factor: 7
Coding Rate: 5
TX Power: 14 dBm
```

**Settings:**
- `ping_interval`: 5s
- `ping_timeout`: 10s
- Expected RTT: 50-500ms

## Troubleshooting

### "Could not establish path to server"
- Verify server is running and announced
- Check server hash is correct
- Ensure LoRa parameters match on both ends
- Try increasing `path_establishment_wait` in config
- Check that devices are in range

### No GPS Data
- **Termux:** Install `termux-api` package and Termux:API app
- Check location permissions granted
- Wait 30-60 seconds outdoors for GPS lock
- Check `termux-location -p gps` works manually
- Remember: **No GPS = No logging to files**

### High RTT / Frequent Timeouts
- Normal for LoRa! (200-2000ms is typical)
- Check spreading factor (higher = slower but longer range)
- Reduce `ping_interval` if too aggressive
- Increase `ping_timeout` for slow links
- Check for obstacles or interference

### Files Not Created
- Files only created when GPS data is available
- Check GPS is working: `termux-location -p gps`
- Verify pongs are received (shown in terminal)
- Check `export/` folder exists and is writable

### Export to Downloads Fails
- Script will show error but files remain in `export/`
- Check Downloads folder exists and is writable
- Termux: Use `~/storage/downloads/`
- Desktop: Use `~/Downloads/`

## Output Files

```
project/
├── client_config.json          # Client configuration
├── server_config.json          # Server configuration  
├── rt_id                        # Client identity (keep private!)
├── rt_server_id                # Server identity (keep private!)
├── range_test.json             # Raw client log (JSON lines)
├── range_test_server.json      # Server log (JSON lines)
└── export/
    ├── range_test.csv          # Spreadsheet data
    ├── range_test.json         # Complete JSON log
    ├── range_test.geojson      # GeoJSON for GIS
    ├── range_test.kml          # Google Earth (with path!)
    └── range_test.html         # Interactive map (with path!)
```

## Terminal Output Example

```
🚀 Init...
✓ My hash: d619c4dbc79bd3b97b828d553b5f4d51
✓ Display name: RangeTest-Mobile
✓ Server: 5f78e4f85713250dfd441dba20dcbb9d
📁 Logging to: export/

▶ Establishing path to server...
✓ Path established

⏱ Waiting 3s before starting...
▶ Starting range test (ping every 5s)
  Press Ctrl+C to stop

→ Ping #1
✓ Pong #1 RTT:234ms RSSI:-95dBm SNR:8.5dB GPS:45.123456,-122.654321 [1/1]
→ Ping #2
✓ Pong #2 RTT:189ms RSSI:-92dBm SNR:9.2dB GPS:45.123567,-122.654210 [2/2]
→ Ping #3
✗ Timeout #3
→ Ping #4
✓ Pong #4 RTT:456ms RSSI:-102dBm SNR:5.1dB GPS:45.123890,-122.653987 [3/4]
```

## Technical Details

### Packet Size
- Ping/Pong JSON: ~50-70 bytes
- Reticulum overhead: ~20-40 bytes
- **Total over LoRa: ~70-110 bytes**

Very efficient for LoRa networks!

### RSSI/SNR Extraction
Reticulum automatically tracks signal quality for received packets. The script extracts:
```python
rssi = getattr(packet, 'rssi', None)  # dBm
snr = getattr(packet, 'snr', None)    # dB
```

These values come from the LoRa modem via RNode.

### Multiple Client Support
The server can handle unlimited simultaneous clients:
- Each client has unique identity hash
- Server caches client destinations
- Responses routed correctly to each client
- No interference between clients

## Roadmap

**v0.2 (Planned):**
- [ ] Web dashboard for real-time monitoring
- [ ] SQLite database for large datasets
- [ ] Heatmap visualization
- [ ] Statistics summary (min/max/avg RTT, RSSI, SNR)
- [ ] Coverage area calculation
- [ ] GPX export format
- [ ] Offline map tiles

**v1.0 (Future):**
- [ ] Multi-server support
- [ ] Automated report generation
- [ ] Voice/audio notifications
- [ ] Integration with Meshtastic
- [ ] Docker container for server
- [ ] Web API for custom integrations

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test thoroughly (especially GPS/LoRa functionality)
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Credits

**Built for the Reticulum Network Stack community**

- [Reticulum](https://github.com/markqvist/Reticulum) by Mark Qvist
- [LXMF](https://github.com/markqvist/lxmf) protocol support
- Leaflet.js for interactive maps
- OpenStreetMap for map tiles

## Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/rtest/issues)
- **Discussions:** [Reticulum Matrix Channel](https://matrix.to/#/#reticulum:matrix.org)
- **Documentation:** [Reticulum Docs](https://markqvist.github.io/Reticulum/manual/)

## Changelog

### v0.1 (2026-01-19)
- Initial release
- GPS logging with Termux support
- RSSI/SNR tracking
- Multiple export formats (CSV, JSON, GeoJSON, KML, HTML)
- Interactive maps with path visualization
- JSON configuration system
- Auto-announce for path maintenance
- Multi-client server support

---

**Happy Range Testing! 📡🗺️**

*For questions or support, please open an issue on GitHub.*
