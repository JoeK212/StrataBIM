# STRATA

A browser dashboard that colours a 3D building model by power, HVAC, temperature or occupancy, with a replayable timeline, floor isolation and per-zone trends.

This first version runs on a simulated feed shaped like the CU-BEMS office dataset (seven floors, 33 zones, AC, lighting and plug loads, temperature, humidity, light level). The viewer reads one sample function per zone and minute, so a real feed can replace the generator without touching the interface.

Everything lives in a single index.html with no build step. Open it in a browser, or deploy the repo to Netlify with the included netlify.toml. The 3D view uses three.js r128 from cdnjs.

Display units switch between imperial and metric. The seed, units, layer, speed and theme are remembered in the browser.

Joe.K, axisbim.io

## Using it

The Help button in the header explains the controls, layers, timeline, alert rules, units and where the data comes from.

## Using your own Revit model

Works in Revit Architecture, which has Rooms but not MEP Spaces.

1. In Revit, place Rooms. Optional: add text parameters STRATA_Zone (rooms with the same value on a level become one zone) and STRATA_Sensor (a sensor ID shown on the zone).
2. In Dynamo, add a Python Script node, set the engine to CPython3, paste in tools/revit_export_rooms.py and run it. Input 0 is an optional output path, input 1 an optional grouping mode (auto, param, department, room). The script only reads the model.
3. In STRATA, choose Load Revit model or drop the JSON file on the model. data/sample_model.json is a synthetic building to try first.

The exporter uses only long-standing Revit API calls (Room boundary segments, Level elevation, text parameters) and fixed unit constants, so it should not depend on the Dynamo or Python version. It has been tested against stand-in objects, not inside Revit 2027. If it errors in Revit, copy the message from the Dynamo node and it can be fixed quickly.

## Real data (next step)

tools/fetch_weather.py downloads a week of NYC weather from Open-Meteo into data/nyc_weather.json. tools/prep_cubems.py cuts one week out of the CU-BEMS CSVs into data/cubems_week.json; run it with --inspect first to see how the columns are recognised. Both use only the Python standard library. The viewer does not read these files yet.
