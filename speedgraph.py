#!/usr/bin/env python3
"""Plot internet speed history from a speedtracker.py CSV log."""

import argparse
import csv
import os
import sys
from datetime import datetime

try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.ticker as mticker
    from matplotlib.gridspec import GridSpec
    from matplotlib.patches import FancyBboxPatch
except ImportError:
    print("Missing dependency. Install with:\n  pip install matplotlib")
    sys.exit(1)

# ── Theme ─────────────────────────────────────────────────────────────────────
BG        = "#0f1117"
PANEL     = "#1a1d27"
GRID      = "#2a2d3a"
TEXT      = "#e0e0e0"
SUBTEXT   = "#8888aa"
C_DOWN    = "#4fc3f7"
C_UP      = "#81c784"
C_PING    = "#ffb74d"
C_JITTER  = "#ce93d8"
C_LOSS    = "#ef5350"


def apply_theme():
    plt.rcParams.update({
        "figure.facecolor":  BG,
        "axes.facecolor":    PANEL,
        "axes.edgecolor":    GRID,
        "axes.labelcolor":   SUBTEXT,
        "axes.titlecolor":   TEXT,
        "axes.titlesize":    13,
        "axes.titleweight":  "bold",
        "axes.titlepad":     10,
        "axes.labelsize":    11,
        "axes.grid":         True,
        "grid.color":        GRID,
        "grid.linewidth":    0.6,
        "xtick.color":       SUBTEXT,
        "ytick.color":       SUBTEXT,
        "xtick.labelsize":   10,
        "ytick.labelsize":   10,
        "text.color":        TEXT,
        "legend.facecolor":  PANEL,
        "legend.edgecolor":  GRID,
        "legend.labelcolor": TEXT,
        "legend.fontsize":   10,
        "lines.linewidth":   1.8,
        "lines.markersize":  4,
    })


def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "ts":       datetime.fromisoformat(row["timestamp"]),
                    "download": float(row["download_mbps"]),
                    "upload":   float(row["upload_mbps"]),
                    "ping":     float(row["ping_ms"]),
                    "jitter":   float(row["jitter_ms"])       if row.get("jitter_ms")       not in ("", None) else None,
                    "loss":     float(row["packet_loss_pct"]) if row.get("packet_loss_pct") not in ("", None) else None,
                    "server":   row.get("server_name", ""),
                    "url":      row.get("result_url", ""),
                })
            except (KeyError, ValueError):
                continue
    if not rows:
        print(f"No valid rows found in {path}")
        sys.exit(1)
    return sorted(rows, key=lambda r: r["ts"])


def _fmt_axes(ax):
    date_fmt = mdates.DateFormatter("%m/%d %H:%M")
    ax.xaxis.set_major_formatter(date_fmt)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)


def _stat_box(fig, x, y, label, value, color):
    """Draw a small stat card on the figure."""
    ax = fig.add_axes([x, y, 0.14, 0.055])
    ax.set_axis_off()
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, transform=ax.transAxes,
                                boxstyle="round,pad=0.05", facecolor=PANEL,
                                edgecolor=color, linewidth=1.2, clip_on=False))
    ax.text(0.5, 0.72, label, transform=ax.transAxes,
            ha="center", va="center", fontsize=9, color=SUBTEXT)
    ax.text(0.5, 0.28, value, transform=ax.transAxes,
            ha="center", va="center", fontsize=13, color=color, fontweight="bold")


def draw(fig, rows, title):
    fig.clear()
    apply_theme()
    fig.patch.set_facecolor(BG)

    timestamps = [r["ts"]      for r in rows]
    downloads  = [r["download"] for r in rows]
    uploads    = [r["upload"]   for r in rows]
    pings      = [r["ping"]     for r in rows]
    jitters    = [r["jitter"]   for r in rows]
    loss_ts    = [r["ts"]   for r in rows if r["loss"] is not None]
    loss_vals  = [r["loss"] for r in rows if r["loss"] is not None]
    has_jitter = any(j is not None for j in jitters)

    avg_dl   = sum(downloads) / len(downloads)
    avg_ul   = sum(uploads)   / len(uploads)
    avg_ping = sum(pings)     / len(pings)
    avg_loss = sum(loss_vals) / len(loss_vals) if loss_vals else 0.0
    avg_jit  = sum(j for j in jitters if j is not None) / max(sum(1 for j in jitters if j is not None), 1)
    max_dl   = max(downloads)
    min_dl   = min(downloads)

    # Title + subtitle
    fig.text(0.5, 0.965, title, ha="center", va="top",
             fontsize=18, fontweight="bold", color=TEXT)
    server_label = rows[-1]["server"] if rows[-1]["server"] else ""
    span = f"{timestamps[0].strftime('%b %d')} – {timestamps[-1].strftime('%b %d, %Y')}  ·  {len(rows)} samples"
    fig.text(0.5, 0.945, f"{span}   {('· ' + server_label) if server_label else ''}",
             ha="center", va="top", fontsize=10, color=SUBTEXT)

    # Stat cards row
    cards = [
        (0.06,  "AVG DOWNLOAD", f"{avg_dl:.1f} Mbps",  C_DOWN),
        (0.235, "AVG UPLOAD",   f"{avg_ul:.1f} Mbps",  C_UP),
        (0.41,  "AVG PING",     f"{avg_ping:.1f} ms",  C_PING),
        (0.585, "AVG JITTER",   f"{avg_jit:.1f} ms",   C_JITTER),
        (0.76,  "AVG LOSS",     f"{avg_loss:.2f}%",    C_LOSS),
    ]
    for x, label, value, color in cards:
        _stat_box(fig, x, 0.875, label, value, color)

    # Chart grid: 3 rows — speed | ping+jitter | loss
    gs = GridSpec(3, 1, figure=fig,
                  top=0.845, bottom=0.07,
                  hspace=0.55, left=0.07, right=0.97)

    # ── Download / Upload ─────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0])
    ax1.fill_between(timestamps, downloads, alpha=0.15, color=C_DOWN)
    ax1.fill_between(timestamps, uploads,   alpha=0.15, color=C_UP)
    ax1.plot(timestamps, downloads, color=C_DOWN, marker="o", label=f"Download  (max {max_dl:.0f} / min {min_dl:.0f} Mbps)")
    ax1.plot(timestamps, uploads,   color=C_UP,   marker="o", label=f"Upload")
    ax1.axhline(avg_dl, color=C_DOWN, linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.axhline(avg_ul, color=C_UP,   linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.set_ylabel("Mbps")
    ax1.set_title("Download & Upload")
    ax1.legend(loc="upper right")
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))
    _fmt_axes(ax1)

    # ── Ping + Jitter ─────────────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1])
    ax2.plot(timestamps, pings, color=C_PING, marker="o", label="Ping")
    ax2.axhline(avg_ping, color=C_PING, linewidth=0.8, linestyle="--", alpha=0.5)
    if has_jitter:
        jitter_clean = [j if j is not None else float("nan") for j in jitters]
        ax2.plot(timestamps, jitter_clean, color=C_JITTER, marker="o",
                 linewidth=1.2, linestyle="--", label="Jitter")
    ax2.set_ylabel("ms")
    ax2.set_title("Ping & Jitter")
    ax2.legend(loc="upper right")
    _fmt_axes(ax2)

    # ── Packet Loss ───────────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[2])
    if loss_ts:
        bar_width = max(
            (loss_ts[-1] - loss_ts[0]).total_seconds() / max(len(loss_ts), 1) * 0.6, 60
        ) / 86400
        bars = ax3.bar(loss_ts, loss_vals, width=bar_width, color=C_LOSS, alpha=0.85)
        # Colour bars by severity
        for bar, val in zip(bars, loss_vals):
            if val == 0:
                bar.set_color(C_UP)
                bar.set_alpha(0.5)
            elif val < 1:
                bar.set_color(C_PING)
                bar.set_alpha(0.8)
        ax3.set_ylim(0, max(max(loss_vals) * 1.3, 2))
        ax3.axhline(avg_loss, color=C_LOSS, linewidth=0.8, linestyle="--", alpha=0.6)
    else:
        ax3.text(0.5, 0.5, "No packet loss data available",
                 transform=ax3.transAxes, ha="center", va="center",
                 color=SUBTEXT, fontsize=9)
    ax3.set_ylabel("Loss %")
    ax3.set_title("Packet Loss  (green = 0%  ·  yellow = <1%  ·  red = ≥1%)")
    ax3.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    _fmt_axes(ax3)


def plot(rows, title, output):
    apply_theme()
    fig = plt.figure(figsize=(15, 10))
    draw(fig, rows, title)
    if output:
        plt.savefig(output, dpi=150, bbox_inches="tight", facecolor=BG)
        print(f"Saved to {output}")
    else:
        plt.show()


def live(csv_file, title, last, interval):
    from matplotlib.animation import FuncAnimation

    apply_theme()
    fig = plt.figure(figsize=(15, 10))
    print(f"Live mode: refreshing every {interval}s. Close the window to stop.")

    state = {"last_mtime": None}

    def update(_frame):
        try:
            mtime = os.path.getmtime(csv_file)
        except FileNotFoundError:
            return
        if mtime == state["last_mtime"]:
            return
        state["last_mtime"] = mtime
        try:
            rows = load_csv(csv_file)
        except SystemExit:
            return
        if last:
            rows = rows[-last:]
        draw(fig, rows, title)
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Chart updated ({len(rows)} samples)")

    update(None)

    _anim = FuncAnimation(fig, update, interval=interval * 1000, cache_frame_data=False)
    plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Plot internet speed history from a speedtracker.py CSV file."
    )
    parser.add_argument("csv_file", help="Path to the CSV log (e.g. speedlog.csv)")
    parser.add_argument("--title", "-t", default="Internet Speed History")
    parser.add_argument("--output", "-o", help="Save to file instead of displaying (e.g. chart.png)")
    parser.add_argument("--last",   "-n", type=int, help="Only plot the last N entries")
    parser.add_argument("--live",   "-l", action="store_true", help="Auto-refresh when CSV changes")
    parser.add_argument("--interval", "-i", type=int, default=30,
                        help="Seconds between file-change checks in live mode (default: 30)")
    args = parser.parse_args()

    if args.live:
        live(args.csv_file, args.title, args.last, args.interval)
        return

    rows = load_csv(args.csv_file)
    if args.last:
        rows = rows[-args.last:]
    plot(rows, args.title, args.output)


if __name__ == "__main__":
    main()
