import asyncio, functools, http.server, json, os, sys, threading
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
THREE = open(os.path.join(HERE, "vendor", "three.r128.min.js"), encoding="utf-8").read()
results = []

def check(label, ok, detail=""):
    results.append(ok)
    print(("  ok   " if ok else "  FAIL ") + label + (("\n       " + str(detail)) if (detail and not ok) else ""))

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

async def route(r):
    url = r.request.url
    if "cdnjs.cloudflare.com" in url and "three" in url:
        await r.fulfill(status=200, content_type="application/javascript", body=THREE)
    elif url.startswith("http://127.0.0.1") or url.startswith("file://"):
        await r.continue_()
    else:
        await r.fulfill(status=200, content_type="text/css", body="")

async def open_page(browser, url, errors, wait_data=True):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console." + m.type + ": " + m.text) if m.type == "error" else None)
    await page.route("**/*", route)
    await page.goto(url)
    await page.wait_for_function("typeof meshes !== 'undefined' && meshes.length > 0")
    if wait_data:
        await page.wait_for_function("DATA.status === 'ready' || DATA.status === 'error'")
        await page.wait_for_timeout(300)
    return ctx, page

async def main():
    handler = functools.partial(Quiet, directory=HERE)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/index.html" % port
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/opt/google/chrome/chrome",
            args=["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        errors = []

        print("\n== CU-BEMS replay over http ==")
        ctx, page = await open_page(browser, base, errors)
        check("data files load and replay is the default source", await page.evaluate("DATA.status === 'ready' && state.source === 'data' && dataMode()"))
        check("reference office is 33 zones on 7 floors, 4-4-5-5-5-5-5", await page.evaluate("zones.length === 33 && layout.floors.join(',') === '4,4,5,5,5,5,5'"))
        check("every reference zone maps to the CU-BEMS zone with the same name", await page.evaluate("zones.every(z => { sample(z, 0); return z.src.id === z.name && z.srcScale === 1; })"))
        check("header says whose data this is", "CU-BEMS replay" in await page.inner_text("#brandSub") and "Bangkok" in await page.inner_text("#brandSub"))
        check("Data source buttons show the replay as selected", await page.evaluate("document.querySelector('#srcSeg button[data-src=data]').getAttribute('aria-pressed') === 'true'"))
        bad = await page.evaluate("""(() => {
            let n = 0;
            for (let m = 0; m < TOTAL_MIN; m += 7) for (const z of zones) {
                const r = sample(z, m);
                for (const k in r) if (typeof r[k] === 'number' && !isFinite(r[k])) n++;
                if (r.kwTotal < 0 || r.f < 0 || r.f > 1 || r.RH < 0 || r.RH > 100) n++;
            }
            return n;
        })()""")
        check("no NaN, negative power or out-of-range values anywhere in the week", bad == 0, bad)
        peak = await page.evaluate("(() => { let mx = 0; for (let m = 0; m < TOTAL_MIN; m += 10) { let s = 0; for (const z of zones) s += sample(z, m).kwTotal; mx = Math.max(mx, s); } return mx; })()")
        check("building peak matches the dataset (about 781 kW)", 700 < peak < 800, peak)
        wk = await page.evaluate("(() => { const p = t => zones.reduce((a, z) => a + sample(z, t).kwTotal, 0); return [p(2 * 1440 + 11 * 60), p(5 * 1440 + 11 * 60)]; })()")
        check("weekday midday draws far more than Saturday midday", wk[0] > 3 * wk[1], wk)
        est = await page.evaluate("""(() => {
            const a = zones.filter(z => sample(z, 600).estT).length;
            const b = zones.filter(z => sample(z, 4 * 1440 + 600).estT).length;
            return [a, b];
        })()""")
        check("all temperatures are flagged estimated before the sensors start", est[0] == 33, est)
        check("later only the 9 source zones without sensors stay estimated", est[1] == 9, est)
        wx = await page.evaluate("(() => { const a = sample(zones[0], 0).to, b = sample(zones[0], 14 * 60).to; return [a, b]; })()")
        check("outdoor temperature follows the New York file (20.3 C at midnight, 26.5 C at 2 PM)", abs(wx[0] - 20.3) < 0.01 and abs(wx[1] - 26.5) < 0.01, wx)
        lab = await page.evaluate("clockLabel(0)")
        check("clock shows no calendar date in replay mode", lab.startswith("Mon") and "Oct" not in lab and "Mar" not in lab, lab)
        found = await page.evaluate("""(() => {
            let hits = 0;
            for (let m = 0; m < TOTAL_MIN; m += 30) {
                zones.forEach((z, i) => { cur[i] = sample(z, m); });
                hits += computeAlerts().filter(a => a.text === 'After-hours cooling').length;
            }
            return hits;
        })()""")
        check("real after-hours cooling shows up as alerts", found > 20, found)
        zone_est = await page.evaluate("""(() => {
            state.t = 600; selectZone(8); updatePanel();
            return document.querySelector('#zoneCard').innerText;
        })()""")
        check("zone card marks estimated values and names the source zone", "(estimated)" in zone_est and "Readings from" in zone_est, zone_est)
        await page.evaluate("state.t = 3 * 1440 + 600; selectZone(8); updatePanel()")
        card = await page.inner_text("#zoneCard")
        check("zone card has no estimate marks for measured temperature", "Temperature (estimated)" not in card, card)
        unmetered = await page.evaluate("(() => { const i = zones.findIndex(z => z.name === 'F1-Z1'); state.t = 3 * 1440 + 600; selectZone(i); updatePanel(); return document.querySelector('#zoneCard').innerText; })()")
        check("unmetered HVAC is labelled, not invented", "HVAC (not metered)" in unmetered, unmetered)
        check("estimates are listed in the Building section", "Estimates:" in await page.inner_text("#simNote"))
        check("ranges are sized from the data", await page.evaluate("ranges.power >= 40 && ranges.power <= 200 && rangeOf(LAYERS.temp).lo === 18"))
        check("people stat is labelled estimated", "People (estimated)" in await page.inner_text("#stats"))

        print("\n== Switching source ==")
        await page.click("#srcSeg button[data-src=sim]")
        await page.wait_for_timeout(200)
        check("Simulated switches back to the generator and planted faults", await page.evaluate("state.source === 'sim' && !dataMode()") and "Planted faults" in await page.inner_text("#simNote"))
        check("source choice is remembered", await page.evaluate("localStorage.getItem('strata.source')") == "sim")
        await page.click("#srcSeg button[data-src=data]")
        await page.wait_for_timeout(200)
        check("CU-BEMS replay switches back on", await page.evaluate("dataMode()"))
        await ctx.close()

        print("\n== Reload remembers Simulated ==")
        ctx, page = await open_page(browser, base, errors)
        await page.click("#srcSeg button[data-src=sim]")
        await page.reload()
        await page.wait_for_function("DATA.status === 'ready'")
        await page.wait_for_timeout(300)
        check("a reload keeps Simulated when that was the last choice", await page.evaluate("state.source === 'sim'"))
        await ctx.close()

        print("\n== Imported Revit model on replay ==")
        ctx, page = await open_page(browser, base, errors)
        await page.set_input_files("#modelFile", os.path.join(HERE, "data", "sample_model.json"))
        await page.wait_for_function("state.model !== null")
        await page.wait_for_timeout(300)
        r = await page.evaluate("""(() => {
            let bad = 0, maxScale = 0;
            for (let m = 0; m < TOTAL_MIN; m += 60) for (const z of zones) {
                const s = sample(z, m);
                for (const k in s) if (typeof s[k] === 'number' && !isFinite(s[k])) bad++;
                maxScale = Math.max(maxScale, z.srcScale);
                if (z.cond === false && s.kwAC !== 0) bad++;
            }
            return { bad, maxScale, n: zones.length, all: zones.every(z => z.src && z.src.id) };
        })()""")
        check("imported model: every zone gets readings, no NaN, unconditioned zones draw no HVAC", r["bad"] == 0 and r["all"], r)
        check("imported model: readings are scaled by area, not copied", r["maxScale"] > 0, r)
        check("imported model: zone card says readings are borrowed and scaled", "scaled by area" in await page.evaluate("(() => { selectZone(0); updatePanel(); return document.querySelector('#zoneCard').innerText; })()"))
        await page.click("#refBtn")
        await page.wait_for_timeout(300)
        check("Remove model returns to the 33-zone reference replay", await page.evaluate("layout.ref && zones.length === 33 && dataMode()"))
        await ctx.close()

        print("\n== Missing or broken data files ==")
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        e2 = []
        page.on("pageerror", lambda e: e2.append(str(e)))
        async def broken(r):
            url = r.request.url
            if "cdnjs.cloudflare.com" in url and "three" in url:
                await r.fulfill(status=200, content_type="application/javascript", body=THREE)
            elif url.endswith("cubems_week.json"):
                await r.fulfill(status=200, content_type="application/json", body=json.dumps({"meta": {"samples": 5, "step_min": 10}, "zones": [{"id": "x", "floor": 1}]}))
            elif url.startswith("http://127.0.0.1"):
                await r.continue_()
            else:
                await r.fulfill(status=200, content_type="text/css", body="")
        await page.route("**/*", broken)
        await page.goto(base)
        await page.wait_for_function("DATA.status === 'error'")
        await page.wait_for_timeout(300)
        check("a malformed data file falls back to the simulation with a clear message", await page.evaluate("state.source === 'sim' && !dataMode()") and "could not be loaded" in await page.inner_text("#srcNote"))
        check("replay button is disabled when data is unavailable", await page.evaluate("document.querySelector('#srcSeg button[data-src=data]').disabled"))
        check("no page errors when data is bad", len(e2) == 0, e2)
        await ctx.close()

        print("\n== file:// has no replay ==")
        ctx, page = await open_page(browser, "file://" + os.path.join(HERE, "index.html"), errors, wait_data=False)
        await page.wait_for_function("DATA.status === 'unavailable'")
        check("opened from disk: simulated feed, replay disabled, reason shown", await page.evaluate("state.source === 'sim' && document.querySelector('#srcSeg button[data-src=data]').disabled") and "http" in await page.inner_text("#srcNote"))
        await ctx.close()

        check("no console or page errors", len([e for e in errors if "ERR_" not in e]) == 0, errors)
        await browser.close()
    ok = sum(1 for r in results if r)
    print("\n%d passed, %d failed" % (ok, len(results) - ok))
    sys.exit(0 if ok == len(results) else 1)

asyncio.run(main())
