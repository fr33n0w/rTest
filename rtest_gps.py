#!/usr/bin/env python3
"""
Reticulum Range Test Client with GPS logging and export
"""

import RNS
import time
import json
import sys
import os
import threading
import subprocess
import csv
import shutil
from datetime import datetime

# Default configuration
DEFAULT_CONFIG = {
    "display_name": "RangeTest-Mobile",
    "announce_interval": 180,
    "ping_interval": 5,
    "ping_delay": 0,
    "ping_timeout": 10,
    "path_establishment_wait": 10,
    "pre_ping_delay": 3,
    "base_station_hash": "ca60113e441aa89fe4e6443339c7becb",
    "log_file": "range_test.json"
}

CONFIG_FILE = "client_config.json"
EXPORT_DIR = "export"

def load_config():
    """Load config from file or create default"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"✓ Loaded config from {CONFIG_FILE}")
                
                # Merge with defaults to add any missing keys
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                
                # Save back if new keys were added
                if len(merged) > len(config):
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump(merged, f, indent=2)
                    print(f"  Updated config with new settings")
                
                return merged
        except Exception as e:
            print(f"⚠ Error loading config: {e}, using defaults")
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"✓ Created default config: {CONFIG_FILE}")
    
    return DEFAULT_CONFIG.copy()

def get_gps_termux():
    """Get GPS from Termux API"""
    try:
        result = subprocess.run(
            ['termux-location', '-p', 'gps'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "altitude": data.get("altitude"),
                "accuracy": data.get("accuracy"),
                "speed": data.get("speed"),
                "bearing": data.get("bearing")
            }
    except:
        pass
    return None

class RangeTestClient:
    def __init__(self, server_hash=None, export_formats=None):
        self.config = load_config()
        self.export_formats = export_formats or []
        
        if server_hash:
            self.config['base_station_hash'] = server_hash
        
        os.makedirs(EXPORT_DIR, exist_ok=True)
        
        print("🚀 Init...")
        self.reticulum = RNS.Reticulum()
        
        if os.path.exists("rt_id"):
            self.identity = RNS.Identity.from_file("rt_id")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file("rt_id")
        
        self.dest = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "rt")
        self.dest.set_packet_callback(self.got_packet)
        
        self.server_hash = bytes.fromhex(self.config['base_station_hash'])
        self.server_identity = None
        self.server_dest = None
        self.pings = {}
        self.count = 0
        self.success = 0
        self.running = False
        
        # GPS logging
        self.test_data = []
        
        print(f"✓ My hash: {self.dest.hash.hex()}")
        print(f"✓ Display name: {self.config['display_name']}")
        print(f"✓ Server: {self.config['base_station_hash']}")
        print(f"📁 Logging to: {EXPORT_DIR}/")
        
        # Initial announce
        self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
        
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
        
        self.server_identity = RNS.Identity.recall(self.server_hash)
        if self.server_identity:
            self.create_server_destination()
        else:
            RNS.Transport.request_path(self.server_hash)
    
    def announce_loop(self):
        while self.running:
            time.sleep(self.config['announce_interval'])
            if self.running:
                self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
    
    def create_server_destination(self):
        if self.server_identity:
            self.server_dest = RNS.Destination(
                self.server_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "rt"
            )
    
    def got_packet(self, data, packet):
        try:
            msg = json.loads(data.decode())
            if msg.get('pong'):
                n = msg['pong']
                if n in self.pings:
                    rtt = time.time() - self.pings[n]
                    del self.pings[n]
                    self.success += 1
                    
                    # Get GPS
                    gps = get_gps_termux()
                    
                    # Get RSSI and SNR from packet
                    rssi = getattr(packet, 'rssi', None)
                    snr = getattr(packet, 'snr', None)
                    
                    # Only log if we have GPS
                    if gps and gps.get('latitude'):
                        # Log entry
                        entry = {
                            "ping": n,
                            "rtt": rtt,
                            "timestamp": datetime.now().isoformat(),
                            "gps": gps,
                            "rssi": rssi,
                            "snr": snr
                        }
                        
                        self.test_data.append(entry)
                        
                        # Show result with RSSI/SNR
                        signal_info = ""
                        if rssi is not None:
                            signal_info += f" RSSI:{rssi}dBm"
                        if snr is not None:
                            signal_info += f" SNR:{snr:.1f}dB"
                        
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms{signal_info} GPS:{gps['latitude']:.6f},{gps['longitude']:.6f} [{self.success}/{self.count}]")
                        
                        # Write logs after each GPS entry
                        self.write_logs()
                    else:
                        # No GPS - just show RTT
                        signal_info = ""
                        if rssi is not None:
                            signal_info += f" RSSI:{rssi}dBm"
                        if snr is not None:
                            signal_info += f" SNR:{snr:.1f}dB"
                        
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms{signal_info} (no GPS - not logged) [{self.success}/{self.count}]")
        except:
            pass
    
    def ping(self):
        if self.server_dest is None:
            self.server_identity = RNS.Identity.recall(self.server_hash)
            if self.server_identity:
                self.create_server_destination()
            else:
                RNS.Transport.request_path(self.server_hash)
                return
        
        if self.config['ping_delay'] > 0:
            time.sleep(self.config['ping_delay'])
        
        self.count += 1
        data = json.dumps({
            "ping": self.count,
            "from": self.dest.hash.hex()
        }).encode()
        
        try:
            p = RNS.Packet(self.server_dest, data)
            p.send()
            self.pings[self.count] = time.time()
            print(f"→ Ping #{self.count}")
        except Exception as e:
            print(f"✗ Send failed: {e}")
    
    def write_logs(self):
        """Always write log files incrementally"""
        if not self.test_data:
            return
        
        # Always write these formats
        self.write_csv()
        self.write_json()
        self.write_geojson()
        self.write_kml()
        self.write_html()
    
    def write_csv(self):
        """Write CSV log"""
        filepath = os.path.join(EXPORT_DIR, "range_test.csv")
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Ping', 'RTT_ms', 'Timestamp', 'Latitude', 'Longitude', 'Altitude', 'Accuracy', 'Speed', 'Bearing', 'RSSI_dBm', 'SNR_dB'])
            
            for entry in self.test_data:
                gps = entry.get('gps') or {}
                writer.writerow([
                    entry['ping'],
                    round(entry['rtt'] * 1000, 1),
                    entry['timestamp'],
                    gps.get('latitude', ''),
                    gps.get('longitude', ''),
                    gps.get('altitude', ''),
                    gps.get('accuracy', ''),
                    gps.get('speed', ''),
                    gps.get('bearing', ''),
                    entry.get('rssi', ''),
                    entry.get('snr', '')
                ])
    
    def write_json(self):
        """Write JSON log"""
        filepath = os.path.join(EXPORT_DIR, "range_test.json")
        
        with open(filepath, 'w') as f:
            json.dump(self.test_data, f, indent=2)
    
    def write_geojson(self):
        """Write GeoJSON"""
        filepath = os.path.join(EXPORT_DIR, "range_test.geojson")
        
        features = []
        for entry in self.test_data:
            gps = entry.get('gps')
            if gps and gps.get('latitude'):
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [gps['longitude'], gps['latitude'], gps.get('altitude', 0)]
                    },
                    "properties": {
                        "ping": entry['ping'],
                        "rtt_ms": round(entry['rtt'] * 1000, 1),
                        "timestamp": entry['timestamp'],
                        "accuracy": gps.get('accuracy'),
                        "speed": gps.get('speed'),
                        "bearing": gps.get('bearing'),
                        "rssi": entry.get('rssi'),
                        "snr": entry.get('snr')
                    }
                })
        
        geojson = {
            "type": "FeatureCollection",
            "features": features
        }
        
        with open(filepath, 'w') as f:
            json.dump(geojson, f, indent=2)
    
    def write_kml(self):
        """Write KML with path line"""
        filepath = os.path.join(EXPORT_DIR, "range_test.kml")
        
        kml = ['<?xml version="1.0" encoding="UTF-8"?>']
        kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
        kml.append('<Document>')
        kml.append('<name>Range Test Results</name>')
        
        # Styles
        kml.append('<Style id="goodSignal"><IconStyle><color>ff00ff00</color></IconStyle></Style>')
        kml.append('<Style id="okSignal"><IconStyle><color>ff00ffff</color></IconStyle></Style>')
        kml.append('<Style id="poorSignal"><IconStyle><color>ff0000ff</color></IconStyle></Style>')
        
        # Add path line
        if len(self.test_data) > 1:
            kml.append('<Placemark>')
            kml.append('<name>Path</name>')
            kml.append('<LineString>')
            kml.append('<coordinates>')
            coords = []
            for entry in self.test_data:
                gps = entry.get('gps')
                if gps and gps.get('latitude'):
                    coords.append(f"{gps['longitude']},{gps['latitude']},{gps.get('altitude', 0)}")
            kml.append(' '.join(coords))
            kml.append('</coordinates>')
            kml.append('</LineString>')
            kml.append('<Style><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>')
            kml.append('</Placemark>')
        
        # Add points
        for entry in self.test_data:
            gps = entry.get('gps')
            if gps and gps.get('latitude'):
                rtt_ms = entry['rtt'] * 1000
                
                if rtt_ms < 500:
                    style = 'goodSignal'
                elif rtt_ms < 2000:
                    style = 'okSignal'
                else:
                    style = 'poorSignal'
                
                desc = f"RTT: {rtt_ms:.0f}ms&lt;br/&gt;Time: {entry['timestamp']}"
                if entry.get('rssi') is not None:
                    desc += f"&lt;br/&gt;RSSI: {entry['rssi']}dBm"
                if entry.get('snr') is not None:
                    desc += f"&lt;br/&gt;SNR: {entry['snr']:.1f}dB"
                
                kml.append('<Placemark>')
                kml.append(f'<name>Ping #{entry["ping"]}</name>')
                kml.append(f'<description>{desc}</description>')
                kml.append(f'<styleUrl>#{style}</styleUrl>')
                kml.append('<Point>')
                kml.append(f'<coordinates>{gps["longitude"]},{gps["latitude"]},{gps.get("altitude", 0)}</coordinates>')
                kml.append('</Point>')
                kml.append('</Placemark>')
        
        kml.append('</Document>')
        kml.append('</kml>')
        
        with open(filepath, 'w') as f:
            f.write('\n'.join(kml))
    def write_html(self):
        """Write HTML map (only entries with GPS)"""
        filepath = os.path.join(EXPORT_DIR, "range_test.html")
        
        # Extract GPS points
        points = []
        for entry in self.test_data:
            gps = entry.get('gps')
            if gps and gps.get('latitude'):
                points.append({
                    'lat': gps['latitude'],
                    'lon': gps['longitude'],
                    'rtt': entry['rtt'] * 1000,
                    'ping': entry['ping'],
                    'time': entry['timestamp'],
                    'rssi': entry.get('rssi'),
                    'snr': entry.get('snr')
                })
        
        if not points:
            # Create placeholder HTML
            html = '''<!DOCTYPE html>
<html><head><title>Range Test Map</title></head>
<body><h1>No GPS data yet</h1><p>Waiting for GPS coordinates...</p></body></html>'''
            with open(filepath, 'w') as f:
                f.write(html)
            return
        
        # Calculate center
        center_lat = sum(p['lat'] for p in points) / len(points)
        center_lon = sum(p['lon'] for p in points) / len(points)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Range Test Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ height: 100vh; width: 100%; }}
        .legend {{ background: white; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lon}], 13);
        
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        var points = {json.dumps(points)};
        
        // Draw path line
        if (points.length > 1) {{
            var pathCoords = points.map(p => [p.lat, p.lon]);
            L.polyline(pathCoords, {{color: 'blue', weight: 3, opacity: 0.7}}).addTo(map);
        }}
        
        // Add markers
        points.forEach(function(point) {{
            var color;
            if (point.rtt < 500) color = 'green';
            else if (point.rtt < 2000) color = 'yellow';
            else color = 'red';
            
            var popup = `<b>Ping #${{point.ping}}</b><br>RTT: ${{point.rtt.toFixed(0)}}ms<br>Time: ${{point.time}}<br>Location: ${{point.lat.toFixed(6)}}, ${{point.lon.toFixed(6)}}`;
            if (point.rssi !== null && point.rssi !== undefined) {{
                popup += `<br>RSSI: ${{point.rssi}}dBm`;
            }}
            if (point.snr !== null && point.snr !== undefined) {{
                popup += `<br>SNR: ${{point.snr.toFixed(1)}}dB`;
            }}
            
            L.circleMarker([point.lat, point.lon], {{
                radius: 6,
                fillColor: color,
                color: '#000',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            }}).bindPopup(popup).addTo(map);
        }});
        
        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<b>Signal Quality</b><br>' +
                '<span style="color:green">● Good (&lt;500ms)</span><br>' +
                '<span style="color:yellow">● OK (500-2000ms)</span><br>' +
                '<span style="color:red">● Poor (&gt;2000ms)</span>';
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>'''
        
        with open(filepath, 'w') as f:
            f.write(html)
    
    def export_to_downloads(self):
        """Copy files to Downloads folder with timestamp"""
        if not self.export_formats and not self.test_data:
            return
        
        # Generate timestamp for filenames
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Try to find Downloads folder
        downloads = None
        if os.path.exists(os.path.expanduser("~/storage/downloads")):
            downloads = os.path.expanduser("~/storage/downloads")  # Termux
        elif os.path.exists(os.path.expanduser("~/Downloads")):
            downloads = os.path.expanduser("~/Downloads")  # Linux/Mac
        elif os.path.exists(os.path.expanduser("~\\Downloads")):
            downloads = os.path.expanduser("~\\Downloads")  # Windows
        
        if not downloads:
            print("\n⚠ Could not find Downloads folder")
            print(f"  Files are in: {os.path.abspath(EXPORT_DIR)}/")
            return
        
        print(f"\n📥 Copying to Downloads...")
        
        file_map = {
            'csv': ('range_test.csv', f'rtest_{timestamp}.csv'),
            'json': ('range_test.json', f'rtest_{timestamp}.json'),
            'geojson': ('range_test.geojson', f'rtest_{timestamp}.geojson'),
            'kml': ('range_test.kml', f'rtest_{timestamp}.kml'),
            'html': ('range_test.html', f'rtest_{timestamp}.html')
        }
        
        # If no specific formats requested, export all (after Ctrl+C)
        if not self.export_formats:
            formats_to_export = file_map.keys()
        elif 'all' in self.export_formats:
            formats_to_export = file_map.keys()
        else:
            formats_to_export = self.export_formats
        
        for fmt in formats_to_export:
            if fmt == 'all':
                continue
            
            if fmt in file_map:
                src_name, dst_name = file_map[fmt]
                src = os.path.join(EXPORT_DIR, src_name)
                dst = os.path.join(downloads, dst_name)
                
                if os.path.exists(src):
                    try:
                        shutil.copy2(src, dst)
                        print(f"  ✓ {dst_name}")
                    except Exception as e:
                        print(f"  ✗ {dst_name}: {e}")
        
        print(f"📁 Saved to: {downloads}")
    
    def run(self):
        print(f"\n▶ Establishing path to server...")
        self.running = True
        
        # Keep trying to get server destination
        retry_count = 0
        while self.server_dest is None:
            time.sleep(0.5)
            
            if self.server_identity is None:
                self.server_identity = RNS.Identity.recall(self.server_hash)
                if self.server_identity:
                    self.create_server_destination()
                    print("✓ Path established")
                    break
            
            # Request path periodically
            retry_count += 1
            if retry_count % 20 == 0:  # Every 10 seconds
                print(f"  ⚠ Waiting for server... ({retry_count//2}s)")
                RNS.Transport.request_path(self.server_hash)
            
            if retry_count == 10:  # After 5 seconds
                print(f"    💡 Press Ctrl+C to cancel")
        
        if self.config['pre_ping_delay'] > 0:
            print(f"\n⏱ Waiting {self.config['pre_ping_delay']}s before starting...")
            time.sleep(self.config['pre_ping_delay'])
        
        print(f"\n▶ Starting range test (ping every {self.config['ping_interval']}s)")
        if self.export_formats:
            print(f"📁 Will export to Downloads on exit")
        print("  Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.ping()
                now = time.time()
                for n, t in list(self.pings.items()):
                    if now - t > self.config['ping_timeout']:
                        del self.pings[n]
                        print(f"✗ Timeout #{n}")
                time.sleep(self.config['ping_interval'])
        except KeyboardInterrupt:
            print(f"\n⏹ Done: {self.success}/{self.count}")
            if self.test_data:
                print(f"📁 Logs in: {EXPORT_DIR}/ ({len(self.test_data)} GPS entries)")
            else:
                print(f"⚠ No GPS data recorded")
            
            # Always export to Downloads on Ctrl+C (with timestamp)
            if self.test_data:
                self.export_to_downloads()
            
            self.running = False

if __name__ == "__main__":
    server_hash = None
    export_formats = []
    
    # Parse arguments
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ['--export', '--exp'] and i + 1 < len(sys.argv):
            fmt = sys.argv[i + 1]
            if fmt == 'all':
                export_formats = ['all']
            else:
                export_formats.append(fmt)
            i += 2
        elif len(arg) == 32:  # Hash
            server_hash = arg
            i += 1
        else:
            i += 1
    
    if export_formats and not all(f in ['csv', 'json', 'geojson', 'kml', 'html', 'all'] for f in export_formats):
        print("Usage: python range_test_gps.py [hash] [--export csv|json|geojson|kml|html|all]")
        print("  --exp all  - Export all formats to Downloads")
        sys.exit(1)
    
    RangeTestClient(server_hash, export_formats).run()


# Default configuration
DEFAULT_CONFIG = {
    "display_name": "RangeTest-Mobile",
    "announce_interval": 180,
    "ping_interval": 5,
    "ping_delay": 0,
    "ping_timeout": 10,
    "path_establishment_wait": 10,
    "pre_ping_delay": 3,
    "base_station_hash": "ca60113e441aa89fe4e6443339c7becb",
    "log_file": "range_test.json"
}

CONFIG_FILE = "client_config.json"
EXPORT_DIR = "export"

def load_config():
    """Load config from file or create default"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"✓ Loaded config from {CONFIG_FILE}")
                
                # Merge with defaults to add any missing keys
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                
                # Save back if new keys were added
                if len(merged) > len(config):
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump(merged, f, indent=2)
                    print(f"  Updated config with new settings")
                
                return merged
        except Exception as e:
            print(f"⚠ Error loading config: {e}, using defaults")
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"✓ Created default config: {CONFIG_FILE}")
    
    return DEFAULT_CONFIG.copy()

def get_gps_termux():
    """Get GPS from Termux API"""
    try:
        result = subprocess.run(
            ['termux-location', '-p', 'gps'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "altitude": data.get("altitude"),
                "accuracy": data.get("accuracy"),
                "speed": data.get("speed"),
                "bearing": data.get("bearing")
            }
    except:
        pass
    return None

class RangeTestClient:
    def __init__(self, server_hash=None, export_mode=None):
        self.config = load_config()
        self.export_mode = export_mode
        
        if server_hash:
            self.config['base_station_hash'] = server_hash
        
        os.makedirs(EXPORT_DIR, exist_ok=True)
        
        print("🚀 Init...")
        self.reticulum = RNS.Reticulum()
        
        if os.path.exists("rt_id"):
            self.identity = RNS.Identity.from_file("rt_id")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file("rt_id")
        
        self.dest = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "rt")
        self.dest.set_packet_callback(self.got_packet)
        
        self.server_hash = bytes.fromhex(self.config['base_station_hash'])
        self.server_identity = None
        self.server_dest = None
        self.pings = {}
        self.count = 0
        self.success = 0
        self.running = False
        
        # GPS logging
        self.test_data = []
        
        print(f"✓ My hash: {self.dest.hash.hex()}")
        print(f"✓ Display name: {self.config['display_name']}")
        print(f"✓ Server: {self.config['base_station_hash']}")
        
        # Initial announce
        self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
        
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
        
        self.server_identity = RNS.Identity.recall(self.server_hash)
        if self.server_identity:
            self.create_server_destination()
        else:
            RNS.Transport.request_path(self.server_hash)
    
    def announce_loop(self):
        while self.running:
            time.sleep(self.config['announce_interval'])
            if self.running:
                self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
    
    def create_server_destination(self):
        if self.server_identity:
            self.server_dest = RNS.Destination(
                self.server_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "rt"
            )
    
    def got_packet(self, data, packet):
        try:
            msg = json.loads(data.decode())
            if msg.get('pong'):
                n = msg['pong']
                if n in self.pings:
                    rtt = time.time() - self.pings[n]
                    del self.pings[n]
                    self.success += 1
                    
                    # Get GPS
                    gps = get_gps_termux()
                    
                    # Log entry
                    entry = {
                        "ping": n,
                        "rtt": rtt,
                        "timestamp": datetime.now().isoformat(),
                        "gps": gps
                    }
                    
                    self.test_data.append(entry)
                    
                    # Show result
                    if gps and gps.get('latitude'):
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms GPS:{gps['latitude']:.6f},{gps['longitude']:.6f} [{self.success}/{self.count}]")
                    else:
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms (no GPS) [{self.success}/{self.count}]")
                    
                    # Incremental export
                    if self.export_mode:
                        self.export_data()
        except:
            pass
    
    def ping(self):
        if self.server_dest is None:
            self.server_identity = RNS.Identity.recall(self.server_hash)
            if self.server_identity:
                self.create_server_destination()
            else:
                RNS.Transport.request_path(self.server_hash)
                return
        
        if self.config['ping_delay'] > 0:
            time.sleep(self.config['ping_delay'])
        
        self.count += 1
        data = json.dumps({
            "ping": self.count,
            "from": self.dest.hash.hex()
        }).encode()
        
        try:
            p = RNS.Packet(self.server_dest, data)
            p.send()
            self.pings[self.count] = time.time()
            print(f"→ Ping #{self.count}")
        except Exception as e:
            print(f"✗ Send failed: {e}")
    
    def export_data(self):
        """Export data incrementally"""
        if not self.test_data:
            return
        
        if self.export_mode == 'csv':
            self.export_csv()
        elif self.export_mode == 'kml':
            self.export_kml()
        elif self.export_mode == 'html':
            self.export_html()
    
    def export_csv(self):
        """Export to CSV"""
        filepath = os.path.join(EXPORT_DIR, "range_test.csv")
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Ping', 'RTT_ms', 'Timestamp', 'Latitude', 'Longitude', 'Altitude', 'Accuracy', 'Speed', 'Bearing'])
            
            for entry in self.test_data:
                gps = entry.get('gps') or {}
                writer.writerow([
                    entry['ping'],
                    round(entry['rtt'] * 1000, 1),
                    entry['timestamp'],
                    gps.get('latitude', ''),
                    gps.get('longitude', ''),
                    gps.get('altitude', ''),
                    gps.get('accuracy', ''),
                    gps.get('speed', ''),
                    gps.get('bearing', '')
                ])
    
    def export_kml(self):
        """Export to KML"""
        filepath = os.path.join(EXPORT_DIR, "range_test.kml")
        
        kml = ['<?xml version="1.0" encoding="UTF-8"?>']
        kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
        kml.append('<Document>')
        kml.append('<name>Range Test Results</name>')
        
        # Style for points
        kml.append('<Style id="goodSignal"><IconStyle><color>ff00ff00</color></IconStyle></Style>')
        kml.append('<Style id="okSignal"><IconStyle><color>ff00ffff</color></IconStyle></Style>')
        kml.append('<Style id="poorSignal"><IconStyle><color>ff0000ff</color></IconStyle></Style>')
        
        for entry in self.test_data:
            gps = entry.get('gps')
            if gps and gps.get('latitude'):
                rtt_ms = entry['rtt'] * 1000
                
                # Color by RTT
                if rtt_ms < 500:
                    style = 'goodSignal'
                elif rtt_ms < 2000:
                    style = 'okSignal'
                else:
                    style = 'poorSignal'
                
                kml.append('<Placemark>')
                kml.append(f'<name>Ping #{entry["ping"]}</name>')
                kml.append(f'<description>RTT: {rtt_ms:.0f}ms&lt;br/&gt;Time: {entry["timestamp"]}</description>')
                kml.append(f'<styleUrl>#{style}</styleUrl>')
                kml.append('<Point>')
                kml.append(f'<coordinates>{gps["longitude"]},{gps["latitude"]},{gps.get("altitude", 0)}</coordinates>')
                kml.append('</Point>')
                kml.append('</Placemark>')
        
        kml.append('</Document>')
        kml.append('</kml>')
        
        with open(filepath, 'w') as f:
            f.write('\n'.join(kml))
    
    def export_html(self):
        """Export to HTML map"""
        filepath = os.path.join(EXPORT_DIR, "range_test.html")
        
        # Extract GPS points
        points = []
        for entry in self.test_data:
            gps = entry.get('gps')
            if gps and gps.get('latitude'):
                points.append({
                    'lat': gps['latitude'],
                    'lon': gps['longitude'],
                    'rtt': entry['rtt'] * 1000,
                    'ping': entry['ping'],
                    'time': entry['timestamp'],
                    'rssi': entry.get('rssi'),
                    'snr': entry.get('snr')
                })
        
        if not points:
            return
        
        # Calculate center
        center_lat = sum(p['lat'] for p in points) / len(points)
        center_lon = sum(p['lon'] for p in points) / len(points)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Range Test Map</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ height: 100vh; width: 100%; }}
        .legend {{ background: white; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        var map = L.map('map').setView([{center_lat}, {center_lon}], 13);
        
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        var points = {json.dumps(points)};
        
        // Draw path line
        if (points.length > 1) {{
            var pathCoords = points.map(p => [p.lat, p.lon]);
            L.polyline(pathCoords, {{color: 'blue', weight: 3, opacity: 0.7}}).addTo(map);
        }}
        
        // Add markers
        points.forEach(function(point) {{
            var color;
            if (point.rtt < 500) color = 'green';
            else if (point.rtt < 2000) color = 'yellow';
            else color = 'red';
            
            var popup = `<b>Ping #${{point.ping}}</b><br>RTT: ${{point.rtt.toFixed(0)}}ms<br>Time: ${{point.time}}<br>Location: ${{point.lat.toFixed(6)}}, ${{point.lon.toFixed(6)}}`;
            if (point.rssi !== null && point.rssi !== undefined) {{
                popup += `<br>RSSI: ${{point.rssi}}dBm`;
            }}
            if (point.snr !== null && point.snr !== undefined) {{
                popup += `<br>SNR: ${{point.snr.toFixed(1)}}dB`;
            }}
            
            L.circleMarker([point.lat, point.lon], {{
                radius: 6,
                fillColor: color,
                color: '#000',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            }}).bindPopup(popup).addTo(map);
        }});
        
        // Add legend
        var legend = L.control({{position: 'bottomright'}});
        legend.onAdd = function(map) {{
            var div = L.DomUtil.create('div', 'legend');
            div.innerHTML = '<b>Signal Quality</b><br>' +
                '<span style="color:green">● Good (&lt;500ms)</span><br>' +
                '<span style="color:yellow">● OK (500-2000ms)</span><br>' +
                '<span style="color:red">● Poor (&gt;2000ms)</span>';
            return div;
        }};
        legend.addTo(map);
    </script>
</body>
</html>'''
        
        with open(filepath, 'w') as f:
            f.write(html)
    
    def run(self):
        print(f"\n▶ Establishing path to server...")
        self.running = True
        
        max_wait = self.config['path_establishment_wait']
        waited = 0
        while self.server_dest is None and waited < max_wait:
            time.sleep(0.5)
            waited += 0.5
            
            if self.server_identity is None:
                self.server_identity = RNS.Identity.recall(self.server_hash)
                if self.server_identity:
                    self.create_server_destination()
        
        if self.server_dest is None:
            print("✗ Could not establish path to server")
            self.running = False
            return
        
        print("✓ Path established")
        
        if self.config['pre_ping_delay'] > 0:
            print(f"\n⏱ Waiting {self.config['pre_ping_delay']}s before starting...")
            time.sleep(self.config['pre_ping_delay'])
        
        print(f"▶ Starting range test (ping every {self.config['ping_interval']}s)")
        if self.export_mode:
            print(f"📁 Exporting to: {EXPORT_DIR}/range_test.{self.export_mode}")
        print("  Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.ping()
                now = time.time()
                for n, t in list(self.pings.items()):
                    if now - t > self.config['ping_timeout']:
                        del self.pings[n]
                        print(f"✗ Timeout #{n}")
                time.sleep(self.config['ping_interval'])
        except KeyboardInterrupt:
            print(f"\n⏹ Done: {self.success}/{self.count}")
            if self.export_mode:
                self.export_data()
                print(f"📁 Final export saved to: {EXPORT_DIR}/range_test.{self.export_mode}")
            self.running = False

if __name__ == "__main__":
    server_hash = None
    export_mode = None
    
    # Parse arguments
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ['--export', '--exp'] and i + 1 < len(sys.argv):
            export_mode = sys.argv[i + 1]
            i += 2
        elif len(arg) == 32:  # Assume it's a hash
            server_hash = arg
            i += 1
        else:
            i += 1
    
    if export_mode and export_mode not in ['csv', 'kml', 'html']:
        print("Usage: python range_client.py [hash] [--export csv|kml|html]")
        sys.exit(1)
    
    RangeTestClient(server_hash, export_mode).run()
