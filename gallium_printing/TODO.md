TODO - Gallium Printing
========================

--- Commands ---
[ ] pos command - print current XYZ + syringe positions

--- Input validation ---
[ ] handle_command crashes on bad axis name - wrap in try/except or validate
[ ] handle_command crashes on wrong argument count for most commands
[ ] sweep validates parameters, rest of commands do not

--- Sweep ---
[ ] Pause/resume during sweep (p to pause, r to resume, q to abort)
[ ] Confirmation before sweep starts - print full plan and ask y/n
[ ] Boley parameter validation (v* and h0/ID bounds check before motion)
[ ] Estimated total time and syringe consumption printed before start
[ ] Per-line CSV log (line_number, timestamp, all parameters, positions)

--- Deposition ---
[ ] Plunger travel calculation per sweep (will syringe run out mid-sweep?)
[ ] Load cell force measurement to determine actual extrusion pressure
[ ] Speed profiles used properly - named profiles for deposition, retract, approach
[x] Substrate mapping with plane fit and Z compensation
[x] Safe area bounds checking
[x] Z tracking during line deposition

--- Logging ---
[ ] CSV output per sweep - one row per line, all parameters + positions
[ ] Substrate material tag per session
[ ] Save/reload substrate map between sessions

--- Contact ---
[x] Arduino contact detection with hardware interrupt
[x] Precision touchdown (3x averaged)
[x] mappoint uses touchdown for Z measurement
[ ] stop motion and return to command

--- Hardware ---
[ ] Load cell integration (5kg, HX711) - waiting for parts
[ ] Force-pressure calibration for syringe extrusion
[ ] New 3D printed parts (X/Y footing, Arduino holder, load cell pusher)

--- Code cleanup ---
[ ] Refactor handle_command into separate cmd_ functions
[ ] is_complete needs parentheses or @property
[ ] Remove duplicate connect_arduino (contact.py import vs main.py definition)

========================
Boley framework reference:

v* = 4Q / (π · ID² · v)
  where Q = flow rate (mm³/s), ID = nozzle inner diameter (mm), v = stage speed (mm/s)

h₀/ID must be between 0.03 and 0.21
v* must be between 0.05 and 1

For 34G nozzle: ID = 0.06 mm
  max gap height = 0.21 × 0.06 = 0.0126 mm = 12.6 µm
  target range: 5-10 µm gap height, 10 µm is ideal

Line height prediction:
  H = 2.1·h₀ - 0.03·ID

For target H = 20 µm:
  h₀ = (20 + 0.03 × 0.06) / 2.1
  h₀ ≈ 9.5 µm ≈ 10 µm

Hagen-Poiseuille for pressure estimate:
  ΔP = 8μLQ / (πr⁴)
  Still need: viscosity of EGaIn/Gallitherm through 34G nozzle
  Load cell will give force → F/A_barrel = pressure at plunger