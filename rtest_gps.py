#!/usr/bin/env python3
"""
Simple Reticulum Range Test - Uses announce callback
"""

import RNS
import time
import json
import sys
import os
import threading
from datetime import datetime

BASE_HASH = "ca60113e441aa89fe4e6443339c7becb"
PING_INTERVAL = 5
LOG_FILE = "range_test.json"
EXPORT_DIR = "export"
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

CLIENT_NAME = "RangeTest-Mobile"  # Display name for announces

class SimpleRangeTest:
    def __init__(self, server_hash):
        print("🚀 Init...")
        self.reticulum = RNS.Reticulum()
        
        if os.path.exists("rt_id"):
            self.identity = RNS.Identity.from_file("rt_id")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file("rt_id")
        
        self.dest = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "rt")
        self.dest.set_packet_callback(self.got_packet)
        
        self.server_hash = bytes.fromhex(server_hash)
        self.server_identity = None
        self.server_dest = None
        self.pings = {}
        self.count = 0
        self.success = 0
        self.running = False
        
        print(f"✓ My hash: {self.dest.hash.hex()}")
        print(f"✓ Server: {server_hash}")
        
        # Initial announce
        print("📡 Announcing to network...")
        self.dest.announce(app_data=CLIENT_NAME.encode('utf-8'))
        print(f"  Name: {CLIENT_NAME}")
        
        # Start announce thread
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
        
        # Try to get server identity
        self.server_identity = RNS.Identity.recall(self.server_hash)
        if self.server_identity:
            print("✓ Server identity known")
            self.create_server_destination()
        else:
            print("  Requesting server path...")
            RNS.Transport.request_path(self.server_hash)
    
    def announce_loop(self):
        """Announce every 3 minutes"""
        while self.running:
            time.sleep(180)  # 3 minutes
            if self.running:
                self.dest.announce(app_data=CLIENT_NAME.encode('utf-8'))
                print("\n[Auto-announced]")
    
    def create_server_destination(self):
        """Create destination object for server"""
        if self.server_identity:
            self.server_dest = RNS.Destination(
                self.server_identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                "rt"
            )
            print("✓ Server destination created")
    
    def got_packet(self, data, packet):
        try:
            msg = json.loads(data.decode())
            if msg.get('pong'):
                n = msg['pong']
                if n in self.pings:
                    rtt = time.time() - self.pings[n]
                    del self.pings[n]
                    self.success += 1
                    
                    # Get GPS and RSSI/SNR
                    gps = get_gps_termux()
                    rssi = getattr(packet, 'rssi', None)
                    snr = getattr(packet, 'snr', None)
                    
                    # Build signal info string
                    signal_info = ""
                    if rssi is not None:
                        signal_info += f" RSSI:{rssi}dBm"
                    if snr is not None:
                        signal_info += f" SNR:{snr:.1f}dB"
                    
                    # Only log if we have GPS
                    if gps and gps.get('latitude'):
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms{signal_info} GPS:{gps['latitude']:.6f},{gps['longitude']:.6f} [{self.success}/{self.count}]")
                        
                        # Save to log
                        entry = {
                            "ping": n,
                            "rtt": rtt,
                            "timestamp": datetime.now().isoformat(),
                            "gps": gps,
                            "rssi": rssi,
                            "snr": snr
                        }
                        
                        with open(LOG_FILE, 'a') as f:
                            f.write(json.dumps(entry) + '\n')
                    else:
                        print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms{signal_info} (no GPS - not logged) [{self.success}/{self.count}]")
        except:
            pass
    
    def ping(self):
        # Check if we have server destination
        if self.server_dest is None:
            # Try to get identity again
            self.server_identity = RNS.Identity.recall(self.server_hash)
            if self.server_identity:
                self.create_server_destination()
            else:
                print("  ⚠ Waiting for server path...")
                RNS.Transport.request_path(self.server_hash)
                return
        
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
    
    def run(self):
        print("\n▶ Establishing path to server...")
        self.running = True
        
        # Wait for server destination to be ready
        max_wait = 10
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
            print("  Make sure server is running and reachable")
            self.running = False
            return
        
        print("✓ Path established")
        print("\n⏱ Waiting 3 seconds before starting test...")
        time.sleep(3)
        
        print("▶ Starting range test (ping every 5s)")
        print("  Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.ping()
                # Timeout check
                now = time.time()
                for n, t in list(self.pings.items()):
                    if now - t > 10:
                        del self.pings[n]
                        print(f"✗ Timeout #{n}")
                time.sleep(PING_INTERVAL)
        except KeyboardInterrupt:
            print(f"\n⏹ Done: {self.success}/{self.count}")
            self.export_logs()
            self.running = False
    
    def export_logs(self):
        """Export all formats to Downloads with timestamp"""
        try:
            # Read log file
            if not os.path.exists(LOG_FILE):
                return
                
            with open(LOG_FILE, 'r') as f:
                entries = [json.loads(line) for line in f if line.strip()]
            
            # Filter entries with GPS
            gps_entries = [e for e in entries if e.get('gps') and e['gps'].get('latitude')]
            
            if not gps_entries:
                print("⚠ No GPS data to export")
                return
            
            # Find Downloads
            downloads = None
            for path in ["~/storage/downloads", "~/Downloads", "~\\Downloads"]:
                expanded = os.path.expanduser(path)
                if os.path.exists(expanded):
                    downloads = expanded
                    break
            
            if not downloads:
                print(f"⚠ Could not find Downloads, files in: {os.path.abspath(EXPORT_DIR)}/")
                return
            
            # Generate timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            print(f"\n📥 Exporting to Downloads...")
            
            # 1. CSV
            csv_file = os.path.join(downloads, f"rtest_{timestamp}.csv")
            with open(csv_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Ping', 'RTT_ms', 'Timestamp', 'Latitude', 'Longitude', 'Altitude', 'Accuracy', 'Speed', 'Bearing', 'RSSI_dBm', 'SNR_dB'])
                for e in gps_entries:
                    gps = e['gps']
                    writer.writerow([
                        e['ping'], round(e['rtt'] * 1000, 1), e['timestamp'],
                        gps.get('latitude', ''), gps.get('longitude', ''), gps.get('altitude', ''),
                        gps.get('accuracy', ''), gps.get('speed', ''), gps.get('bearing', ''),
                        e.get('rssi', ''), e.get('snr', '')
                    ])
            print(f"  ✓ rtest_{timestamp}.csv")
            
            # 2. JSON
            json_file = os.path.join(downloads, f"rtest_{timestamp}.json")
            with open(json_file, 'w') as f:
                json.dump(gps_entries, f, indent=2)
            print(f"  ✓ rtest_{timestamp}.json")
            
            # 3. GeoJSON
            features = []
            for e in gps_entries:
                gps = e['gps']
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [gps['longitude'], gps['latitude'], gps.get('altitude', 0)]
                    },
                    "properties": {
                        "ping": e['ping'],
                        "rtt_ms": round(e['rtt'] * 1000, 1),
                        "timestamp": e['timestamp'],
                        "accuracy": gps.get('accuracy'),
                        "speed": gps.get('speed'),
                        "bearing": gps.get('bearing'),
                        "rssi": e.get('rssi'),
                        "snr": e.get('snr')
                    }
                })
            
            geojson_file = os.path.join(downloads, f"rtest_{timestamp}.geojson")
            with open(geojson_file, 'w') as f:
                json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
            print(f"  ✓ rtest_{timestamp}.geojson")
            
            # 4. KML with path
            kml = ['<?xml version="1.0" encoding="UTF-8"?>']
            kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
            kml.append('<Document>')
            kml.append('<name>Range Test Results</name>')
            kml.append('<Style id="goodSignal"><IconStyle><color>ff00ff00</color></IconStyle></Style>')
            kml.append('<Style id="okSignal"><IconStyle><color>ff00ffff</color></IconStyle></Style>')
            kml.append('<Style id="poorSignal"><IconStyle><color>ff0000ff</color></IconStyle></Style>')
            
            # Path line
            if len(gps_entries) > 1:
                kml.append('<Placemark><name>Path</name><LineString><coordinates>')
                coords = []
                for e in gps_entries:
                    gps = e['gps']
                    coords.append(f"{gps['longitude']},{gps['latitude']},{gps.get('altitude', 0)}")
                kml.append(' '.join(coords))
                kml.append('</coordinates></LineString>')
                kml.append('<Style><LineStyle><color>ff0000ff</color><width>3</width></LineStyle></Style>')
                kml.append('</Placemark>')
            
            # Points
            for e in gps_entries:
                gps = e['gps']
                rtt_ms = e['rtt'] * 1000
                style = 'goodSignal' if rtt_ms < 500 else ('okSignal' if rtt_ms < 2000 else 'poorSignal')
                
                desc = f"RTT: {rtt_ms:.0f}ms&lt;br/&gt;Time: {e['timestamp']}"
                if e.get('rssi') is not None:
                    desc += f"&lt;br/&gt;RSSI: {e['rssi']}dBm"
                if e.get('snr') is not None:
                    desc += f"&lt;br/&gt;SNR: {e['snr']:.1f}dB"
                
                kml.append(f'<Placemark><name>Ping #{e["ping"]}</name>')
                kml.append(f'<description>{desc}</description>')
                kml.append(f'<styleUrl>#{style}</styleUrl>')
                kml.append(f'<Point><coordinates>{gps["longitude"]},{gps["latitude"]},{gps.get("altitude", 0)}</coordinates></Point>')
                kml.append('</Placemark>')
            
            kml.append('</Document></kml>')
            
            kml_file = os.path.join(downloads, f"rtest_{timestamp}.kml")
            with open(kml_file, 'w') as f:
                f.write('\n'.join(kml))
            print(f"  ✓ rtest_{timestamp}.kml")
            
            # 5. HTML map with path
            center_lat = sum(e['gps']['latitude'] for e in gps_entries) / len(gps_entries)
            center_lon = sum(e['gps']['longitude'] for e in gps_entries) / len(gps_entries)
            
            points = []
            for e in gps_entries:
                gps = e['gps']
                points.append({
                    'lat': gps['latitude'],
                    'lon': gps['longitude'],
                    'rtt': e['rtt'] * 1000,
                    'ping': e['ping'],
                    'time': e['timestamp'],
                    'rssi': e.get('rssi'),
                    'snr': e.get('snr')
                })
            
            html = f"""<!DOCTYPE html>
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
        
        // Draw path
        if (points.length > 1) {{
            var pathCoords = points.map(p => [p.lat, p.lon]);
            L.polyline(pathCoords, {{color: 'blue', weight: 3, opacity: 0.7}}).addTo(map);
        }}
        
        // Add markers
        points.forEach(function(point) {{
            var color = point.rtt < 500 ? 'green' : (point.rtt < 2000 ? 'yellow' : 'red');
            var popup = `<b>Ping #${{point.ping}}</b><br>RTT: ${{point.rtt.toFixed(0)}}ms<br>Time: ${{point.time}}<br>Location: ${{point.lat.toFixed(6)}}, ${{point.lon.toFixed(6)}}`;
            if (point.rssi !== null && point.rssi !== undefined) popup += `<br>RSSI: ${{point.rssi}}dBm`;
            if (point.snr !== null && point.snr !== undefined) popup += `<br>SNR: ${{point.snr.toFixed(1)}}dB`;
            
            L.circleMarker([point.lat, point.lon], {{
                radius: 6, fillColor: color, color: '#000',
                weight: 1, opacity: 1, fillOpacity: 0.8
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
</html>"""
            
            html_file = os.path.join(downloads, f"rtest_{timestamp}.html")
            with open(html_file, 'w') as f:
                f.write(html)
            print(f"  ✓ rtest_{timestamp}.html")
            
            print(f"📁 Saved to: {downloads}")
            
        except Exception as e:
            print(f"✗ Export failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    h = sys.argv[1] if len(sys.argv) > 1 else BASE_HASH
    SimpleRangeTest(h).run()
