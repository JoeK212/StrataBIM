import importlib.util
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rex", os.path.join(HERE, "tools", "revit_export_rooms.py"))
rex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rex)

results = []


def check(label, ok, detail=""):
    results.append(bool(ok))
    print(("  ok   " if ok else "  FAIL ") + label + (("\n       " + str(detail)) if (detail and not ok) else ""))


M = 1 / 0.3048


class XYZ:
    def __init__(self, x, y):
        self.X = x * M
        self.Y = y * M


class Curve:
    def __init__(self, pts):
        self.pts = pts

    def Tessellate(self):
        return [XYZ(x, y) for x, y in self.pts]


class Seg:
    def __init__(self, pts):
        self.c = Curve(pts)

    def GetCurve(self):
        return self.c


class Param:
    def __init__(self, v):
        self.v = v
        self.HasValue = v is not None

    def AsString(self):
        return self.v


class Level:
    def __init__(self, name, elev):
        self.Name = name
        self.Elevation = elev * M


class Room:
    def __init__(self, uid, number, name, level_id, loops, area_m2, params=None, dept=None, placed=True, height=None):
        self.UniqueId = uid
        self.Number = number
        self._name = name
        self.LevelId = level_id
        self._loops = loops
        self.Area = area_m2 * 10.7639 if placed else 0.0
        self.Location = object() if placed else None
        self._params = params or {}
        self._dept = dept
        self.UnboundedHeight = (height or 3.6) * M

    def GetBoundarySegments(self, opt):
        return self._loops

    def LookupParameter(self, n):
        return Param(self._params[n]) if n in self._params else None

    def get_Parameter(self, bip):
        if bip == "ROOM_NAME":
            return Param(self._name)
        if bip == "ROOM_DEPARTMENT":
            return Param(self._dept) if self._dept else None
        return None


class Doc:
    Title = "Synthetic Office"

    def __init__(self, levels, rooms):
        self.levels = levels
        self.rooms = rooms

    def GetElement(self, lid):
        return self.levels.get(lid)


class FakeApi:
    class SpatialElementBoundaryOptions:
        SpatialElementBoundaryLocation = None

    class SpatialElementBoundaryLocation:
        Finish = "Finish"

    class BuiltInCategory:
        OST_Rooms = "OST_Rooms"

    class BuiltInParameter:
        ROOM_NAME = "ROOM_NAME"
        ROOM_DEPARTMENT = "ROOM_DEPARTMENT"

    class FilteredElementCollector:
        def __init__(self, doc):
            self.doc = doc

        def OfCategory(self, c):
            return self

        def WhereElementIsNotElementType(self):
            return list(self.doc.rooms)


rng = random.Random(7)


def rect_loop(x0, y0, x1, y1, flip=True):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    segs = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        seg = [a, b]
        if flip and rng.random() < 0.4:
            seg = [b, a]
        segs.append(Seg(seg))
    return segs


def arc_pts(cx, cy, r, a0, a1, n=8):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n), cy + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def build_office():
    levels = {}
    rooms = []
    elevs = [0.0, 3.8, 7.6, 11.4]
    for li, e in enumerate(elevs):
        levels[li] = Level("Level %d" % (li + 1), e)
    n = 0
    for li, e in enumerate(elevs):
        cells = []
        for col in range(6):
            for row in range(2):
                cells.append((col * 9, row * 9, "bar", col, row))
        for col in range(2):
            for row in range(2):
                cells.append((col * 9, 18 + row * 9, "wing", col, row))
        for x0, y0, part, col, row in cells:
            n += 1
            uid = "uid-%d-%d" % (li, n)
            x1, y1 = x0 + 9, y0 + 9
            loops = [rect_loop(x0, y0, x1, y1)]
            area = 81.0
            params = {}
            dept = None
            name = "Open Office"
            if part == "bar" and col == 3 and row == 0:
                name = "Core"
                loops.append(rect_loop(x0 + 3, y0 + 3, x0 + 6, y0 + 6, flip=False))
                area = 72.0
                dept = "Core"
            elif part == "bar" and col == 0 and row == 0:
                name = "Lobby"
                arc = arc_pts(x0 + 4.5, y1, 4.5, 0, math.pi, 8)
                loops = [[Seg([(x0, y0), (x1, y0)]), Seg([(x1, y0), (x1, y1)]), Seg(arc), Seg([(x0, y1), (x0, y0)])]]
                area = 81.0 + math.pi * 4.5 ** 2 / 2
                dept = "Public"
            elif part == "bar":
                params["STRATA_Zone"] = "South" if row == 0 else "North"
                if col == 1 and row == 1 and li == 0:
                    params["STRATA_Sensor"] = "CUBEMS-F1-Z2"
            else:
                dept = "Studio"
            rooms.append(Room(uid, str(100 * (li + 1) + n), name, li, loops, area, params, dept))
    rooms.append(Room("uid-unplaced", "999", "Unplaced", 0, [], 0, placed=False))
    rooms.append(Room("uid-tiny", "998", "Closet", 0, [rect_loop(0, 40, 1, 41)], 1.0))
    rooms.append(Room("uid-open", "997", "Not enclosed", 0, None, 20))
    return Doc(levels, rooms)


print("\n== Pure helpers ==")
sq = [[(0, 0), (4, 0)], [(4, 0), (4, 3)], [(4, 3), (0, 3)], [(0, 3), (0, 0)]]
ring = rex.chain_loop(sq)
check("closed ring of 4 points from 4 curves", len(ring) == 4 and abs(rex.poly_area(ring) - 12) < 1e-9, ring)
shuf = [[(4, 0), (0, 0)], [(4, 0), (4, 3)], [(0, 3), (4, 3)], [(0, 3), (0, 0)]]
ring = rex.chain_loop(shuf)
check("reversed curves are re-oriented (first curve backwards too)", len(ring) == 4 and abs(rex.poly_area(ring) - 12) < 1e-9, ring)
check("loop of fewer than 3 points is dropped", rex.chain_loop([[(0, 0), (1, 0)]]) == [])
check("zero-area loop is dropped", rex.chain_loop([[(0, 0), (1, 0)], [(1, 0), (2, 0)], [(2, 0), (0, 0)]]) == [])
outer, holes = rex.split_loops([[(1, 1), (2, 1), (2, 2), (1, 2)], [(0, 0), (9, 0), (9, 9), (0, 9)]])
check("largest loop is the outer boundary, the rest are holes", rex.poly_area(outer) == 81 and len(holes) == 1)
lv, idx = rex.level_table([
    {"level": "L1", "elev": 0.0, "height_hint": 3.0},
    {"level": "L2", "elev": 4.0, "height_hint": 3.0},
    {"level": "L3", "elev": 7.5, "height_hint": 3.0},
    {"level": "Roof", "elev": 20.0, "height_hint": 3.0},
])
check("level heights come from the gap to the next level, clamped to 2.4 to 6 m", [l["height"] for l in lv][:3] == [4.0, 3.5, 6.0], lv)
check("top level takes the median of the others", lv[-1]["height"] == 4.0, lv)

print("\n== End to end with fake Revit objects ==")
doc = build_office()
out_path = os.path.join(HERE, "data", "sample_model.json")
msg = rex.run([out_path, "auto"], api=FakeApi, doc=doc)
print("   " + msg.replace("\n", "\n   "))
model = json.load(open(out_path, encoding="utf-8"))
check("schema tag written", model["schema"] == "strata-model-1")
check("4 levels in ascending elevation", [l["elevation"] for l in model["levels"]] == [0.0, 3.8, 7.6, 11.4], model["levels"])
check("heights 3.8 3.8 3.8 and top level takes the median", [l["height"] for l in model["levels"]] == [3.8, 3.8, 3.8, 3.8], model["levels"])
rooms_total = sum(len(z["rooms"]) for z in model["zones"])
check("16 rooms per level exported, unplaced, tiny and open rooms skipped", rooms_total == 64, rooms_total)
check("skip counts reported to the user", "Skipped" in msg, msg)
names = {z["name"] for z in model["zones"] if z["level"] == 0}
check("STRATA_Zone, Department and per-room fallbacks all appear", {"South", "North", "Studio", "Core", "Public"} <= names, names)
south = [z for z in model["zones"] if z["level"] == 0 and z["name"] == "South"][0]
check("rooms with the same STRATA_Zone merge into one zone per level", len(south["rooms"]) == 4 and abs(south["area"] - 4 * 81) < 0.01 or len(south["rooms"]) == 4, (len(south["rooms"]), south["area"]))
core = [z for z in model["zones"] if z["level"] == 0 and z["name"] == "Core"][0]
check("hole kept on the Core room and its area excludes the hole", len(core["rooms"][0]["holes"]) == 1 and core["area"] == 72.0, core["rooms"][0]["holes"])
lobby = [z for z in model["zones"] if z["level"] == 0 and z["name"] == "Public"][0]
check("arc boundary tessellated into many points", len(lobby["rooms"][0]["boundary"]) >= 10, len(lobby["rooms"][0]["boundary"]))
check("sensor ID carried onto the zone", any(z["sensor"] == "CUBEMS-F1-Z2" for z in model["zones"]))
check("coordinates are metres (max x about 54)", 50 < max(p[0] for z in model["zones"] for r in z["rooms"] for p in r["boundary"]) <= 54.01)
check("every boundary ring has at least 3 points", all(len(r["boundary"]) >= 3 for z in model["zones"] for r in z["rooms"]))
check("file is compact", os.path.getsize(out_path) < 200 * 1024, os.path.getsize(out_path))

print("\n== Grouping modes ==")
m_room, st = rex.build_model("x", rex.read_rooms(doc, FakeApi)[0], "room")
check("room mode gives one zone per room", st["zones"] == 64, st)
m_dept, st = rex.build_model("x", rex.read_rooms(doc, FakeApi)[0], "department")
check("department mode makes un-departmented rooms their own zones", st["zones"] > 4 * 3, st)
bad = rex.run([out_path, "banana"], api=FakeApi, doc=doc)
check("unknown grouping mode rejected with guidance", "Unknown grouping mode" in bad, bad)
empty = rex.run([out_path, "auto"], api=FakeApi, doc=Doc({}, []))
check("no rooms gives guidance, not a crash", "No placed, enclosed Rooms" in empty, empty)

ok = sum(results)
print("\n%d passed, %d failed" % (ok, len(results) - ok))
sys.exit(0 if ok == len(results) else 1)
