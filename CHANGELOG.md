v1.2.1 - 2026-10-05 - Add Density layer: power per unit of floor area, so large and small zones compare fairly

Raw kW colours the biggest rooms hottest regardless of how hard they work, which made imported Revit models with very different room sizes hard to read. Density divides each zone's power by its area (W/m² or W/ft² to match the unit toggle), has its own colour range sized to the building's week, shows beside the other readings in the zone card, and plots an area-weighted building figure in the trend chart. Power stays as it was.

v1.2.0 - 2026-10-05 - Load a Revit model: Dynamo Room exporter plus an in-browser importer that extrudes your rooms into coloured zones

tools/revit_export_rooms.py runs in a Dynamo CPython3 Python Script node (Revit Architecture has Rooms, not MEP Spaces). It reads every placed, enclosed Room, converts feet to metres, tessellates curved walls, keeps holes such as shafts, groups rooms into zones by an optional STRATA_Zone text parameter, then Department, then one zone per Room, and carries an optional STRATA_Sensor ID. It opens no transaction and changes nothing in the model. The output is a small strata-model-1 JSON file.

The viewer validates the file before using it (schema tag, level references, point counts, zone limit of 600, 25 MB limit), extrudes each room outline to its level height, merges a zone's rooms into one mesh, re-centres the model, rebuilds the floor strip with Revit level names, and reframes the camera. Readings on an imported model are the same simulated feed until real data is connected. Load with the button or by dropping the file on the model; the last model is remembered in the browser when small enough. Remove model returns to the reference office. data/sample_model.json is a synthetic four-level building with an L-shaped plan, a curved lobby and a shaft hole, for trying the loader without Revit.

The camera zoom limit, grid size and fog now scale with the model so large buildings are not clipped.

v1.1.0 - 2026-10-05 - New simulated building now changes the building: floors, zones, footprint, schedule, climate and fault placement

Previously the button only re-rolled per-zone usage factors, so the model looked the same. A seed now selects a layout of 4 to 10 floors with 3 to 7 zones each, a 40 to 72 m by 22 to 36 m footprint, and one of five archetypes: standard, early-start, late-start studio with weekend work, hot-climate (cooling dominates) and cold-climate (heating appears). Fault zones and days also vary. The camera reframes to fit, the floor strip rebuilds, and the Simulation section describes the building and names the planted faults. A Reference office button returns to the default seven-floor, 33-zone building, which is unchanged from v1.0.x.

v1.0.1 - 2026-10-05 - Add in-app Help: controls, layers, timeline, alert rules, units, data provenance and a short glossary

A Help button in the header opens a scrollable panel written for someone seeing the dashboard for the first time. It states plainly that the data is simulated, lists the two planted faults, and gives the exact alert thresholds (2 kW after-hours HVAC, 26 C occupied) so the text cannot drift from the code; audit_deploy.js checks both. Layer and speed buttons also gained hover hints. Escape, the Close button or a click outside closes the panel, and focus returns to the Help button.

v1.0.0 - 2026-10-05 - Initial release: 3D 7-floor, 33-zone building viewer with simulated replay feed

First version of STRATA. Zones are boxes in a generated 56 m x 30 m plate, seven floors at 4 m pitch. Each zone is coloured by one of four layers: power, HVAC, temperature, occupancy. Data comes from a seeded generator (mulberry32) that is a pure function of (zone, minute), so scrubbing the timeline never depends on earlier playback state. The generator mimics the CU-BEMS channels (AC, lighting, plug kW, temperature, humidity, lux) so the real dataset can replace it without UI changes.

Includes: play/pause, four replay speeds, one-week scrubber, floor isolation strip, click-to-inspect with 24 h trend chart, planted HVAC faults (Wednesday night stuck cooling, Thursday afternoon cooling failure) feeding an alerts list, imperial and metric display with the other unit shown beside temperature, area and light level, Axis BIM Dark default with a light toggle, iOS safe-area and overscroll handling, seed persistence in localStorage.

Outdoor temperature is a placeholder sine curve, not real NYC weather. Zone counts per floor (5,5,5,5,5,4,4) are a placeholder for the real CU-BEMS zone map.

Found and fixed before release: the alerts list was rebuilt with innerHTML on every 4 Hz refresh, which detached the button between pointerdown and pointerup and could drop a tap. The list now rebuilds only when the set of alerting zones changes and updates the readout text in place.
