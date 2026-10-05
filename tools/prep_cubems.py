#!/usr/bin/env python3
"""Cut one week out of the CU-BEMS CSVs and write a compact JSON feed for STRATA.

Usage:
  python3 tools/prep_cubems.py --input ~/Downloads/cubems --inspect
  python3 tools/prep_cubems.py --input ~/Downloads/cubems --start 2019-03-04 --days 7 --step 10

--input   a folder of CU-BEMS CSV files (searched recursively) or a single CSV
--start   first day of the window, YYYY-MM-DD. Use a Monday.
--step    minutes per output sample (default 10). The raw data is 1 minute.
--inspect print how every column is classified, then stop. Run this first.

Each CSV is expected to have a date/time column first, then columns named like
z1_AC1(kW), z1_Light(kW), z1_Plug(kW), z1_S1(degC), z1_S1(RH%), z1_S1(lux).
The floor number is read from the file name (for example 2019Floor3.csv).
Column names are matched loosely; run --inspect to see what was recognised.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta

FORMATS = [
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
]
POWER = ("ac", "light", "plug")
SENSOR = ("temp", "rh", "lux")
ROUND = {"ac": 3, "light": 3, "plug": 3, "temp": 2, "rh": 1, "lux": 0}
_fmt_cache = [None]


def parse_dt(s):
    s = s.strip()
    if _fmt_cache[0]:
        try:
            return datetime.strptime(s, _fmt_cache[0])
        except ValueError:
            pass
    for f in FORMATS:
        try:
            d = datetime.strptime(s, f)
            _fmt_cache[0] = f
            return d
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def classify(col):
    m = re.match(r"^\s*z(\d+)[_\s-]*(.*)$", col, re.I)
    if not m:
        return None
    zone = int(m.group(1))
    rest = m.group(2).lower()
    if "lux" in rest:
        ch = "lux"
    elif "humid" in rest or re.search(r"\brh\b|rh%|\(rh", rest):
        ch = "rh"
    elif "degc" in rest or "temp" in rest or "(c)" in rest:
        ch = "temp"
    elif "light" in rest:
        ch = "light"
    elif "plug" in rest:
        ch = "plug"
    elif re.match(r"^ac", rest):
        ch = "ac"
    else:
        return None
    return zone, ch


def floor_of(path):
    m = re.search(r"floor[\s_-]*(\d+)", os.path.basename(path), re.I)
    return int(m.group(1)) if m else None


def find_files(inp):
    if os.path.isfile(inp):
        return [inp]
    files = glob.glob(os.path.join(inp, "**", "*.csv"), recursive=True)
    return sorted(files)


def inspect(files):
    for p in files:
        with open(p, newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            head = next(r, [])
            first = next(r, [])
        fl = floor_of(p)
        print("\n%s  (floor %s)" % (os.path.basename(p), fl if fl is not None else "NOT FOUND IN FILE NAME"))
        print("  first column:", head[0] if head else "?", "| first value:", first[0] if first else "?",
              "| parsed:", parse_dt(first[0]) if first else None)
        counts = {}
        unknown = []
        for c in head[1:]:
            k = classify(c)
            if k is None:
                unknown.append(c)
            else:
                counts.setdefault(k[0], {}).setdefault(k[1], 0)
                counts[k[0]][k[1]] += 1
        for z in sorted(counts):
            print("  zone %-3d %s" % (z, ", ".join("%s x%d" % (k, v) for k, v in sorted(counts[z].items()))))
        if unknown:
            print("  not recognised:", ", ".join(unknown[:12]) + (" ..." if len(unknown) > 12 else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--start", default="2019-03-04")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--out", default="data/cubems_week.json")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()

    files = find_files(a.input)
    if not files:
        sys.exit("No CSV files found in " + a.input)
    if a.inspect:
        inspect(files)
        return

    start = datetime.strptime(a.start, "%Y-%m-%d")
    if start.weekday() != 0:
        print("Warning: %s is not a Monday; STRATA labels the timeline Monday to Sunday." % a.start)
    end = start + timedelta(days=a.days)
    n = a.days * 1440 // a.step
    years = {start.year, (end - timedelta(minutes=1)).year}

    sums = {}
    cnts = {}
    rows_used = 0
    for p in files:
        yr = re.search(r"(20\d\d)", os.path.basename(p))
        if yr and int(yr.group(1)) not in years:
            continue
        fl = floor_of(p)
        if fl is None:
            print("Skipping %s: no 'Floor<number>' in the file name" % os.path.basename(p))
            continue
        with open(p, newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            head = next(r, [])
            cols = []
            for i, c in enumerate(head):
                if i == 0:
                    continue
                k = classify(c)
                if k:
                    cols.append((i, fl, k[0], k[1]))
            if not cols:
                print("Skipping %s: no recognised columns (run --inspect)" % os.path.basename(p))
                continue
            used = 0
            for row in r:
                if not row:
                    continue
                dt = parse_dt(row[0])
                if dt is None or dt < start or dt >= end:
                    continue
                idx = int((dt - start).total_seconds() // 60) // a.step
                if idx >= n:
                    continue
                rv = {}
                for i, fl_, z, ch in cols:
                    if i >= len(row):
                        continue
                    try:
                        v = float(row[i])
                    except ValueError:
                        continue
                    if v != v:
                        continue
                    s = rv.setdefault((fl_, z, ch), [0.0, 0])
                    s[0] += v
                    s[1] += 1
                for key, (sv, c) in rv.items():
                    val = sv if key[2] in POWER else sv / c
                    if key not in sums:
                        sums[key] = [0.0] * n
                        cnts[key] = [0] * n
                    sums[key][idx] += val
                    cnts[key][idx] += 1
                used += 1
            rows_used += used
            print("%s: %d rows in window" % (os.path.basename(p), used))

    if not sums:
        sys.exit("No data found between %s and %s. Check --start and the file names." % (start.date(), end.date()))

    zones = {}
    for (fl, z, ch), s in sums.items():
        c = cnts[(fl, z, ch)]
        series = [(s[i] / c[i]) if c[i] else None for i in range(n)]
        have = sum(1 for v in series if v is not None)
        last = None
        for i in range(n):
            if series[i] is None:
                series[i] = last
            else:
                last = series[i]
        first = next((v for v in series if v is not None), 0.0)
        series = [first if v is None else v for v in series]
        zd = zones.setdefault((fl, z), {"id": "F%d-Z%d" % (fl, z), "floor": fl, "zone": z, "coverage": {}})
        zd[ch] = [round(v, ROUND[ch]) for v in series]
        zd["coverage"][ch] = round(have / n, 3)

    out_zones = [zones[k] for k in sorted(zones)]
    meta = {
        "source": "CU-BEMS, Chulalongkorn University (Bangkok), Scientific Data 2020",
        "start": start.strftime("%Y-%m-%dT%H:%M"),
        "days": a.days,
        "step_min": a.step,
        "samples": n,
        "zones": len(out_zones),
        "floors": len({z["floor"] for z in out_zones}),
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "zones": out_zones}, f, separators=(",", ":"))

    per_floor = {}
    for z in out_zones:
        per_floor[z["floor"]] = per_floor.get(z["floor"], 0) + 1
    print("\nWrote %s (%.1f KB)" % (a.out, os.path.getsize(a.out) / 1024))
    print("Zones per floor:", ", ".join("F%d=%d" % (k, per_floor[k]) for k in sorted(per_floor)), "| total", len(out_zones))
    total = [0.0] * n
    for z in out_zones:
        for ch in POWER:
            if ch in z:
                for i, v in enumerate(z[ch]):
                    total[i] += v
    print("Building power: peak %.0f kW, mean %.0f kW" % (max(total), sum(total) / n))
    low = [(z["id"], ch, c) for z in out_zones for ch, c in z["coverage"].items() if c < 0.9]
    if low:
        print("Channels with under 90%% of samples present (gaps were forward-filled): %d" % len(low))
        for x in low[:10]:
            print("  %s %s %.0f%%" % (x[0], x[1], x[2] * 100))


if __name__ == "__main__":
    main()
