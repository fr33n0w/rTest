#!/usr/bin/env python3
"""
Simple Reticulum Range Test Server - With Config
"""

import RNS
import time
import json
import os
import threading
from datetime import datetime

# Default configuration
DEFAULT_CONFIG = {
    "display_name": "RangeTest-BaseStation",
    "announce_interval": 180,  # seconds (3 minutes)
    "log_file": "range_test_server.json"
}

CONFIG_FILE = "server_config.json"

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

class SimpleServer:
    def __init__(self):
        # Load configuration
        self.config = load_config()
        
        print("🚀 Init server...")
        self.reticulum = RNS.Reticulum()
        
        if os.path.exists("rt_server_id"):
            self.identity = RNS.Identity.from_file("rt_server_id")
        else:
            self.identity = RNS.Identity()
            self.identity.to_file("rt_server_id")
        
        self.dest = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "rt")
        self.dest.set_packet_callback(self.got_packet)
        
        self.count = 0
        self.client_dests = {}  # Cache of client destinations
        self.running = False
        
        print(f"✓ Server hash: {self.dest.hash.hex()}")
        print(f"  Use this hash in client!")
        print(f"✓ Display name: {self.config['display_name']}")
        print(f"✓ Announce interval: {self.config['announce_interval']}s")
        
        # Initial announce
        print("📡 Announcing to network...")
        self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
        
        # Start announce thread
        self.announce_thread = threading.Thread(target=self.announce_loop, daemon=True)
        self.announce_thread.start()
    
    def announce_loop(self):
        """Announce periodically"""
        while self.running:
            time.sleep(self.config['announce_interval'])
            if self.running:
                self.dest.announce(app_data=self.config['display_name'].encode('utf-8'))
                print("\n[Auto-announced]")
    
    def got_packet(self, data, packet):
        try:
            msg = json.loads(data.decode())
            if msg.get('ping'):
                n = msg['ping']
                from_hash_hex = msg.get('from')
                self.count += 1
                
                print(f"← Ping #{n} from {from_hash_hex[:16] if from_hash_hex else '?'}... [{self.count}]")
                
                # Log ping
                with open(self.config['log_file'], 'a') as f:
                    f.write(json.dumps({
                        "ping": n,
                        "from": from_hash_hex,
                        "time": datetime.now().isoformat()
                    }) + '\n')
                
                # Reply
                if from_hash_hex:
                    from_hash = bytes.fromhex(from_hash_hex)
                    
                    # Get or cache client destination
                    client_dest = self.client_dests.get(from_hash_hex)
                    
                    if client_dest is None:
                        # Get identity and create destination
                        client_identity = RNS.Identity.recall(from_hash)
                        if client_identity:
                            client_dest = RNS.Destination(
                                client_identity,
                                RNS.Destination.OUT,
                                RNS.Destination.SINGLE,
                                "rt"
                            )
                            self.client_dests[from_hash_hex] = client_dest
                        else:
                            print(f"  ✗ Client identity unknown, requesting...")
                            RNS.Transport.request_path(from_hash)
                            return
                    
                    reply = json.dumps({"pong": n}).encode()
                    try:
                        p = RNS.Packet(client_dest, reply)
                        p.send()
                        print(f"→ Pong #{n}")
                    except Exception as e:
                        print(f"✗ Reply failed: {e}")
                        
        except Exception as e:
            print(f"✗ Parse error: {e}")
    
    def run(self):
        print("\n▶ Server running...")
        self.running = True
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print(f"\n⏹ Stopped. Handled {self.count} pings")
            print(f"📁 Log saved to: {self.config['log_file']}")
            self.running = False

if __name__ == "__main__":
    SimpleServer().run()