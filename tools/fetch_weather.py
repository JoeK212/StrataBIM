#!/usr/bin/env python3
"""Download one week of hourly NYC weather from Open-Meteo and save data/nyc_weather.json.

Usage:
  python3 tools/fetch_weather.py
  python3 tools/fetch_weather.py --start 2025-10-06 --days 7 --out data/nyc_weather.json

Start should be a Monday so the week lines up with the STRATA timeline (Mon to Sun).
Open-Meteo's free tier is for non-commercial use; check their terms before using
this in client work.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

LAT = 40.7794
LON = -73.9632
URL = "https://archive-api.open-meteo.com/v1/archive"


def build(resp, start, days):
    h = resp.get("hourly") or {}
    need = ["time", "temperature_2m", "relative_humidity_2m", "shortwave_radiation"]
    for k in need:
        if k not in h:
            raise ValueError("response is missing hourly." + k)
    n = days * 24
    if len(h["time"]) != n:
        raise ValueError("expected %d hourly rows, got %d" % (n, len(h["time"])))

    def clean(vals, nd):
        out = []
        last = None
        for v in vals:
            if v is None:
                v = last
            if v is not None:
                v = round(float(v), nd)
                last = v
            out.append(v)
        first = next((v for v in out if v is not None), 0.0)
        return [first if v is None else v for v in out]

    return {
        "meta": {
            "source": "Open-Meteo archive API",
            "lat": LAT,
            "lon": LON,
            "place": "Central Park area, New York City",
            "start": start.isoformat() + "T00:00",
            "days": days,
            "step_min": 60,
            "timezone": "America/New_York",
            "generated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "tempC": clean(h["temperature_2m"], 1),
        "rh": clean(h["relative_humidity_2m"], 0),
        "solarWm2": clean(h["shortwave_radiation"], 0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-10-06")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="data/nyc_weather.json")
    a = ap.parse_args()
    start = date.fromisoformat(a.start)
    if start.weekday() != 0:
        print("Warning: %s is not a Monday; the STRATA timeline starts on Monday." % a.start)
    end = start + timedelta(days=a.days - 1)
    q = urllib.parse.urlencode({
        "latitude": LAT,
        "longitude": LON,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "temperature_2m,relative_humidity_2m,shortwave_radiation",
        "timezone": "America/New_York",
    })
    print("Requesting", URL + "?" + q)
    try:
        with urllib.request.urlopen(URL + "?" + q, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        sys.exit("Download failed: %s" % e)
    data = build(resp, start, a.days)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    t = data["tempC"]
    print("Wrote %s: %d hours, %.1f to %.1f C" % (a.out, len(t), min(t), max(t)))


if __name__ == "__main__":
    main()
