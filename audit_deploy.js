// STRATA deploy audit. Run: node audit_deploy.js
// Project-specific invariants, not a linter. Every bug found in this tool gets a check() here
// in the same edit that fixes it, under a sectionHeader() named after the fixing version.

const fs = require('fs');
const path = require('path');

const dir = __dirname;
const read = f => fs.readFileSync(path.join(dir, f), 'utf8');
const html = read('index.html');
const changelog = read('CHANGELOG.md');
const toml = fs.existsSync(path.join(dir, 'netlify.toml')) ? read('netlify.toml') : '';

let pass = 0;
let fail = 0;

function sectionHeader(name) {
  console.log('\n== ' + name + ' ==');
}
function check(label, ok, detail) {
  if (ok) {
    pass++;
    console.log('  ok   ' + label);
  } else {
    fail++;
    console.log('  FAIL ' + label + (detail ? '\n       ' + detail : ''));
  }
}

const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
const script = scriptMatch ? scriptMatch[1] : '';
const head = html.split('<html lang="en">')[0];

sectionHeader('Template baseline');
const topEntry = changelog.match(/^v(\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2}) - (.+)/);
check('CHANGELOG.md top entry matches "vX.Y.Z - YYYY-MM-DD - description"', !!topEntry);
const av = script.match(/const APP_VERSION = '(\d+\.\d+\.\d+)'/);
check('APP_VERSION constant present', !!av);
check('APP_VERSION matches CHANGELOG top entry', !!(av && topEntry && av[1] === topEntry[1]),
  av && topEntry ? 'APP_VERSION ' + av[1] + ' vs changelog ' + topEntry[1] : '');
check('footer rendered through template literal referencing APP_VERSION',
  /footVersion'\)\.innerHTML = `[^`]*\$\{APP_VERSION\}[^`]*`/.test(script));
check('footer element id="footVersion" exists and is empty in static HTML',
  /<footer class="foot" id="footVersion"><\/footer>/.test(html));
check('footer links to axisbim.io', /axisbim\.io/.test(script));
check('index.html header comment has no CHANGELOG block', !/CHANGELOG/.test(head));
check('header comment sits before <html lang="en"> with name, description, credit',
  /<!--\nSTRATA\n.+ — .+\nJoe\.K · axisbim\.io\n-->/.test(head));
check('escapeHtml defined', /function escapeHtml\(/.test(script));
check('escapeAttr defined', /function escapeAttr\(/.test(script));
check('confirmDialog defined', /function confirmDialog\(/.test(script));
check('toast element has class="toast" id="toast" in static HTML', /<div class="toast" id="toast"><\/div>/.test(html));
check('no native alert() or confirm()', !/(^|[^.\w])(alert|confirm)\(/.test(script));
check('theme-color meta has id="themeColorMeta"', /<meta name="theme-color"[^>]*id="themeColorMeta"/.test(html));
check('meta description present', /<meta name="description"/.test(html));
check('viewport meta has viewport-fit=cover', /viewport-fit=cover/.test(html));
check('apple-mobile-web-app-capable present', /name="apple-mobile-web-app-capable" content="yes"/.test(html));
check('mobile-web-app-capable present', /name="mobile-web-app-capable" content="yes"/.test(html));
check('body has overscroll-behavior-y: contain', /overscroll-behavior-y:\s*contain/.test(html));
check('safe-area insets used', /env\(safe-area-inset-bottom/.test(html) && /env\(safe-area-inset-top/.test(html));
check('Axis BIM Dark baseline tokens at :root',
  /--paper:#0E1220/.test(html) && /--card:#141829/.test(html) && /--ink:#E7E4F4/.test(html) && /--accent:#7C5CFC/.test(html));
check('light theme lives under :root[data-theme="light"]', /:root\[data-theme="light"\]/.test(html));
check('zero border-radius rule present', /\*\{box-sizing:border-box;border-radius:0\}/.test(html));
check('buttons set explicit color', /button\{[^}]*color:var\(--ink\)/.test(html));
const textInputs = html.match(/<input[^>]*type="(text|url)"[^>]*>/g) || [];
check('text/url inputs (if any) set font-size:16px', textInputs.length === 0 || /input\[type=(text|url)\][^}]*font-size:16px/.test(html));
check('no hardcoded hex colours inside component rules (outside :root blocks)',
  (() => {
    const css = (html.match(/<style>([\s\S]*?)<\/style>/) || [])[1] || '';
    const stripped = css.replace(/:root\[?[^{]*\{[^}]*\}/g, '');
    return !/#[0-9a-fA-F]{3,8}\b/.test(stripped.replace(/rgba\([^)]*\)/g, ''));
  })());

sectionHeader('Comment-free index.html (template rule 2026-09-11)');
check('only the one header comment block in HTML', (html.match(/<!--/g) || []).length === 1);
check('no /* */ comments in index.html', !/\/\*/.test(html));
check('no // line comments in script', !/^\s*\/\/(?!\/)/m.test(script) && !/;\s*\/\/\s/.test(script));

sectionHeader('Deploy files');
check('netlify.toml publishes "."', /publish = "\."/.test(toml));
check('netlify.toml sets no-cache on index.html', /for = "\/index\.html"[\s\S]*?no-cache/.test(toml));
check('README.md exists with no emoji or badges',
  fs.existsSync(path.join(dir, 'README.md')) && !/[\u{1F300}-\u{1FAFF}]|!\[/u.test(read('README.md')));
check('only expected files in repo folder',
  fs.readdirSync(dir).every(f => ['index.html', 'netlify.toml', 'README.md', 'CHANGELOG.md', 'audit_deploy.js', 'test_runtime.py', 'test_data.py', 'test_exporter.py', 'node_modules', 'package.json', 'package-lock.json', 'vendor', 'shots', 'tools', 'data'].includes(f)));

sectionHeader('v1.0.0 STRATA invariants');
check('three.js pinned to r128 on cdnjs', /cdnjs\.cloudflare\.com\/ajax\/libs\/three\.js\/r128\/three\.min\.js/.test(html));
check('only network call is one same-origin fetch of the two bundled data files (no sockets, beacons or remote URLs)',
  (script.match(/fetch\(/g) || []).length === 1 && /function fetchJson\(url\)/.test(script) && !/XMLHttpRequest|WebSocket|sendBeacon/.test(script) &&
  /cu: 'data\/cubems_week\.json', wx: 'data\/nyc_weather\.json'/.test(script));
check('seeded PRNG mulberry32 defined', /function mulberry32\(/.test(script));
check('no Math.random() in data generation (only in reseed)',
  (() => {
    const calls = script.match(/Math\.random\(\)/g) || [];
    return calls.length === 1 && /let seed = Math\.floor\(Math\.random\(\)/.test(script);
  })());
check('sample() is stateless: takes (z, m) and reads no mutable sim state except seed',
  (() => {
    const body = (script.match(/function sample\(z, m\) \{([\s\S]*?)\n\}\n/) || [])[1] || '';
    return body.length > 0 && !/state\.t\b|state\.playing|cur\[/.test(body);
  })());
check('imperial and metric conversions defined for temp, area, lux',
  /kind === 'temp'\) return v \* 9 \/ 5 \+ 32/.test(script) && /SQM_TO_SQFT/.test(script) && /kind === 'lux'/.test(script));
check('unit toggle buttons present for both systems', /data-u="imperial"/.test(html) && /data-u="metric"/.test(html));
check('localStorage access always wrapped in try/catch',
  (() => {
    const uses = (script.match(/localStorage\./g) || []).length;
    const wrapped = (script.match(/try \{[^}]*localStorage\./g) || []).length;
    return uses > 0 && uses === wrapped;
  })());
check('all top-level const/let declared before init() call (temporal dead zone guard)',
  (() => {
    const initCall = script.lastIndexOf('\ninit();');
    const after = script.slice(initCall);
    return initCall > 0 && !/^(const|let) /m.test(after);
  })());
check('scrubber covers exactly one week of minutes', /max="10079"/.test(html));
check('reseed goes through confirmDialog', /await confirmDialog\(/.test(script));
check('floor strip includes an "All" reset', /data-f="-1"/.test(script));
check('planted faults defined (stuck and fail)', /kind: 'stuck'/.test(script) && /kind: 'fail'/.test(script));
check('prefers-reduced-motion respected', /prefers-reduced-motion/.test(script) && /prefers-reduced-motion/.test(html));

sectionHeader('v1.0.0 click-stability (found in headless test before first release)');
check('alert list is not rebuilt on every refresh tick (root cause: innerHTML swap at 4 Hz detached the button between pointerdown and pointerup, dropping taps)',
  /ul\.dataset\.sig !== sig/.test(script) && /querySelector\('small'\)\.textContent/.test(script));
check('alert button markup does not embed the changing value', !/<small>' \+ escapeHtml\(fmt\(a\.kind/.test(script));

sectionHeader('v1.0.1 help panel');
check('Help button and overlay exist', /id="helpBtn"/.test(html) && /<div class="modal" id="help" hidden>/.test(html));
check('help overlay has dialog role, aria-modal and a labelled title', /id="help"[\s\S]*?role="dialog" aria-modal="true" aria-labelledby="helpTitle"/.test(html) && /id="helpTitle"/.test(html));
check('help closes on Escape and returns focus to the Help button', /e\.key === 'Escape'\) closeHelp\(\)/.test(script) && /helpBtn\.focus\(\)/.test(script));
check('help text explains both data sources and their limits', /CU-BEMS replay is the default/.test(html) && /Simulated is generated from an office schedule/.test(html) && /does not explain its loads/.test(html));
check('help alert thresholds match the code (2 kW after-hours HVAC, 26 C occupied)',
  /r\.s < 0\.15 && r\.kwAC > 2\)/.test(script) && /r\.f > 0\.25 && r\.T > 26 && !r\.estT\)/.test(script) &&
  /more than 2 kW of HVAC power/.test(html) && /above 26 °C \(79 °F\)/.test(html));
check('help describes planted faults and points to the Simulation note instead of hard-coding days',
  /Two faults are planted/.test(html) && /note at the bottom of the panel says which zones and when/.test(html) && !/Wednesday evening/.test(html));
check('help speed descriptions match SPEEDS', /const SPEEDS = \[1, 60, 600, 3600\]/.test(script) && /60× is one simulated minute per second, 600× is ten minutes per second, 3600× is one hour per second/.test(html));
check('help card scrolls inside the viewport', /\.help-card\{[^}]*max-height:calc\(100dvh - 32px\);overflow-y:auto/.test(html));
check('every layer has a hover hint', (script.match(/hint: '/g) || []).length === 5);

sectionHeader('v1.1.0 New simulated building changes the building');
check('reference layout is seven floors and 33 zones (CU-BEMS count)',
  (() => {
    const m = script.match(/const REF_FLOORS = \[([^\]]+)\]/);
    if (!m) return false;
    const f = m[1].split(',').map(x => parseInt(x, 10));
    return f.length === 7 && f.reduce((x, y) => x + y, 0) === 33;
  })());
check('no fixed FLOOR_ZONES / PLATE_W / PLATE_D constants remain (layout comes from makeLayout)', !/FLOOR_ZONES|PLATE_W|PLATE_D/.test(script) && /function makeLayout\(/.test(script));
check('at least five building archetypes', (script.match(/\{ name: '[^']+', desc:/g) || []).length >= 5);
check('layout varies floors, footprint, schedule and climate', /layout\.floors|floors: floors/.test(script) && /w: Math\.round\(40/.test(script) && /shift: -1\.5/.test(script) && /climate: -10/.test(script));
check('schedule, occupancy and outdoor temperature read the layout', /layout\.shift/.test(script) && /layout\.weekend/.test(script) && /layout\.climate/.test(script));
check('New simulated building never reuses the reference seed by accident', /if \(seed === DEFAULT_SEED\) seed\+\+/.test(script));
check('Reference office button exists and is disabled while already showing it', /id="refBtn"/.test(html) && /\$\('#refBtn'\)\.disabled = layout\.ref/.test(script));
check('floor filter resets and camera reframes whenever a building is built', /state\.floor = -1;\s*state\.skippedRooms = 0;\s*zones = state\.model/.test(script) && /frameCamera\(\);\s*applyFloorFilter\(\)/.test(script));
check('kW colour range is computed per building from its own week (99th percentile, rounded up) and shared by legend and colours',
  /function computeRanges\(\)/.test(script) && /0\.99/.test(script) && /function niceCeil\(/.test(script) &&
  /const R = rangeOf\(L\);\s*\$\('#legendLo'\)/.test(script) && /\(v - R\.lo\) \/ \(R\.hi - R\.lo\)/.test(script));
check('Simulation note is generated from the faults, not hard-coded days', /Planted faults: stuck cooling in/.test(script) && !/Wednesday night and Thursday afternoon/.test(script));

sectionHeader('v1.2.0 Revit model import');
const exporter = fs.existsSync(path.join(dir, 'tools', 'revit_export_rooms.py')) ? read('tools/revit_export_rooms.py') : '';
check('exporter exists', exporter.length > 0);
check('schema tag identical in viewer and exporter',
  (script.match(/const MODEL_SCHEMA = '([^']+)'/) || [])[1] === (exporter.match(/SCHEMA = "([^"]+)"/) || [])[1] && !!(exporter.match(/SCHEMA = "([^"]+)"/)));
check('exporter is read-only: no Transaction, Delete, Set or Create calls',
  !/Transaction|\.Delete\(|\.Set\(|\.Create\w*\(|doc\.Regenerate/.test(exporter));
check('exporter avoids version-sensitive ElementId integer APIs and unit helpers', !/IntegerValue|\.Value\b|UnitUtils|UnitTypeId|DisplayUnitType/.test(exporter));
check('exporter converts feet with fixed constants (0.3048, 0.09290304)', /FT = 0\.3048/.test(exporter) && /SQFT = 0\.09290304/.test(exporter));
check('exporter runs only inside Dynamo (guards on IN)', /if "IN" in globals\(\):/.test(exporter));
check('exporter is Python 3.9 compatible: no match statement, no X | Y type unions', !/^\s*match\s/m.test(exporter) && !/: \w+ \| \w+/.test(exporter));
check('exporter documents Revit Architecture Rooms and the two optional parameters', /STRATA_Zone/.test(exporter) && /STRATA_Sensor/.test(exporter) && /CPython3/.test(exporter));
check('viewer validates a model before using it (checkModel before normalizeModel)', /const err = checkModel\(obj\);\s*if \(err\) \{[\s\S]*?return false;[\s\S]*?state\.model = normalizeModel\(obj\)/.test(script));
check('saved model is re-validated on load', /if \(!checkModel\(o\)\) state\.model = normalizeModel\(o\)/.test(script));
check('model limits defined (zones, points, bytes)', /MAX_MODEL_ZONES = 600/.test(script) && /MAX_MODEL_POINTS/.test(script) && /MAX_MODEL_BYTES = 25 \* 1024 \* 1024/.test(script));
check('model files are read locally with FileReader, never fetched', /new FileReader\(\)/.test(script) && /function fetchJson\(url\)/.test(script) && !/fetch\(file|fetch\(obj|fetch\(text/.test(script));
check('zone names from the model are escaped before innerHTML', /escapeHtml\(z\.sensor\)/.test(script) && /escapeHtml\(zoneLabel\(z\) \+ ' · ' \+ a\.text\)/.test(script));
check('imported zones use the same simulation fields as generated zones (profile draw order matches buildZones)',
  /const density = 8 \+ rnd\(\) \* 6;\s*return \{/.test(script) && /util: 0\.55 \+ 0\.45 \* rnd\(\),\s*arrive: \(rnd\(\) - 0\.5\) \* 40,\s*lightW: 6 \+ rnd\(\) \* 4,\s*plugW: 4 \+ rnd\(\) \* 5,\s*acEff: 0\.8 \+ rnd\(\) \* 0\.5,\s*bias: \(rnd\(\) - 0\.5\) \* 1\.6,\s*win: rnd\(\)/.test(script));
check('Y-up conversion: shape rotated about X by -90 degrees so Revit north maps to -Z', /g\.rotateX\(-Math\.PI \/ 2\)/.test(script));
check('Remove model and Load buttons exist, file input is hidden', /id="loadModel"/.test(html) && /id="modelFile" accept="\.json,application\/json" hidden/.test(html));
check('help explains the Revit export steps and file name', /tools\/revit_export_rooms\.py/.test(html) && /CPython3/.test(html) && /Remove model returns to the reference office/.test(html));
check('sample model present and uses the schema', fs.existsSync(path.join(dir, 'data', 'sample_model.json')) && JSON.parse(read('data/sample_model.json')).schema === 'strata-model-1');

sectionHeader('v1.2.1 density layer');
check('density layer defined with unit-aware kind', /dens: \{ label: 'Density'/.test(script) && /kind: 'wm2'/.test(script));
check('sample() returns wm2 = kW * 1000 / zone area', /wm2: \(kwLight \+ kwPlug \+ kwAC\) \* 1000 \/ z\.area/.test(script));
check('W/ft2 and W/m2 conversion matches the area conversion', /kind === 'wm2'\) return v \/ SQM_TO_SQFT/.test(script) && /'W\/ft²' : 'W\/m²'/.test(script));
check('building density is area-weighted, not a plain mean', /L\.agg === 'area'/.test(script) && /sum \+= v \* zones\[i\]\.area/.test(script));
check('density colour range computed per building', /\['power', 'hvac', 'dens'\]\.forEach/.test(script));
check('help explains Density', /<dt>Density<\/dt>/.test(html) && /area-weighted/.test(html));

sectionHeader('v1.2.2 unconditioned spaces');
check('name heuristic covers roof, shaft and stair', /const UNCOND_RE = \/[^\n]*roof\|shaft\|stair/.test(script));
check('explicit conditioned flag beats the name guess', /mz\.conditioned === true \? true : mz\.conditioned === false \? false : !UNCOND_RE/.test(script));
check('sample() zeroes HVAC for unconditioned zones and lets temperature follow the weather', /kwAC = cond \? kwAC \* \(1 - 0\.8 \* fail\)/.test(script) && /: to \+ 1\.5 \* day \+ noise/.test(script));
check('faults are drawn from conditioned zones only', /if \(z\.cond !== false\) pool\.push\(i\)/.test(script) && /buildFaults\(state\.seed, zones\)/.test(script));
check('generated zones are always conditioned', /win: rnd\(\),\s*cond: true,/.test(script));
check('loading a model switches Power to Density', /const switched = state\.layer === 'power';/.test(script) && /state\.layer = 'dens'/.test(script));
check('exporter reads STRATA_Conditioned and writes an optional conditioned field', /PARAM_COND = "STRATA_Conditioned"/.test(exporter) && /"conditioned": None/.test(exporter) && /def parse_cond/.test(exporter));
check('help documents the unconditioned rule and the override parameter', /treated as unconditioned/.test(html) && /STRATA_Conditioned/.test(html));

sectionHeader('v1.2.3 stepped-site level heights (found loading the real Snowdon export)');
check('viewer sets level height from the next level at least MIN_STOREY higher', /const MIN_STOREY = 2;/.test(script) && /if \(d >= MIN_STOREY\) return clamp\(d, MIN_LEVEL_H, MAX_LEVEL_H\)/.test(script));
check('normalizeModel applies storeyHeights so old files and the saved copy are corrected', /const hs = storeyHeights\(levels\);\s*levels\.forEach\(\(l, i\) => \{ l\.height = hs\[i\]; \}\);/.test(script));
check('exporter uses the same rule and constants', /MIN_STOREY = 2\.0/.test(exporter) && /if d >= MIN_STOREY:/.test(exporter) && /MIN_LEVEL_H = 2\.4/.test(exporter) && /MAX_LEVEL_H = 6\.0/.test(exporter));

sectionHeader('v1.3.0 CU-BEMS replay');
const cubemsPath = path.join(dir, 'data', 'cubems_week.json');
const wxPath = path.join(dir, 'data', 'nyc_weather.json');
check('both data files ship in data/', fs.existsSync(cubemsPath) && fs.existsSync(wxPath));
const cuData = fs.existsSync(cubemsPath) ? JSON.parse(fs.readFileSync(cubemsPath, 'utf8')) : null;
const wxData = fs.existsSync(wxPath) ? JSON.parse(fs.readFileSync(wxPath, 'utf8')) : null;
check('CU-BEMS file is one week at 10 minute steps and every series has 1008 samples',
  !!cuData && cuData.meta.samples === 1008 && cuData.meta.step_min === 10 &&
  cuData.zones.every(z => ['ac', 'light', 'plug', 'temp', 'rh', 'lux'].every(k => z[k] === undefined || z[k].length === 1008)));
check('REF_FLOORS equals the CU-BEMS zones per floor', !!cuData && (() => {
  const m = script.match(/const REF_FLOORS = \[([^\]]+)\]/);
  const want = {};
  cuData.zones.forEach(z => { want[z.floor] = (want[z.floor] || 0) + 1; });
  const w = Object.keys(want).map(Number).sort((x, y) => x - y).map(k => want[k]);
  return !!m && m[1].split(',').map(x => parseInt(x, 10)).join() === w.join();
})());
check('weather file is a week of hourly temperature and humidity', !!wxData && wxData.meta.step_min === 60 && wxData.tempC.length === 168 && wxData.rh.length === 168);
check('sample() routes to the data feed only when data mode is ready', /function sample\(z, m\) \{\s*return dataMode\(\) \? dataSample\(z, m\) : simSample\(z, m\);/.test(script) && /function dataMode\(\) \{ return state\.source === 'data' && DATA\.status === 'ready'/.test(script));
check('data is only fetched over http, never from file://', /location\.protocol === 'file:'/.test(script) && /DATA\.status = 'unavailable'/.test(script));
check('bad or missing data falls back to the simulation', /DATA\.status = 'error'/.test(script) && /Showing the simulation instead/.test(script) && /function checkData\(cu, wx\)/.test(script) && /const err = checkData\(res\[0\], res\[1\]\)/.test(script));
check('flat sensor runs are masked, not trusted (FLAT_RUN)', /const FLAT_RUN = 36/.test(script) && /i - s0 >= FLAT_RUN/.test(script));
check('estimated temperature and humidity are flagged and never raise Running warm', /estT: cond && S\.tEst\[near\] === 1/.test(script) && /estRH: cond/.test(script) && /!r\.estT\)/.test(script));
check('zone card labels estimated and unmetered values', /\(estimated\)/.test(script) && /\(not metered\)/.test(script) && /Readings from/.test(script));
check('missing meters read zero instead of an invented load', /S\[ch\]\[i\] = isNum\(z\[ch\]\[i\]\) && z\[ch\]\[i\] > 0 \? z\[ch\]\[i\] : 0/.test(script));
check('people are inferred from lighting plus plug load and labelled estimated', /lp\[i\] = S\.light\[i\] \+ S\.plug\[i\]/.test(script) && /People \(estimated\)/.test(script));
check('weather and building origin are stated honestly in the UI and help', /New York weather/.test(script) && /Bangkok/.test(script) && /does not explain its loads/.test(html) && /does not drive the Bangkok building/.test(script));
check('imported zones borrow a source zone by floor and scale by area', /z\.index % list\.length/.test(script) && /z\.area \/ \(REF_AREA \/ list\.length\)/.test(script));
check('Data source switch exists and the choice is remembered', /id="srcSeg"/.test(html) && /store\('source', src\)/.test(script) && /load\('source', 'data'\)/.test(script));
check('test_data.py exists', fs.existsSync(path.join(dir, 'test_data.py')));

sectionHeader('v1.3.1 Help accuracy');
check('Help no longer says the numbers are generated', !/numbers are generated for now/.test(html) && /replays one week of measured data/.test(html));
check('Help Temp layer explains estimated temperature', /Temp<\/dt>\s*<dd>[^<]*estimated for every zone before about Wednesday 3 PM/.test(html));
check('Help Estimates explains masking, fill order and occupancy effect', /6 hours or more of an identical reading/.test(html) && /from the same floor, then the whole building/.test(html) && /empty zone[^.]*estimated warmer/.test(html) && /labelled not metered/.test(html));

sectionHeader('v1.4.0 Data-quality overlay');
check('each layer declares which zones are estimated', /est: r => !!r\.estLoad/.test(script) && /est: r => !!r\.estAC/.test(script) && /est: r => !!r\.estT/.test(script) && /inferred: true/.test(script));
check('data samples flag unmetered loads and no-HVAC-meter zones', /estLoad: cond && \(!S\.has\.ac \|\| !S\.has\.light \|\| !S\.has\.plug\)/.test(script) && /estAC: cond && !S\.has\.ac/.test(script));
check('estimated zones are faded with dashed edges', /LineDashedMaterial/.test(script) && /mu\.dash\.visible = est/.test(script) && /est \? 0\.5 : 0\.94/.test(script));
check('overlay only applies in replay mode (markOn)', /function markOn\(\) \{ return state\.mark && dataMode\(\); \}/.test(script));
check('trend chart dashes estimated stretches', /function estSeriesFor\(L\)/.test(script) && /setLineDash\(estS\[i\] \? \[4, 3\] : \[\]\)/.test(script) && /dashed = estimated/.test(script));
check('legend key counts estimated zones and says People is inferred', /id="legendQa"/.test(html) && /zones estimated now/.test(script) && /All values are inferred from lighting and plug load/.test(script));
check('Marked / Unmarked switch exists and the choice is remembered', /id="qaSeg"/.test(html) && /store\('mark'/.test(script) && /load\('mark', 'on'\)/.test(script));
check('Help explains marking estimates', /<dt>Marking estimates<\/dt>/.test(html) && /dashed edges/.test(html));

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
