# Internet Speed Tracker

A lightweight Python wrapper around the official **Ookla Speedtest CLI** that monitors your internet connection, detects outages, and visualizes results over time.

---

## Features

- **1-second ping monitoring** — detects outages and high latency the moment they happen
- **Automatic speed tests** — triggered on outage recovery, sustained high latency (3× >1000ms), or every 15 minutes
- **Full Ookla accuracy** — uses the official CLI binary so results match speedtest.net
- **Outage logging** — records start time, end time, and duration of every outage
- **Live graphs** — dark-themed dashboard showing download, upload, ping, jitter, and packet loss
- **Rate limit handling** — gracefully skips tests when Ookla throttles requests

---

## Requirements

- Python 3.8+
- `pip install matplotlib`
- Ookla Speedtest CLI — see install instructions below

### Installing the Ookla CLI

**Windows** — place `speedtest.exe` in `ookla/speedtest.exe`, or:
```powershell
winget install Ookla.Speedtest
```

**Ubuntu / Debian:**
```bash
sudo apt-get install -y curl
curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | sudo bash
sudo apt-get install -y speedtest
```

---

## Usage

**Monitor mode** *(recommended)* — pings every second, auto speed tests:
```bash
python speedtracker.py monitor -o speedlog.csv -O outages.csv
```

**Single speed test:**
```bash
python speedtracker.py run -o speedlog.csv
```

**Scheduled speed tests** (every N seconds):
```bash
python speedtracker.py watch -o speedlog.csv --interval 900
```

**View recent results:**
```bash
python speedtracker.py history -o speedlog.csv
```

**Graph results:**
```bash
python speedgraph.py speedlog.csv
```

**Live-updating graph** (while monitor is running):
```bash
python speedgraph.py speedlog.csv --live
```

Any unrecognised flags are passed directly to the Ookla CLI — e.g. `--server-id 1234`.

---

## Output Files

| File | Contents |
|---|---|
| `speedlog.csv` | Download, upload, ping, jitter, packet loss per test |
| `outages.csv` | Outage start, end, and duration |
