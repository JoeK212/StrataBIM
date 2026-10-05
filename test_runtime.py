import asyncio, json, os, sys
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = "file://" + os.path.join(HERE, "index.html")
THREE = open(os.path.join(HERE, "vendor", "three.r128.min.js"), encoding="utf-8").read()
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

results = []

def check(label, ok, detail=""):
    results.append(ok)
    print(("  ok   " if ok else "  FAIL ") + label + (("\n       " + str(detail)) if (detail and not ok) else ""))

async def route(r):
    url = r.request.url
    if "cdnjs.cloudflare.com" in url and "three" in url:
        await r.fulfill(status=200, content_type="application/javascript", body=THREE)
    elif url.startswith("file://"):
        await r.continue_()
    else:
        await r.fulfill(status=200, content_type="text/css", body="")

async def new_page(browser, w, h, errors, touch=False):
    ctx = await browser.new_context(viewport={"width": w, "height": h}, has_touch=touch, is_mobile=touch)
    page = await ctx.new_page()
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
    await page.route("**/*", route)
    await page.goto(INDEX)
    await page.wait_for_function("typeof meshes !== 'undefined' && meshes.length > 0")
    return ctx, page

async def zone_xy(page, i):
    return await page.evaluate("""(i) => {
        applyCam();
        camera.updateMatrixWorld();
        const v = meshes[i].position.clone().project(camera);
        const r = canvas.getBoundingClientRect();
        return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
    }""", i)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/opt/google/chrome/chrome",
            args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
        )
        errors = []
        ctx, page = await new_page(browser, 1280, 800, errors)

        print("\n== Load and structure ==")
        n = await page.evaluate("meshes.length")
        check("33 zone meshes", n == 33, n)
        floors = await page.evaluate("new Set(zones.map(z => z.floor)).size")
        check("7 floors", floors == 7, floors)
        check("footer shows version", "v1.2.1" in await page.inner_text("#footVersion"))
        gl = await page.evaluate("!!renderer.getContext()")
        check("WebGL context created", gl)
        await page.wait_for_timeout(600)
        await page.screenshot(path=os.path.join(SHOTS, "desktop_dark.png"))

        print("\n== Data sanity ==")
        stats = await page.evaluate("""() => {
            let mn = 1e9, mx = -1e9, nan = 0, tmn = 1e9, tmx = -1e9, peak = 0, night = 1e9, wk = 0, wkc = 0, wd = 0, wdc = 0;
            for (let m = 0; m < TOTAL_MIN; m += 15) {
                let tot = 0;
                for (const z of zones) {
                    const r = sample(z, m);
                    for (const k of ['kwTotal','kwAC','kwLight','kwPlug','T','RH','lux','f']) if (!isFinite(r[k])) nan++;
                    tmn = Math.min(tmn, r.T); tmx = Math.max(tmx, r.T);
                    tot += r.kwTotal;
                }
                peak = Math.max(peak, tot);
                const d = Math.floor(m / 1440);
                if (d === 5 && m % 1440 === 3 * 60) night = Math.min(night, tot);
                if (d >= 5) { wk += tot; wkc++; } else { wd += tot; wdc++; }
            }
            return { nan, tmn, tmx, peak, night, wkAvg: wk / wkc, wdAvg: wd / wdc };
        }""")
        print("   ", json.dumps({k: round(v, 1) for k, v in stats.items()}))
        check("no NaN or Infinity anywhere in the week", stats["nan"] == 0, stats["nan"])
        check("indoor temp stays in a plausible 16-30 C band", 16 < stats["tmn"] and stats["tmx"] < 30, (stats["tmn"], stats["tmx"]))
        check("building peak kW is plausible for 11,700 m2 (150-700)", 150 < stats["peak"] < 700, stats["peak"])
        check("weekend average well below weekday average", stats["wkAvg"] < 0.6 * stats["wdAvg"], stats)
        det = await page.evaluate("""() => {
            const a = sample(zones[3], 3000), b = sample(zones[3], 3000);
            return JSON.stringify(a) === JSON.stringify(b);
        }""")
        check("sample() deterministic for same (zone, minute)", det)

        print("\n== Select, layers, units ==")
        xy = await zone_xy(page, 12)
        await page.mouse.click(xy["x"], xy["y"])
        await page.wait_for_timeout(400)
        sel = await page.evaluate("state.sel")
        check("click selects a zone", sel is not None, sel)
        title = await page.inner_text("#zoneTitle")
        check("zone card titled with floor and zone", title.startswith("Floor "), title)
        card = await page.inner_text("#zoneCard")
        check("zone card shows imperial temp with metric beside it", "°F" in card and "°C" in card, card)
        check("zone card shows area in ft2 and m2", "ft²" in card and "m²" in card, card)
        await page.click("#unitSeg button[data-u=metric]")
        await page.wait_for_timeout(300)
        card2 = await page.inner_text("#zoneCard")
        first_temp = [l for l in card2.splitlines() if "°" in l]
        check("metric toggle puts °C first", bool(first_temp) and first_temp[0].find("°C") < first_temp[0].find("°F"), card2)
        leg = await page.inner_text("#legendLo")
        await page.click("#layerSeg button[data-l=temp]")
        await page.wait_for_timeout(300)
        lo = await page.inner_text("#legendLo")
        hi = await page.inner_text("#legendHi")
        check("temp layer legend in °C when metric", "°C" in lo and "°C" in hi, (lo, hi))
        await page.click("#unitSeg button[data-u=imperial]")
        await page.wait_for_timeout(300)
        lo = await page.inner_text("#legendLo")
        check("temp layer legend in °F when imperial", "°F" in lo, lo)
        ct = await page.inner_text("#chartTitle")
        check("chart title names selected zone and layer", "Indoor temperature" in ct, ct)
        stored = await page.evaluate("localStorage.getItem('strata.units')")
        check("units persisted", stored == "imperial", stored)

        print("\n== Density layer ==")
        await page.evaluate("state.playing = false; state.t = 14*60; evaluate(); updatePanel();")
        await page.click("#layerSeg button[data-l=dens]")
        await page.wait_for_timeout(300)
        d = await page.evaluate("""() => {
            const z = zones[5], r = sample(z, state.t);
            let kw = 0, area = 0;
            zones.forEach(q => { kw += sample(q, state.t).kwTotal; area += q.area; });
            return { direct: r.wm2, viaKw: r.kwTotal * 1000 / z.area, bldg: buildingValue(LAYERS.dens, state.t), bldgExpected: kw * 1000 / area, hi: rangeOf(LAYERS.dens).hi };
        }""")
        check("zone density equals kW per area", abs(d["direct"] - d["viaKw"]) < 1e-9, d)
        check("building density is the area-weighted total", abs(d["bldg"] - d["bldgExpected"]) < 1e-6, d)
        check("density colour range is a sensible W/m2 figure", 5 < d["hi"] < 200, d)
        lo = await page.inner_text("#legendHi")
        check("legend in W/ft2 when imperial", "W/ft²" in lo, lo)
        await page.click("#unitSeg button[data-u=metric]")
        await page.wait_for_timeout(250)
        lo = await page.inner_text("#legendHi")
        check("legend in W/m2 when metric", "W/m²" in lo, lo)
        await page.click("#unitSeg button[data-u=imperial]")
        ct = await page.inner_text("#chartTitle")
        check("chart title names the layer", "Power density" in ct, ct)
        xy = await zone_xy(page, 12)
        await page.mouse.click(xy["x"], xy["y"])
        await page.wait_for_timeout(400)
        card = await page.inner_text("#zoneCard")
        check("zone card shows density in both units", "Power density" in card and "W/ft²" in card and "W/m²" in card, card)
        spread = await page.evaluate("""() => {
            const R = rangeOf(LAYERS.dens); let over = 0, n = 0;
            for (let m = 0; m < TOTAL_MIN; m += 30) for (const z of zones) { n++; if (sample(z, m).wm2 > R.hi) over++; }
            return 100 * over / n;
        }""")
        check("under 3 percent of density samples exceed the colour range", spread < 3, spread)
        await page.click("#layerSeg button[data-l=power]")
        await page.evaluate("selectZone(null)")

        print("\n== Floor isolation ==")
        await page.click("#floors button[data-f='2']")
        await page.wait_for_timeout(200)
        ghost = await page.evaluate("meshes.filter(m => m.material.opacity < 0.2).length")
        check("isolating floor 3 ghosts the other 28 zones", ghost == 28, ghost)
        sel_after = await page.evaluate("state.sel")
        check("selection on a hidden floor is cleared", sel_after is None, sel_after)
        await page.click("#floors button[data-f='-1']")
        ghost = await page.evaluate("meshes.filter(m => m.material.opacity < 0.2).length")
        check("All restores every zone", ghost == 0, ghost)

        print("\n== Timeline and alerts ==")
        await page.evaluate("state.playing = false; renderControls();")
        await page.evaluate("document.querySelector('#scrub').value = String(2*1440 + 23*60); document.querySelector('#scrub').dispatchEvent(new Event('input'))")
        await page.wait_for_timeout(300)
        clock = await page.inner_text("#clock")
        check("scrubber moves the clock to Wednesday 11 PM", clock.startswith("Wed") and "11:00 PM" in clock, clock)
        alerts = await page.inner_text("#alerts")
        check("Wednesday night shows the planted after-hours cooling alert", "After-hours cooling" in alerts, alerts)
        await page.click("#alerts button")
        await page.wait_for_timeout(300)
        check("clicking an alert selects that zone", await page.evaluate("state.sel !== null"))
        await page.screenshot(path=os.path.join(SHOTS, "desktop_alert.png"))
        await page.evaluate("document.querySelector('#scrub').value = String(3*1440 + 14*60); document.querySelector('#scrub').dispatchEvent(new Event('input'))")
        await page.wait_for_timeout(300)
        alerts = await page.inner_text("#alerts")
        check("Thursday afternoon shows the planted running-warm alert", "Running warm" in alerts, alerts)
        await page.evaluate("document.querySelector('#scrub').value = String(5*1440 + 10*60); document.querySelector('#scrub').dispatchEvent(new Event('input'))")
        await page.wait_for_timeout(300)
        alerts = await page.inner_text("#alerts")
        check("Saturday morning shows no alerts", "No active alerts" in alerts, alerts)

        print("\n== Playback ==")
        await page.evaluate("state.t = 9*60; state.playing = true; state.speed = 60; renderControls();")
        t0 = await page.evaluate("state.t")
        await page.wait_for_timeout(1500)
        t1 = await page.evaluate("state.t")
        slow = t1 - t0
        await page.evaluate("state.t = 9*60; state.speed = 3600; renderControls();")
        await page.wait_for_timeout(1500)
        t2 = await page.evaluate("state.t")
        fast = t2 - 9*60
        check("play advances sim time", slow > 0.2, (t0, t1))
        check("3600x runs far faster than 60x over the same window", fast > 8 * slow, (slow, fast))
        await page.click("#playBtn")
        ta = await page.evaluate("state.t")
        await page.wait_for_timeout(500)
        tb = await page.evaluate("state.t")
        check("pause freezes sim time", abs(tb - ta) < 0.001, (ta, tb))
        await page.evaluate("state.t = TOTAL_MIN - 5; state.playing = true; state.speed = 3600; renderControls();")
        await page.wait_for_timeout(500)
        tl = await page.evaluate("state.t")
        check("replay loops past Sunday midnight", tl < 1000, tl)

        print("\n== Reseed (confirmDialog) ==")
        seed0 = await page.evaluate("state.seed")
        await page.evaluate("state.playing = false;")
        await page.click("#reseed")
        await page.wait_for_timeout(200)
        shown = await page.evaluate("!document.querySelector('#modal').hidden")
        check("confirm dialog opens", shown)
        await page.click("#modalCancel")
        await page.wait_for_timeout(200)
        check("cancel leaves the seed alone", await page.evaluate("state.seed") == seed0)
        await page.click("#reseed")
        await page.click("#modalOk")
        await page.wait_for_timeout(400)
        seed1 = await page.evaluate("state.seed")
        check("confirm generates a new seed", seed1 != seed0, (seed0, seed1))
        check("scene rebuilt consistently", await page.evaluate("meshes.length === zones.length && zoneGroup.children.length === zones.length + layout.floors.length"))
        check("floor strip matches the new floor count", await page.evaluate("document.querySelectorAll('#floors button').length === layout.floors.length + 1"))
        check("toast names the new building", "floors" in await page.inner_text("#toast"))
        check("simulation section describes the building", "floors" in await page.inner_text("#simSummary") and "Planted faults" in await page.inner_text("#simNote"))
        check("Reference office button enabled on a non-reference building", await page.evaluate("document.querySelector('#refBtn').disabled") is False)
        await page.screenshot(path=os.path.join(SHOTS, "desktop_new_building.png"))
        await page.click("#refBtn")
        await page.wait_for_timeout(300)
        check("Reference office restores 7 floors and 33 zones", await page.evaluate("layout.floors.length === 7 && zones.length === 33"))
        check("Reference button disables itself on the reference building", await page.evaluate("document.querySelector('#refBtn').disabled"))
        await page.click("#reseed")
        await page.click("#modalOk")
        await page.wait_for_timeout(300)
        seed1 = await page.evaluate("state.seed")

        print("\n== Layout variety across seeds ==")
        var = await page.evaluate("""() => {
            const combos = new Set(), names = new Set(), dims = new Set();
            let bad = 0, tmin = 99, tmax = -99, hmax = 0, nan = 0, tot = 0, over = 0;
            for (let sd = 1000; sd < 1040; sd++) {
                const L = makeLayout(sd);
                combos.add(L.floors.length + ':' + L.floors.join(','));
                names.add(L.name); dims.add(L.w + 'x' + L.d);
                if (L.floors.length < 4 || L.floors.length > 10) bad++;
                if (L.floors.some(n => n < 3 || n > 7)) bad++;
            }
            for (let sd = 1000; sd < 1010; sd++) {
                state.seed = sd; buildScene();
                for (let m = 0; m < TOTAL_MIN; m += 30) for (const z of zones) {
                    const r = sample(z, m);
                    for (const k of ['kwTotal','kwAC','T','RH','lux','f']) if (!isFinite(r[k])) nan++;
                    tmin = Math.min(tmin, r.T); tmax = Math.max(tmax, r.T); hmax = Math.max(hmax, r.kwAC); tot++; if (r.kwAC > rangeOf(LAYERS.hvac).hi) over++;
                }
            }
            state.seed = %d; buildScene();
            return { combos: combos.size, names: names.size, dims: dims.size, bad, tmin, tmax, hmax, nan, overPct: 100 * over / tot };
        }""" % seed1)
        print("   ", json.dumps({k: (round(v, 1) if isinstance(v, float) else v) for k, v in var.items()}))
        check("40 seeds give many distinct layouts", var["combos"] >= 30 and var["dims"] >= 20, var)
        check("every archetype appears", var["names"] == 5, var["names"])
        check("floor and zone counts stay within bounds", var["bad"] == 0, var["bad"])
        check("no NaN in any simulated building", var["nan"] == 0, var["nan"])
        check("indoor temps plausible even in hot and cold climates (13-32 C)", 13 < var["tmin"] and var["tmax"] < 32, var)
        check("under 3 percent of HVAC samples exceed the legend range in any building", var["overPct"] < 3, var["overPct"])
        arch_effect = await page.evaluate("""() => {
            const out = {};
            for (const sd of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]) {
                const L = makeLayout(sd);
                if (out[L.name]) continue;
                state.seed = sd; buildScene();
                let t = 0, heat = 0, wk = 0;
                for (let m = 0; m < TOTAL_MIN; m += 30) for (const z of zones) { const r = sample(z, m); t += r.kwAC; if (m >= 5*1440) wk += r.kwTotal; }
                out[L.name] = { perM2: t / zones.reduce((a, z) => a + z.area, 0), wk: wk };
            }
            state.seed = %d; buildScene();
            return out;
        }""" % seed1)
        names = list(arch_effect.keys())
        print("   ", json.dumps({k: round(v["perM2"], 2) for k, v in arch_effect.items()}))
        if "Hot-climate office" in arch_effect and "Cold-climate office" in arch_effect:
            check("hot-climate HVAC per m2 exceeds standard office", arch_effect["Hot-climate office"]["perM2"] > arch_effect.get("Standard office", arch_effect["Early-start office"])["perM2"], arch_effect)
        check("saw several archetypes in the first 20 seeds", len(names) >= 3, names)

        print("\n== Theme ==")
        await page.click("#themeBtn")
        await page.wait_for_timeout(500)
        check("light theme sets data-theme", await page.evaluate("document.documentElement.getAttribute('data-theme')") == "light")
        check("theme-color meta follows theme", (await page.evaluate("document.getElementById('themeColorMeta').content")).lower() == "#f2f0fa")
        await page.screenshot(path=os.path.join(SHOTS, "desktop_light.png"))
        await page.click("#themeBtn")
        check("toggle returns to dark by removing the attribute", await page.evaluate("document.documentElement.hasAttribute('data-theme')") is False)

        print("\n== Help ==")
        await page.click("#helpBtn")
        await page.wait_for_timeout(200)
        check("Help opens", await page.evaluate("!document.querySelector('#help').hidden"))
        check("focus moves to Close", await page.evaluate("document.activeElement.id") == "helpClose")
        txt = await page.inner_text("#help")
        check("help names every layer", all(w in txt for w in ["Power", "HVAC", "Temp", "People"]))
        await page.keyboard.press("Tab")
        check("Tab keeps focus inside the panel", await page.evaluate("document.activeElement.id") == "helpClose")
        await page.screenshot(path=os.path.join(SHOTS, "desktop_help.png"))
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(100)
        check("Escape closes Help", await page.evaluate("document.querySelector('#help').hidden"))
        check("focus returns to the Help button", await page.evaluate("document.activeElement.id") == "helpBtn")
        await page.click("#helpBtn")
        await page.mouse.click(5, 5)
        await page.wait_for_timeout(100)
        check("clicking the backdrop closes Help", await page.evaluate("document.querySelector('#help').hidden"))
        await page.click("#helpBtn")
        await page.click("#helpClose")
        check("Close button closes Help and unlocks scroll", await page.evaluate("document.querySelector('#help').hidden && document.body.style.overflow === ''"))
        hint = await page.evaluate("document.querySelector('#layerSeg button').title")
        check("layer buttons carry hover hints", len(hint) > 5, hint)

        print("\n== Revit model import ==")
        sample = os.path.join(HERE, "data", "sample_model.json")
        await page.evaluate("state.playing = false;")
        await page.click("#refBtn") if await page.evaluate("!layout.ref") else None
        await page.wait_for_timeout(200)
        await page.set_input_files("#modelFile", sample)
        await page.wait_for_timeout(700)
        info = await page.evaluate("""() => ({
            imported: layout.imported, levels: layout.floors.length, zones: zones.length, meshes: meshes.length,
            counts: layout.floors.join(','), name: layout.name, sub: layout.sub,
            strip: document.querySelectorAll('#floors button').length,
            stripTitle: document.querySelector('#floors button[data-f="0"]').title
        })""")
        print("   ", json.dumps(info))
        check("sample model loads as 4 levels and 20 zones", info["imported"] and info["levels"] == 4 and info["zones"] == 20 and info["meshes"] == 20, info)
        check("floor strip uses Revit level names", info["stripTitle"] == "Level 1" and info["strip"] == 5, info)
        check("header names the project", "Synthetic Office" in info["sub"], info["sub"])
        check("toast reports what loaded", "Loaded Synthetic Office" in await page.inner_text("#toast"))
        geo = await page.evaluate("""() => {
            const box = new THREE.Box3();
            meshes.forEach(m => box.expandByObject(m));
            const c = new THREE.Vector3(); box.getCenter(c);
            const s = new THREE.Vector3(); box.getSize(s);
            return { cx: c.x, cz: c.z, minY: box.min.y, maxY: box.max.y, sx: s.x, sz: s.z };
        }""")
        check("model is centred on the origin", abs(geo["cx"]) < 0.6 and abs(geo["cz"]) < 0.6, geo)
        check("lowest level sits at ground and the top is about 4 storeys up", abs(geo["minY"]) < 0.01 and 14 < geo["maxY"] < 15.2, geo)
        check("footprint is about 54 m by 36 m (north is -Z)", 53 < geo["sx"] < 55 and 35 < geo["sz"] < 37, geo)
        holes = await page.evaluate("""() => {
            const z = zones.findIndex(z => z.name === 'Core' && z.floor === 0);
            const m = meshes[z];
            return { verts: m.geometry.attributes.position.count, box: new THREE.BoxGeometry(1,1,1).attributes.position.count };
        }""")
        check("Core zone with a shaft hole has far more geometry than a plain 4-sided room (96 vs 36 vertices)", holes["verts"] > 60, holes)
        nan = await page.evaluate("""() => { let n = 0; for (let m = 0; m < TOTAL_MIN; m += 60) for (const z of zones) { const r = sample(z, m); for (const k of ['kwTotal','kwAC','T','RH','lux','f']) if (!isFinite(r[k])) n++; } return n; }""")
        check("simulation runs on the imported zones without NaN", nan == 0, nan)
        sensor_zone = await page.evaluate("zones.findIndex(z => z.sensor === 'CUBEMS-F1-Z2')")
        check("sensor ID carried through to a zone", sensor_zone >= 0, sensor_zone)
        pos = await page.evaluate("""(i) => {
            const m = meshes[i]; m.geometry.computeBoundingBox();
            const c = new THREE.Vector3(); m.geometry.boundingBox.getCenter(c);
            applyCam(); camera.updateMatrixWorld();
            const v = c.clone().project(camera); const r = canvas.getBoundingClientRect();
            return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
        }""", sensor_zone)
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(500)
        picked = await page.evaluate("state.sel")
        check("clicking an imported zone selects a zone", picked is not None, picked)
        if picked is not None:
            card = await page.inner_text("#zoneCard")
            check("zone card shows rooms and area in both unit systems", "Rooms" in card and "ft²" in card and "m²" in card, card)
            title = await page.inner_text("#zoneTitle")
            check("zone title shows level name and zone name", title.startswith("Level"), title)
        await page.click("#floors button[data-f='1']")
        await page.wait_for_timeout(200)
        ghost = await page.evaluate("meshes.filter(m => m.material.opacity < 0.2).length")
        check("isolating a level ghosts the other 15 zones", ghost == 15, ghost)
        await page.click("#floors button[data-f='-1']")
        await page.evaluate("state.sel = null; selectZone(null);")
        await page.evaluate("state.t = 11*60; evaluate(); updatePanel(); updateLegend();")
        await page.screenshot(path=os.path.join(SHOTS, "desktop_imported.png"))

        stored = await page.evaluate("localStorage.getItem('strata.model') && localStorage.getItem('strata.model').length")
        check("model remembered in the browser", stored and stored > 1000, stored)
        await page.reload()
        await page.wait_for_function("typeof meshes !== 'undefined' && meshes.length > 0")
        check("model survives a reload", await page.evaluate("layout.imported && zones.length === 20"))

        before = await page.evaluate("zones.length")
        bad_cases = {
            "not json": ("{oops", "not valid JSON"),
            "wrong schema": (json.dumps({"schema": "other", "levels": [], "zones": []}), "not a STRATA model"),
            "zone points at missing level": (json.dumps({"schema": "strata-model-1", "levels": [{"name": "L", "elevation": 0, "height": 3}], "zones": [{"name": "Z", "level": 5, "rooms": [{"boundary": [[0,0],[1,0],[1,1]]}]}]}), "level that does not exist"),
            "outline with 2 points": (json.dumps({"schema": "strata-model-1", "levels": [{"name": "L", "elevation": 0, "height": 3}], "zones": [{"name": "Z", "level": 0, "rooms": [{"boundary": [[0,0],[1,0]]}]}]}), "fewer than 3 points"),
            "non-numeric coordinate": (json.dumps({"schema": "strata-model-1", "levels": [{"name": "L", "elevation": 0, "height": 3}], "zones": [{"name": "Z", "level": 0, "rooms": [{"boundary": [[0,0],[1,"x"],[1,1]]}]}]}), "not a pair of numbers"),
            "null coordinate": (json.dumps({"schema": "strata-model-1", "levels": [{"name": "L", "elevation": 0, "height": 3}], "zones": [{"name": "Z", "level": 0, "rooms": [{"boundary": [[0,0],[1,None],[1,1]]}]}]}), "not a pair of numbers"),
            "too many zones": (json.dumps({"schema": "strata-model-1", "levels": [{"name": "L", "elevation": 0, "height": 3}], "zones": [{"name": "Z%d" % i, "level": 0, "rooms": [{"boundary": [[0,0],[1,0],[1,1]]}]} for i in range(601)]}), "limit is 600"),
        }
        for label, (body, expect) in bad_cases.items():
            fp = os.path.join(HERE, "shots", "bad.json")
            open(fp, "w", encoding="utf-8").write(body)
            await page.evaluate("document.querySelector('#toast').textContent = ''")
            await page.set_input_files("#modelFile", fp)
            await page.wait_for_timeout(350)
            msg = await page.inner_text("#toast")
            check("rejects %s with a clear message" % label, expect in msg, msg)
        check("a rejected file leaves the current model untouched", await page.evaluate("zones.length") == before and await page.evaluate("layout.imported"))

        evil = {"schema": "strata-model-1", "project": "<img src=x onerror=window.__pwn=1>", "levels": [{"name": "<b>L</b>", "elevation": 0, "height": 3.5}],
                "zones": [{"name": "<img src=x onerror=window.__pwn=2>", "level": 0, "sensor": "<script>window.__pwn=3</script>", "rooms": [{"id": "1", "boundary": [[0,0],[10,0],[10,8],[0,8]]}]}]}
        fp = os.path.join(HERE, "shots", "evil.json")
        open(fp, "w", encoding="utf-8").write(json.dumps(evil))
        await page.set_input_files("#modelFile", fp)
        await page.wait_for_timeout(500)
        await page.evaluate("state.t = 10*60; evaluate();")
        await page.evaluate("selectZone(0)")
        await page.wait_for_timeout(400)
        pwn = await page.evaluate("window.__pwn === undefined && document.querySelectorAll('#zoneCard img, #zoneCard script, #alerts img, #panel img, #brandSub img').length === 0")
        check("markup in project, zone and sensor names is not executed", pwn)
        await page.evaluate("state.model = null; store('model',''); swapBuildingForTest && 0") if False else None

        print("\n== Drag and drop ==")
        good = open(sample, encoding="utf-8").read()
        await page.evaluate("""(txt) => {
            const dt = new DataTransfer();
            dt.items.add(new File([txt], 'strata_model.json', { type: 'application/json' }));
            const ev = new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true });
            document.querySelector('#stage').dispatchEvent(ev);
        }""", good)
        await page.wait_for_timeout(700)
        check("dropping the file on the model loads it", await page.evaluate("layout.imported && zones.length === 20 && layout.name === 'Synthetic Office'"))
        check("drop overlay hides again", await page.evaluate("!document.querySelector('#stage').classList.contains('drop')"))

        print("\n== Remove model ==")
        label = await page.inner_text("#refBtn")
        check("button reads Remove model while imported", label == "Remove model", label)
        await page.click("#refBtn")
        await page.wait_for_timeout(400)
        check("Remove model returns to the 7-floor, 33-zone reference office", await page.evaluate("layout.ref && !layout.imported && zones.length === 33 && state.model === null"))
        check("saved model cleared", await page.evaluate("!localStorage.getItem('strata.model')"))
        check("camera reframed and floor strip rebuilt for 7 floors", await page.evaluate("document.querySelectorAll('#floors button').length === 8"))

        await page.set_input_files("#modelFile", sample)
        await page.wait_for_timeout(500)
        await page.click("#reseed")
        check("replacing an imported model asks first, in plain words", "Replace the loaded Revit model" in await page.inner_text("#modalMsg"))
        await page.click("#modalOk")
        await page.wait_for_timeout(400)
        check("generating a new building drops the imported model", await page.evaluate("!layout.imported && state.model === null"))
        await page.click("#refBtn")
        await page.wait_for_timeout(300)

        print("\n== Persistence across reload ==")
        await page.evaluate("state.layer='occ'; store('layer','occ');")
        seed_now = await page.evaluate("state.seed")
        await page.reload()
        await page.wait_for_function("typeof meshes !== 'undefined' && meshes.length > 0")
        check("layer, units and seed restored", await page.evaluate("state.layer") == "occ" and await page.evaluate("state.seed") == seed_now)

        check("no console or page errors on desktop", len(errors) == 0, errors)
        await ctx.close()

        print("\n== Mobile ==")
        merr = []
        ctx, page = await new_page(browser, 390, 844, merr, touch=True)
        await page.wait_for_timeout(700)
        await page.screenshot(path=os.path.join(SHOTS, "mobile_top.png"))
        sw = await page.evaluate("document.documentElement.scrollWidth")
        check("no horizontal overflow at 390 px", sw <= 391, sw)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(300)
        await page.screenshot(path=os.path.join(SHOTS, "mobile_bottom.png"))
        stage_h = await page.evaluate("document.querySelector('#stage').clientHeight")
        check("stage keeps a usable height on phone", stage_h > 340, stage_h)
        await page.evaluate("window.scrollTo(0, 0)")
        xy = await zone_xy(page, 8)
        await page.touchscreen.tap(xy["x"], xy["y"])
        await page.wait_for_timeout(400)
        check("tap selects a zone on touch", await page.evaluate("state.sel !== null"))
        await page.click("#helpBtn")
        await page.wait_for_timeout(200)
        fits = await page.evaluate("(() => { const c = document.querySelector('.help-card'); const r = c.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight + 1 && c.scrollHeight > c.clientHeight; })()")
        check("help card fits the phone screen and scrolls inside itself", fits)
        await page.screenshot(path=os.path.join(SHOTS, "mobile_help.png"))
        await page.evaluate("document.querySelector('.help-card').scrollTop = 99999")
        await page.wait_for_timeout(150)
        vis = await page.evaluate("(() => { const b = document.querySelector('#helpClose').getBoundingClientRect(); return b.bottom <= innerHeight && b.top >= 0; })()")
        check("Close button stays reachable after scrolling to the end", vis)
        await page.click("#helpClose")
        check("no console or page errors on mobile", len(merr) == 0, merr)
        await ctx.close()
        await browser.close()

    ok = sum(1 for r in results if r)
    print("\n%d passed, %d failed" % (ok, len(results) - ok))
    sys.exit(0 if ok == len(results) else 1)

asyncio.run(main())
