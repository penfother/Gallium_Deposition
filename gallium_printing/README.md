# Gallium Printing

Control software for shear-driven direct-write deposition of gallium-based liquid metals. Built for a 4-axis Zaber stage system (X, Y, Z + syringe pump) with Arduino-based contact detection.

## Hardware

- **Stages:** 4× Zaber X-LSM series linear stages (X: 100 mm, Y: 200 mm, Z: 50 mm, Syringe: 50 mm)
- **Contact sensing:** Arduino Uno hardware interrupt on Pin 2
- **Nozzle:** Blunt-tip dispensing needles (30G–34G), currently 34G (60 µm ID)

## Setup

Install dependencies:

```
pip install -r requirements.txt
```

Run:

```
python run.py
```

## Commands

### Motion
| Command | Description |
|---------|-------------|
| `move x 10` | Relative move (mm) |
| `move abs x 50` | Absolute move (mm) |
| `home x` | Home single axis |
| `home all` | Home all stages |
| `sethome x` | Set current position as home |
| `speed x 2.5` | Set axis speed (mm/s) |
| `getspeed x` | Read current speed |

### Syringe
| Command | Description |
|---------|-------------|
| `syringe dispense 1` | Dispense (mm plunger travel) |
| `syringe retract 1` | Retract |
| `syringe speed 2` | Set plunger speed (mm/s) |
| `syringe pressure 30` | Set motor current as pressure proxy (0–70) |

### Contact Detection
| Command | Description |
|---------|-------------|
| `approach x 0.05` | Manual fine approach (W/S keys, X to exit) |
| `touchdown` | Precision contact measurement (3× averaged) |

### Substrate Mapping
| Command | Description |
|---------|-------------|
| `mappoint` | Run touchdown at current XY, store as substrate corner |
| `mapshow` | Print current map (corners, plane fit, safe area) |
| `mapclear` | Reset substrate map |

Workflow: jog XY to each of the 4 substrate corners, run `mappoint` at each. After the 4th point, a plane is fitted and a safe deposition rectangle is computed. During deposition, Z automatically tracks the fitted plane to maintain constant standoff height.

### Deposition
| Command | Description |
|---------|-------------|
| `setstart` | Save current XYZ as deposition start position |
| `makeline 10 x 2 0.001 0.01` | Deposit a line: length (mm), direction, v_stage (mm/s), Q (mm³/s), h0 (mm) |
| `sweep` | Interactive 2-parameter sweep (100 lines: 10 × 10 grid) |

### Other
| Command | Description |
|---------|-------------|
| `help` | Print all commands |
| `ESC` | Emergency stop (all axes) |
| `exit` | Quit |

## Project Structure

```
gallium_printing/
├── config/
│   └── constants.py        # Device serial numbers, syringe specs, approach parameters
├── core/
│   ├── contact.py          # Arduino listener, manual approach, touchdown routine
│   ├── deposition.py       # make_line, sweep, make_dots
│   ├── logging.py          # Session logging
│   ├── substrate_mapping.py # SubstrateMap, plane fitting, safe area, Z compensation
│   └── zaber_wrapper.py    # ZaberDevice class (motion, limits, speed profiles, syringe)
├── main.py                 # CLI, command dispatch, connections
└── requirements.txt
```

## Dependencies

- `zaber-motion` — Zaber stage communication
- `pyserial` — Arduino serial communication
- `keyboard` — Hotkey binding (ESC emergency stop, W/S approach)
- `numpy` — Plane fitting, parameter sweeps
