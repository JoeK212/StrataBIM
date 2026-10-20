# STRATA

A browser dashboard that colours a 3D building model by power, HVAC, temperature or occupancy, with a replayable timeline, floor isolation and per-zone trends.

STRATA replays one week of measured data from the CU-BEMS office dataset (seven floors, 33 zones, AC, lighting and plug loads, temperature, humidity, light level) with New York weather outdoors, or runs a simulated feed shaped like it. The viewer reads one sample function per zone and minute, so the feed behind it can change without touching the interface.

Everything lives in a single index.html with no build step. Open it in a browser, or deploy the repo to Netlify with the included netlify.toml. The 3D view uses three.js r128 from cdnjs.

Display units switch between imperial and metric. The seed, units, layer, speed and theme are remembered in the browser.

Joe.K, axisbim.io

## Using it

The Help button in the header explains the controls, layers, timeline, alert rules, units and where the data comes from.

## Using your own Revit model

Works in Revit Architecture, which has Rooms but not MEP Spaces.

1. In Revit, place Rooms. Optional: add text parameters STRATA_Zone (rooms with the same value on a level become one zone) and STRATA_Sensor (a sensor ID shown on the zone). Roofs, shafts, stairs, terraces and similar are treated as unconditioned (no HVAC) by name; set STRATA_Conditioned to Yes or No on a Room to override.
2. In Dynamo, add a Python Script node, set the engine to CPython3, paste in tools/revit_export_rooms.py and run it. Input 0 is an optional output path, input 1 an optional grouping mode (auto, param, department, room). The script only reads the model.
3. In STRATA, choose Load Revit model or drop the JSON file on the model. data/sample_model.json is a synthetic building to try first.

The exporter uses only long-standing Revit API calls (Room boundary segments, Level elevation, text parameters) and fixed unit constants, so it should not depend on the Dynamo or Python version. It has been tested against stand-in objects, not inside Revit 2027. If it errors in Revit, copy the message from the Dynamo node and it can be fixed quickly.

## Real data (CU-BEMS replay)

data/cubems_week.json and data/nyc_weather.json are loaded when the folder is served over http, for example `python -m http.server 8888` and then http://localhost:8888. Opened straight from disk, STRATA uses the simulation, because browsers block data files on file://. Data source in the panel switches between the two.

tools/prep_cubems.py cuts one week out of the CU-BEMS CSVs into data/cubems_week.json (run it with --inspect first to see how the columns are recognised). tools/fetch_weather.py downloads a week of NYC weather from Open-Meteo into data/nyc_weather.json. Both use only the Python standard library.

What to know about the data: the building is in Bangkok and the weather is New York, so the weather is context and does not drive the loads. Temperature and humidity sensors only start reporting around Wednesday 3 PM, floor 1 has none, and some zones lack an HVAC, lighting or plug meter. STRATA estimates the gaps, labels every estimate in the zone card and the Building note, and shows unmetered loads as zero. People are inferred from lighting and plug load.

## Credits

- Measured building data: CU-BEMS, Pipattanasomporn et al., "CU-BEMS, smart building electricity consumption and indoor environmental sensor datasets", Scientific Data 7, 241 (2020), https://doi.org/10.1038/s41597-020-00582-3 (article CC BY 4.0). Dataset: https://doi.org/10.6084/m9.figshare.11726517. The article does not state a licence for the CSV files, so check the Figshare record before redistributing the data. data/cubems_week.json is one reshaped week of it.
- Weather: Open-Meteo.com historical data, CC BY 4.0, https://open-meteo.com/. Its free API is for non-commercial use, so a commercial deployment needs their paid plan.
- three.js r128, MIT licence, bundled in vendor/.
- Models you load stay in your browser and are remembered locally until removed.
