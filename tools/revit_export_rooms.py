"""STRATA Room exporter for Dynamo (Revit, CPython3 Python Script node).

Paste this whole file into a Python Script node set to the CPython3 engine.

Inputs (both optional):
  IN[0]  output file path as a string, for example C:/Users/you/Desktop/strata_model.json
         Default: strata_model.json on the Desktop.
  IN[1]  grouping mode, one of:
           "auto"        STRATA_Zone parameter, else Department, else one zone per Room (default)
           "param"       STRATA_Zone parameter only
           "department"  Department only
           "room"        one zone per Room
Output:
  OUT    a short text summary of what was exported and what was skipped.

What it reads: every placed, enclosed Room in the open document. It does not
modify the model and opens no transaction.

Optional Room text parameters (create them as project parameters on the Rooms category):
  STRATA_Zone    rooms with the same value on the same level become one coloured zone
  STRATA_Sensor  a sensor ID to attach to the zone (shown in the viewer, used later for live data)

Units: the file is in metres and square metres; Revit's internal feet are converted here.
Coordinates are Revit internal coordinates (x east, y north); the viewer re-centres the model.
"""
import json
import math
import os
from datetime import datetime

FT = 0.3048
SQFT = 0.09290304
SCHEMA = "strata-model-1"
MIN_AREA_M2 = 2.0
PARAM_ZONE = "STRATA_Zone"
PARAM_SENSOR = "STRATA_Sensor"
MIN_LEVEL_H = 2.4
MAX_LEVEL_H = 6.0
DEFAULT_LEVEL_H = 3.5


def r3(v):
    return round(float(v), 3)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def poly_area(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def chain_loop(curves):
    """Join the tessellated curves of one boundary loop into one ring of (x, y) points in metres.

    Each curve is a list of (x, y). Curves can come back reversed, so each one is flipped
    when its far end is the one that touches the ring built so far.
    """
    curves = [list(c) for c in curves if len(c) >= 2]
    if not curves:
        return []
    if len(curves) > 1:
        c0, c1 = curves[0], curves[1]
        d_end = min(dist(c0[-1], c1[0]), dist(c0[-1], c1[-1]))
        d_start = min(dist(c0[0], c1[0]), dist(c0[0], c1[-1]))
        if d_start < d_end:
            curves[0].reverse()
    pts = []
    for c in curves:
        if pts and dist(pts[-1], c[0]) > dist(pts[-1], c[-1]):
            c.reverse()
        if pts and dist(pts[-1], c[0]) < 1e-3:
            c = c[1:]
        pts.extend(c)
    ring = []
    for p in pts:
        if not ring or dist(ring[-1], p) > 1e-3:
            ring.append(p)
    if len(ring) > 1 and dist(ring[0], ring[-1]) < 1e-3:
        ring.pop()
    return ring if len(ring) >= 3 and poly_area(ring) > 1e-4 else []


def split_loops(loops):
    """First the outer boundary (largest area), then holes (columns, courtyards)."""
    rings = [r for r in loops if len(r) >= 3]
    if not rings:
        return None, []
    rings.sort(key=poly_area, reverse=True)
    return rings[0], rings[1:]


def level_table(rooms):
    """Sorted unique levels with a plausible storey height for each."""
    seen = {}
    for r in rooms:
        key = (r["level"], round(r["elev"], 3))
        seen[key] = max(seen.get(key, 0.0), r.get("height_hint", 0.0))
    keys = sorted(seen, key=lambda k: k[1])
    heights = []
    for i, k in enumerate(keys):
        if i + 1 < len(keys):
            heights.append(min(MAX_LEVEL_H, max(MIN_LEVEL_H, keys[i + 1][1] - k[1])))
        else:
            heights.append(None)
    known = sorted(h for h in heights if h is not None)
    if heights and heights[-1] is None:
        if known:
            top = known[len(known) // 2]
        else:
            hint = seen[keys[-1]]
            top = min(MAX_LEVEL_H, max(MIN_LEVEL_H, hint)) if hint else DEFAULT_LEVEL_H
        heights[-1] = top
    levels = [{"name": k[0], "elevation": r3(k[1]), "height": r3(h)} for k, h in zip(keys, heights)]
    index = {k: i for i, k in enumerate(keys)}
    return levels, index


def zone_name_for(room, mode):
    if mode in ("auto", "param") and room.get("zone"):
        return room["zone"]
    if mode in ("auto", "department") and room.get("department"):
        return room["department"]
    return None


def build_model(project, rooms, mode="auto"):
    """rooms: plain dicts, see read_rooms(). Returns (model dict, stats dict)."""
    stats = {"rooms_in": len(rooms), "rooms_out": 0, "bad_boundary": 0, "tiny": 0}
    usable = []
    for r in rooms:
        outer, holes = split_loops(r["loops"])
        if outer is None:
            stats["bad_boundary"] += 1
            continue
        area = r["area"] if r["area"] > 0 else poly_area(outer) - sum(poly_area(h) for h in holes)
        if area < MIN_AREA_M2:
            stats["tiny"] += 1
            continue
        usable.append((r, outer, holes, area))
    levels, lindex = level_table([u[0] for u in usable])
    zones = {}
    order = []
    for r, outer, holes, area in usable:
        li = lindex[(r["level"], round(r["elev"], 3))]
        name = zone_name_for(r, mode)
        if name is None:
            key = (li, "room:" + r["id"])
            label = ((r.get("number") or "") + " " + (r.get("name") or "")).strip() or "Room"
        else:
            key = (li, "zone:" + name)
            label = name
        if key not in zones:
            zones[key] = {
                "id": "%s::%s" % (levels[li]["name"], key[1]),
                "name": label,
                "level": li,
                "sensor": "",
                "area": 0.0,
                "rooms": [],
            }
            order.append(key)
        z = zones[key]
        if r.get("sensor") and not z["sensor"]:
            z["sensor"] = r["sensor"]
        z["area"] += area
        z["rooms"].append({
            "id": r["id"],
            "number": r.get("number", ""),
            "name": r.get("name", ""),
            "area": r3(area),
            "boundary": [[r3(x), r3(y)] for x, y in outer],
            "holes": [[[r3(x), r3(y)] for x, y in h] for h in holes],
        })
        stats["rooms_out"] += 1
    out = []
    for k in order:
        z = zones[k]
        z["area"] = r3(z["area"])
        out.append(z)
    out.sort(key=lambda z: (z["level"], z["name"]))
    model = {
        "schema": SCHEMA,
        "project": project,
        "units": "m",
        "exported": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grouping": mode,
        "levels": levels,
        "zones": out,
    }
    stats["zones"] = len(out)
    stats["levels"] = len(levels)
    return model, stats


def text_param(el, name):
    try:
        p = el.LookupParameter(name)
        if p is None or not p.HasValue:
            return ""
        return (p.AsString() or "").strip()
    except Exception:
        return ""


def built_in_text(el, bip):
    try:
        p = el.get_Parameter(bip)
        if p is None or not p.HasValue:
            return ""
        return (p.AsString() or "").strip()
    except Exception:
        return ""


def read_rooms(doc, api):
    """Read every placed Room into a plain dict. api is Autodesk.Revit.DB."""
    opt = api.SpatialElementBoundaryOptions()
    opt.SpatialElementBoundaryLocation = api.SpatialElementBoundaryLocation.Finish
    col = api.FilteredElementCollector(doc).OfCategory(api.BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
    rooms = []
    skipped = {"unplaced": 0, "no_level": 0, "no_boundary": 0}
    for r in col:
        try:
            if r.Location is None or r.Area <= 0:
                skipped["unplaced"] += 1
                continue
            lvl = doc.GetElement(r.LevelId)
            if lvl is None:
                skipped["no_level"] += 1
                continue
            segs = r.GetBoundarySegments(opt)
            if segs is None:
                skipped["no_boundary"] += 1
                continue
            loops = []
            for loop in segs:
                curves = []
                for seg in loop:
                    pts = [(p.X * FT, p.Y * FT) for p in seg.GetCurve().Tessellate()]
                    curves.append(pts)
                loops.append(chain_loop(curves))
            try:
                hint = float(r.UnboundedHeight) * FT
            except Exception:
                hint = 0.0
            rooms.append({
                "id": str(r.UniqueId),
                "number": str(r.Number or ""),
                "name": built_in_text(r, api.BuiltInParameter.ROOM_NAME),
                "department": built_in_text(r, api.BuiltInParameter.ROOM_DEPARTMENT),
                "zone": text_param(r, PARAM_ZONE),
                "sensor": text_param(r, PARAM_SENSOR),
                "level": str(lvl.Name),
                "elev": float(lvl.Elevation) * FT,
                "area": float(r.Area) * SQFT,
                "height_hint": hint,
                "loops": loops,
            })
        except Exception as e:
            skipped["no_boundary"] += 1
    return rooms, skipped


def default_path():
    base = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(base):
        base = os.path.expanduser("~")
    return os.path.join(base, "strata_model.json")


def run(inputs, api=None, doc=None):
    path = inputs[0] if len(inputs) > 0 and inputs[0] else default_path()
    mode = inputs[1] if len(inputs) > 1 and inputs[1] else "auto"
    if mode not in ("auto", "param", "department", "room"):
        return "Unknown grouping mode '%s'. Use auto, param, department or room." % mode
    if api is None:
        import clr
        clr.AddReference("RevitAPI")
        clr.AddReference("RevitServices")
        from Autodesk.Revit import DB as api
        from RevitServices.Persistence import DocumentManager
        doc = DocumentManager.Instance.CurrentDBDocument
    rooms, skipped = read_rooms(doc, api)
    if not rooms:
        return "No placed, enclosed Rooms found. Place Rooms (Architecture > Room) and try again. Skipped: %s" % skipped
    model, stats = build_model(str(doc.Title), rooms, mode)
    if not model["zones"]:
        return "Rooms were found but none were usable. Stats: %s" % stats
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(model, f, separators=(",", ":"))
    except Exception as e:
        return "Could not write %s: %s" % (path, e)
    size = os.path.getsize(path) / 1024.0
    lines = [
        "Wrote %s (%.0f KB)" % (path, size),
        "%d levels, %d zones, %d rooms (grouping: %s)" % (stats["levels"], stats["zones"], stats["rooms_out"], mode),
    ]
    bad = stats["bad_boundary"] + stats["tiny"] + sum(skipped.values())
    if bad:
        lines.append("Skipped: %d unplaced or not enclosed, %d without a usable boundary, %d under %.0f m2" % (
            skipped["unplaced"] + skipped["no_level"], stats["bad_boundary"] + skipped["no_boundary"], stats["tiny"], MIN_AREA_M2))
    if stats["zones"] > 400:
        lines.append("Warning: %d zones is a lot. Group rooms with %s or Department for a faster dashboard." % (stats["zones"], PARAM_ZONE))
    return "\n".join(lines)


if "IN" in globals():
    OUT = run(list(IN))
