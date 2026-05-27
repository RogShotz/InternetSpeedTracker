#!/usr/bin/env python3
"""Thin wrapper around the Ookla speedtest CLI: run periodically and record results."""

import argparse
import csv
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS    = sys.platform == "win32"
SPEEDTEST_EXE = os.path.join(SCRIPT_DIR, "ookla", "speedtest.exe") if IS_WINDOWS else None


PING_HOST = "8.8.8.8"
PING_PORT = 53
PING_TIMEOUT = 1.0  # seconds


def ping_once():
    """Return latency in ms if reachable, None if timed out / unreachable."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(PING_TIMEOUT)
        t0 = time.perf_counter()
        sock.connect((PING_HOST, PING_PORT))
        sock.close()
        return (time.perf_counter() - t0) * 1000
    except OSError:
        return None


def save_outage(outage, outage_file):
    file_exists = os.path.isfile(outage_file)
    with open(outage_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=outage.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(outage)


def monitor(speed_output, outage_output, fmt, speed_interval, extra_args):
    import threading

    print(f"Monitoring: pinging {PING_HOST} every second.")
    print(f"Speed test triggers: on outage recovery  OR  every {speed_interval // 60} minutes.")
    print("Press Ctrl+C to stop.\n")

    HIGH_LATENCY_MS    = 1000
    HIGH_LATENCY_STREAK = 3  # consecutive pings needed to trigger

    last_speed_test    = 0.0
    outage_start       = None
    high_latency_count = 0
    speedtest_running  = [False]

    def do_speedtest(reason):
        if speedtest_running[0]:
            return
        speedtest_running[0] = True
        try:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Speed test triggered: {reason}")
            result = run_once(extra_args, verbose=False)
            print_result(result)
            if speed_output:
                save_result(result, speed_output, fmt)
        except RuntimeError as e:
            if "RATE_LIMITED" in str(e):
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] Rate limited by Ookla — skipping test, will retry next interval.")
            elif "NO_CONNECTION" in str(e):
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] No connection during speed test — skipping.")
            else:
                print(f"  Speed test failed: {e}")
        except Exception as e:
            print(f"  Speed test failed: {e}")
        finally:
            speedtest_running[0] = False

    while True:
        try:
            now     = time.time()
            latency = ping_once()
            ts      = datetime.now().strftime("%H:%M:%S")

            if latency is None:
                # ── Outage ────────────────────────────────────────────────
                high_latency_count = 0
                if outage_start is None:
                    outage_start = datetime.now()
                    print(f"\n  [{ts}] OUTAGE DETECTED — connection lost", flush=True)
                else:
                    elapsed = (datetime.now() - outage_start).seconds
                    print(f"  [{ts}] Still down... ({elapsed}s)", flush=True)
            else:
                # ── Connected ─────────────────────────────────────────────
                if outage_start is not None:
                    # Recovery
                    outage_end = datetime.now()
                    duration   = round((outage_end - outage_start).total_seconds(), 1)
                    print(f"\n  [{ts}] Connection restored after {duration}s")
                    outage = {
                        "outage_start":     outage_start.isoformat(),
                        "outage_end":       outage_end.isoformat(),
                        "duration_seconds": duration,
                    }
                    save_outage(outage, outage_output)
                    print(f"  Outage logged to {outage_output}")
                    outage_start = None
                    threading.Thread(target=do_speedtest, args=("outage recovery",), daemon=True).start()
                    last_speed_test = now
                elif latency >= HIGH_LATENCY_MS:
                    high_latency_count += 1
                    print(f"\r  [{ts}] HIGH LATENCY  {latency:.0f}ms  ({high_latency_count}/{HIGH_LATENCY_STREAK})", end="", flush=True)
                    if high_latency_count >= HIGH_LATENCY_STREAK:
                        high_latency_count = 0
                        print()
                        threading.Thread(target=do_speedtest, args=(f"high latency ({latency:.0f}ms)",), daemon=True).start()
                        last_speed_test = now
                else:
                    high_latency_count = 0
                    print(f"\r  [{ts}] OK  {latency:.0f}ms    ", end="", flush=True)

            # ── Scheduled speed test ──────────────────────────────────────
            if latency is not None and (now - last_speed_test) >= speed_interval:
                last_speed_test = now
                threading.Thread(target=do_speedtest, args=("scheduled",), daemon=True).start()

            time.sleep(1)

        except KeyboardInterrupt:
            print("\nStopped.")
            break


def find_speedtest():
    if SPEEDTEST_EXE and os.path.isfile(SPEEDTEST_EXE):
        return SPEEDTEST_EXE
    found = shutil.which("speedtest")
    if found:
        return found
    if IS_WINDOWS:
        print(
            "Ookla speedtest CLI not found.\n"
            f"Place speedtest.exe in: {os.path.join(SCRIPT_DIR, 'ookla', 'speedtest.exe')}\n"
            "Or install via: winget install Ookla.Speedtest"
        )
    else:
        print(
            "Ookla speedtest CLI not found.\n"
            "Install via:\n"
            "  sudo apt-get install -y curl\n"
            "  curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | sudo bash\n"
            "  sudo apt-get install -y speedtest"
        )
    sys.exit(1)


def run_once(extra_args, verbose=True):
    if verbose:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Running speed test...", flush=True)

    cmd = [find_speedtest(), "--format=json", "--accept-license", "--accept-gdpr"] + extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if proc.returncode != 0:
        err = proc.stderr.strip()
        if "Limit reached" in err or "Too many requests" in err:
            raise RuntimeError("RATE_LIMITED")
        if "HostNotFoundException" in err or "ConfigurationError" in err or "WSA Error" in err:
            raise RuntimeError("NO_CONNECTION")
        raise RuntimeError(f"speedtest CLI failed:\n{err}")

    res = json.loads(proc.stdout)

    # Flatten the nested JSON into a single record for easy CSV storage
    server = res.get("server", {})
    ping   = res.get("ping", {})
    dl     = res.get("download", {})
    ul     = res.get("upload", {})

    return {
        "timestamp":        datetime.now().isoformat(),
        "download_mbps":    round(dl.get("bandwidth", 0) * 8 / 1_000_000, 2),
        "upload_mbps":      round(ul.get("bandwidth", 0) * 8 / 1_000_000, 2),
        "ping_ms":          ping.get("latency"),
        "jitter_ms":        ping.get("jitter"),
        "packet_loss_pct":  res.get("packetLoss"),
        "server_id":        server.get("id"),
        "server_name":      server.get("name"),
        "server_location":  server.get("location"),
        "server_country":   server.get("country"),
        "result_url":       res.get("result", {}).get("url"),
    }


def print_result(r):
    loss = f"{r['packet_loss_pct']:.2f}%" if r["packet_loss_pct"] is not None else "N/A"
    jitter = f"{r['jitter_ms']:.2f} ms" if r["jitter_ms"] is not None else "N/A"
    print(f"  Download:    {r['download_mbps']:.2f} Mbps")
    print(f"  Upload:      {r['upload_mbps']:.2f} Mbps")
    print(f"  Ping:        {r['ping_ms']:.2f} ms  (jitter: {jitter})")
    print(f"  Packet Loss: {loss}")
    if r["server_name"]:
        print(f"  Server:      {r['server_name']}, {r['server_location']} ({r['server_country']})")
    if r["result_url"]:
        print(f"  Result URL:  {r['result_url']}")


def save_result(r, output_file, fmt):
    file_exists = os.path.isfile(output_file)
    if fmt == "csv":
        with open(output_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=r.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(r)
    else:
        rows = []
        if file_exists:
            with open(output_file) as f:
                try:
                    rows = json.load(f)
                except json.JSONDecodeError:
                    rows = []
        rows.append(r)
        with open(output_file, "w") as f:
            json.dump(rows, f, indent=2)
    print(f"  Saved to {output_file}")


def show_history(output_file, fmt, limit):
    if not os.path.isfile(output_file):
        print("No history file found.")
        return
    if fmt == "csv":
        with open(output_file) as f:
            rows = list(csv.DictReader(f))
    else:
        with open(output_file) as f:
            rows = json.load(f)

    rows = rows[-limit:]
    print(f"\n{'Timestamp':<22} {'DL (Mbps)':>10} {'UL (Mbps)':>10} {'Ping (ms)':>10} {'Jitter':>8} {'Loss':>7}")
    print("-" * 74)
    for r in rows:
        loss   = f"{float(r['packet_loss_pct']):.1f}%" if r.get("packet_loss_pct") not in (None, "") else "N/A"
        jitter = f"{float(r['jitter_ms']):.1f}ms"      if r.get("jitter_ms")       not in (None, "") else "N/A"
        print(
            f"{str(r['timestamp'])[:19]:<22}"
            f"{float(r['download_mbps']):>10.2f}"
            f"{float(r['upload_mbps']):>10.2f}"
            f"{float(r['ping_ms']):>10.2f}"
            f"{jitter:>8}"
            f"{loss:>7}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Run the Ookla speedtest CLI periodically and record results.",
        epilog="Any unrecognised arguments are passed directly to the speedtest binary."
    )
    subparsers = parser.add_subparsers(dest="command")

    run_p = subparsers.add_parser("run", help="Run a single speed test")
    run_p.add_argument("--output", "-o", help="File to save result to")
    run_p.add_argument("--format", "-f", choices=["csv", "json"], default="csv")
    run_p.add_argument("--json", action="store_true", help="Print result as JSON")

    watch_p = subparsers.add_parser("watch", help="Run speed tests repeatedly")
    watch_p.add_argument("--interval", "-i", type=int, default=300, help="Seconds between tests (default: 300)")
    watch_p.add_argument("--output", "-o", help="File to append results to")
    watch_p.add_argument("--format", "-f", choices=["csv", "json"], default="csv")

    mon_p = subparsers.add_parser("monitor", help="Ping every second, speed test on outage or schedule")
    mon_p.add_argument("--output",  "-o", default="speedlog.csv",  help="Speed test results file (default: speedlog.csv)")
    mon_p.add_argument("--outages", "-O", default="outages.csv",   help="Outage log file (default: outages.csv)")
    mon_p.add_argument("--format",  "-f", choices=["csv", "json"], default="csv")
    mon_p.add_argument("--interval","-i", type=int, default=900,   help="Scheduled speed test interval in seconds (default: 900 = 15 min)")

    hist_p = subparsers.add_parser("history", help="Show saved results")
    hist_p.add_argument("--output", "-o", default="speedlog.csv")
    hist_p.add_argument("--format", "-f", choices=["csv", "json"], default="csv")
    hist_p.add_argument("--limit", "-n", type=int, default=10)

    args, extra = parser.parse_known_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "monitor":
        monitor(args.output, args.outages, args.format, args.interval, extra)
        return

    if args.command == "history":
        show_history(args.output, args.format, args.limit)
        return

    if args.command == "run":
        try:
            result = run_once(extra)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print_result(result)
            if args.output:
                save_result(result, args.output, args.format)
        except RuntimeError as e:
            if "RATE_LIMITED" in str(e):
                print("Rate limited by Ookla — try again in a few minutes.")
            elif "NO_CONNECTION" in str(e):
                print("No connection — check your internet and try again.")
            else:
                print(e)

    elif args.command == "watch":
        print(f"Running every {args.interval}s. Press Ctrl+C to stop.")
        while True:
            try:
                result = run_once(extra)
                print_result(result)
                if args.output:
                    save_result(result, args.output, args.format)
                print(f"\n  Next test in {args.interval}s...")
                time.sleep(args.interval)
            except RuntimeError as e:
                if "RATE_LIMITED" in str(e):
                    print(f"  Rate limited by Ookla — skipping, next test in {args.interval}s.")
                elif "NO_CONNECTION" in str(e):
                    print(f"  No connection during speed test — skipping, next test in {args.interval}s.")
                else:
                    print(f"  Error: {e}")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped.")
                break


if __name__ == "__main__":
    main()
