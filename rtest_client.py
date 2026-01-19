#!/usr/bin/env python3
"""
Simple Reticulum Range Test Client - With Config
"""

import RNS
import time
import json
import sys
import os
import threading
from datetime import datetime

# Default configuration
DEFAULT_CONFIG = {
    "display_name": "RangeTest-Mobile",
    "announce_interval": 180,  # seconds (3 minutes)
    "ping_interval": 5,  # seconds between pings
    "ping_timeout": 10,  # seconds to wait for pong
    "path_establishment_wait": 10,  # seconds to wait for server path
    "pre_ping_delay": 3,  # seconds to wait before starting pings
    "base_station_hash": "ca60113e441aa89fe4e6443339c7becb",
    "log_file": "range_test.json"
}

CONFIG_FILE = "client_config.json"

def load_config():
    """Load config from file or create default"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"✓ Loaded config from {CONFIG_FILE}")
                return config
        except Exception as e:
            print(f"⚠ Error loading config: {e}")
            print("  Using defaults")
    
    # Create default config file
    with open(CONFIG_FILE, 'w') as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)
    print(f"✓ Created default config: {CONFIG_FILE}")
    
    return DEFAULT_CONFIG.copy()

class SimpleRangeTest:
    def __init__(self, server_hash=None):
        # Load configuration
        self.config = load_config()
        
        # Override server hash if provided as argument
        if server_hash:
            self.config['base_station_hash'] = server_hash
        
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
        
        print(f"✓ My hash: {self.dest.hash.hex()}")
        print(f"✓ Display name: {self.config['display_name']}")
        print(f"✓ Server: {self.config['base_station_hash']}")
        print(f"✓ Announce interval: {self.config['announce_interval']}s")
        print(f"✓ Ping interval: {self.config['ping_interval']}s")
        
        # Initial announce
        print("📡 Announcing to network...")
        self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
        
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
        """Announce periodically"""
        while self.running:
            time.sleep(self.config['announce_interval'])
            if self.running:
                self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
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
                    print(f"✓ Pong #{n} RTT:{rtt*1000:.0f}ms [{self.success}/{self.count}]")
                    
                    with open(self.config['log_file'], 'a') as f:
                        f.write(json.dumps({
                            "n": n,
                            "rtt": rtt,
                            "time": datetime.now().isoformat()
                        }) + '\n')
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
        print(f"\n▶ Establishing path to server...")
        self.running = True
        
        # Wait for server destination to be ready
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
            print("  Make sure server is running and reachable")
            self.running = False
            return
        
        print("✓ Path established")
        
        if self.config['pre_ping_delay'] > 0:
            print(f"\n⏱ Waiting {self.config['pre_ping_delay']}s before starting test...")
            time.sleep(self.config['pre_ping_delay'])
        
        print(f"▶ Starting range test (ping every {self.config['ping_interval']}s)")
        print("  Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.ping()
                # Timeout check
                now = time.time()
                for n, t in list(self.pings.items()):
                    if now - t > self.config['ping_timeout']:
                        del self.pings[n]
                        print(f"✗ Timeout #{n}")
                time.sleep(self.config['ping_interval'])
        except KeyboardInterrupt:
            print(f"\n⏹ Done: {self.success}/{self.count}")
            print(f"📁 Log saved to: {self.config['log_file']}")
            self.running = False

if __name__ == "__main__":
    h = sys.argv[1] if len(sys.argv) > 1 else None
    SimpleRangeTest(h).run()