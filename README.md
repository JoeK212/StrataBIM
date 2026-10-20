# STRATA

A browser dashboard that colours a 3D building model by power, HVAC, temperature or occupancy, with a replayable timeline, floor isolation and per-zone trends. By Joe.K, [axisbim.io](https://axisbim.io).

It replays one week of measured office data from the CU-BEMS dataset (7 floors, 33 zones, with New York weather outdoors), or runs a simulated feed. Everything is in a single `index.html` with no build step. The Help button explains the controls, layers, alerts and data.

## Run it

Serve the folder over http, for example `python -m http.server 8888`, then open http://localhost:8888. Opened straight from disk, STRATA falls back to the simulation because browsers block the data files. To deploy, use Netlify with the included `netlify.toml`.

## Your own Revit model

Revit Architecture, with Rooms (no MEP Spaces needed):

1. Place Rooms. Optional text parameters: `STRATA_Zone` (rooms with the same value on a level become one zone), `STRATA_Sensor`, and `STRATA_Conditioned` (Yes or No).
2. In Dynamo, add a CPython3 Python Script node, paste in `tools/revit_export_rooms.py` and run it. It only reads the model.
3. In STRATA, choose Load Revit model or drop the JSON on the model. `data/sample_model.json` is a synthetic building to try first.

Loaded models stay in your browser and are remembered locally until removed. The exporter has been tested against stand-in objects, not inside Revit itself.

## About the data

The building is in Bangkok and the weather is New York, so the weather is context and does not drive the loads. The measured data has gaps (temperature sensors start reporting around Wednesday 3 PM, floor 1 has none, some zones lack meters). STRATA estimates them and marks every estimate. People are inferred from lighting and plug load. `tools/prep_cubems.py` and `tools/fetch_weather.py` rebuild the data files.

## Credits

- CU-BEMS: Pipattanasomporn et al., *CU-BEMS, smart building electricity consumption and indoor environmental sensor datasets*, Scientific Data 7, 241 (2020), [doi:10.1038/s41597-020-00582-3](https://doi.org/10.1038/s41597-020-00582-3) (CC BY 4.0). Dataset: [doi:10.6084/m9.figshare.11726517](https://doi.org/10.6084/m9.figshare.11726517) (CC BY 4.0). Changes made: `data/cubems_week.json` is one week of it, reshaped, with gaps estimated in the app. Not endorsed by the authors.
- Weather: [Open-Meteo.com](https://open-meteo.com/), CC BY 4.0. The free API is non-commercial.
- three.js r128 (MIT), loaded from cdnjs.

---
Joe.K · [axisbim.io](https://axisbim.io)
