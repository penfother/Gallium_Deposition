import os
import datetime
import csv

import numpy as np

from gallium_printing.core.zaber_wrapper import ZaberDevice
from gallium_printing.config.constants import SYRINGE
from gallium_printing.core.substrate_mapping import SubstrateMap, z_velocity_for_line

# -----------------------------------------------------------------------------------
# DOTS -> Not fully implemented
# -----------------------------------------------------------------------------------
def make_dots(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
              dots: int, spacing: float, dispense_amount: float) -> None:
    '''From the start position dispenses dots along the desired axis'''
    # TODO: Fix the start position capability
    # TODO: Change the speed profile for the printing of dots
    # TODO: do the z approach for each dot
    # TODO: Limit the dispensing amount in a range
    # TODO: Make this give back a string that gives the error or if it does everything
    #       correctly give back printed

    stage_x.set_speed(0.2)



    for i in range(dots):
        # Approach 2 mm to the stage
        stage_z.move_rel(2, wait=True)
        syringe.syringe_dispense(dispense_amount, wait=True)

        stage_z.move_rel(-2, wait=True)
        if i < dots - 1:
            stage_x.move_rel(spacing, wait=True)

    stage_x.home()

# -----------------------------------------------------------------------------------
# MAKE LINE
# -----------------------------------------------------------------------------------
def make_line(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
              start_pos: list, line_length: float, direction: str,
              v_stage: float, Q: float, h0: float,
              substrate_map: SubstrateMap = None) -> None:
    '''Deposits a line from start_pos in given direction.
    v_stage: XY stage speed (mm/s)
    Q: flow rate (mm³/s)
    h0: standoff distance (mm)'''

    if substrate_map is None or substrate_map.plane is None:
        print("[make_line] aborting: substrate map required (need 2 or 4 corners mapped)")
        return

    if direction == "x":
        target = start_pos[0] + line_length
        if target < stage_x.min_pos or target > stage_x.max_pos:
            print(f"[make_line] aborting: x endpoint {target} outside [{stage_x.min_pos}, {stage_x.max_pos}]")
            return
    elif direction == "y":
        target = start_pos[1] + line_length
        if target < stage_y.min_pos or target > stage_y.max_pos:
            print(f"[make_line] aborting: y endpoint {target} outside [{stage_y.min_pos}, {stage_y.max_pos}]")
            return
    else:
        print(f"[make_line] aborting: invalid direction '{direction}'")
        return

    # v_plunger = Q / (π × (D_barrel/2)²) -> continuity equation
    barrel_area = 3.14159265 * ((SYRINGE["barrel_inner_diameter_mm"] / 2) ** 2)
    v_plunger = Q / barrel_area

    # Set speeds
    stage_x.set_speed(v_stage)
    stage_y.set_speed(v_stage)
    stage_z.set_speed(0.2)
    syringe.set_speed(v_plunger)

    # Move XY to start position
    stage_x.move_abs(start_pos[0], wait=True)
    stage_y.move_abs(start_pos[1], wait=True)

    # Calculate Z position
    x0, y0 = start_pos[0], start_pos[1]
    if direction == "x":
        x1, y1 = x0 + line_length, y0
    else:
        x1, y1 = x0, y0 + line_length
    a, b, c = substrate_map.plane
    z_start, z_end, v_z = z_velocity_for_line(a, b, c, x0, y0, x1, y1, h0, v_stage)
    stage_z.move_abs(z_start, wait=True)

    # Dispense - finishes at the same time as the stage movement
    plunger_travel = (Q / barrel_area) * (line_length / v_stage)
    syringe.syringe_dispense(plunger_travel, wait=False)

    # Start Z tracking
    if v_z and v_z != 0:
        stage_z.set_speed(abs(v_z))
        stage_z.move_abs(z_end, wait=False)

    # Stage movement
    axis = stage_x if direction == "x" else stage_y
    axis.move_rel(line_length, wait=True)

    # Raise Z
    stage_z.set_speed(2.0)
    stage_z.move_rel(-2, wait=True)

# -----------------------------------------------------------------------------------
# SWEEP HELPERS
# -----------------------------------------------------------------------------------
def _validate_sweep_area(line_length: float, direction: str, perp_span: float,
                         start_pos: list, substrate_map: SubstrateMap = None) -> bool:
    '''Checks if sweep fits within the mapped safe area. Returns True if valid.'''
    if not (substrate_map and substrate_map.safe_area):
        return True

    x_min, y_min, x_max, y_max = substrate_map.safe_area

    if direction == "x":
        par_limit, perp_limit = x_max - x_min, y_max - y_min
    else:
        par_limit, perp_limit = y_max - y_min, x_max - x_min

    if abs(line_length) > par_limit:
        print(f"Line length {line_length} mm exceeds safe area ({round(par_limit, 3)} mm).")
        return False
    if perp_span > perp_limit:
        print(f"Sweep span {round(perp_span, 3)} mm exceeds safe area ({round(perp_limit, 3)} mm).")
        return False
    if not (x_min <= start_pos[0] <= x_max and y_min <= start_pos[1] <= y_max):
        print("Start position is outside the safe area.")
        return False

    print(f"Sweep footprint: {abs(line_length)} x {round(perp_span, 3)} mm — fits within safe area.")
    return True

def _create_sweep_csv() -> str:
    '''Creates a timestamped CSV file for sweep logging. Returns the file path.'''
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, f"sweep_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

    header = [
        "line_number", "timestamp",
        "v_stage", "h0", "Q", "v_star", "h0_over_ID",
        "direction",
        "x_start", "y_start", "z_start",
        "x_end", "y_end", "z_end",
        "line_length"
    ]

    with open(csv_path, "w", newline="") as f:
        csv.writer(f).writerow(header)

    return csv_path

def _log_sweep_line(csv_path: str, line_number: int, params: dict,
                    direction: str, actual_length: float,
                    x0: float, y0: float, z0: float,
                    x1: float, y1: float, z1: float) -> None:
    '''Appends one row to the sweep CSV.'''
    nozzle_id = SYRINGE["nozzle_inner_diameter_mm"]
    v_star = round(4 * params["Q"] / (3.14159265 * nozzle_id**2 * params["v_stage"]), 4)
    h0_over_id = round(params["h0"] / nozzle_id, 4)

    row = [
        line_number,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        params["v_stage"], params["h0"], params["Q"],
        v_star, h0_over_id,
        direction,
        round(x0, 4), round(y0, 4), round(z0, 4),
        round(x1, 4), round(y1, 4), round(z1, 4),
        actual_length
    ]

    with open(csv_path, "a", newline="") as f:
        csv.writer(f).writerow(row)

# -----------------------------------------------------------------------------------
# SWEEP
# -----------------------------------------------------------------------------------
def sweep(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
          start_pos: list, line_length: float, direction: str,
          split: float, fixed: dict, swept: dict,
          substrate_map: SubstrateMap = None) -> None:
    '''Runs a 2-parameter sweep of deposition lines.
    Always 10 steps per parameter = 100 lines total.'''

    gap_width = 3 * SYRINGE["nozzle_inner_diameter_mm"]
    perp_span = 10 * (9 * gap_width) + 9 * split

    if not _validate_sweep_area(line_length, direction, perp_span, start_pos, substrate_map):
        return

    csv_path = _create_sweep_csv()
    print(f"Sweep CSV: {csv_path}")

    v_stage = fixed.get("v_stage")
    Q       = fixed.get("Q")
    h0      = fixed.get("h0")

    outer_name, inner_name = swept.keys()
    outer_range = np.linspace(*swept[outer_name], 10)
    inner_range = np.linspace(*swept[inner_name], 10)

    current_pos = start_pos.copy()
    params = {"v_stage": v_stage, "Q": Q, "h0": h0}
    n = 0

    for outer_val in outer_range:
        params[outer_name] = outer_val

        for inner_val in inner_range:
            params[inner_name] = inner_val

            actual_length = line_length if n % 2 == 0 else -line_length

            x0 = stage_x.position()
            y0 = stage_y.position()
            z0 = stage_z.position()

            make_line(stage_x, stage_y, stage_z, syringe,
                      current_pos, actual_length, direction,
                      params["v_stage"], params["Q"], params["h0"],
                      substrate_map)

            x1 = stage_x.position()
            y1 = stage_y.position()
            z1 = stage_z.position() + 5

            _log_sweep_line(csv_path, n + 1, params, direction, actual_length,
                            x0, y0, z0, x1, y1, z1)

            if direction == "x":
                current_pos[1] += gap_width
            elif direction == "y":
                current_pos[0] += gap_width

            n += 1

        if direction == "x":
            current_pos[1] += split
        elif direction == "y":
            current_pos[0] += split

    print(f"Sweep complete — {n} lines logged to {os.path.basename(csv_path)}")

def _confirm_sweep(line_length: float, direction: str, perp_span: float,
                   fixed: dict, swept: dict, gap_width: float) -> bool:
    '''Prints sweep plan and asks for confirmation. Returns True if user confirms.'''
    nozzle_id = SYRINGE["nozzle_inner_diameter_mm"]
    outer_name, inner_name = swept.keys()
    outer_start, outer_end = swept[outer_name]
    inner_start, inner_end = swept[inner_name]

    print("\n--- Sweep Plan ---")
    print(f"  Direction:    {direction}")
    print(f"  Line length:  {line_length} mm")
    print(f"  Lines:        100 (10 × 10)")
    print(f"  Gap width:    {round(gap_width, 4)} mm")
    print(f"  Footprint:    {abs(line_length)} × {round(perp_span, 3)} mm")

    for name, val in fixed.items():
        print(f"  {name} (fixed): {val}")

    print(f"  {outer_name} (outer): {outer_start} → {outer_end}, 10 steps")
    print(f"  {inner_name} (inner): {inner_start} → {inner_end}, 10 steps")

    # Boley bounds check on extremes
    all_v_stage = [fixed["v_stage"]] if "v_stage" in fixed else np.linspace(*swept["v_stage"], 10).tolist()
    all_Q = [fixed["Q"]] if "Q" in fixed else np.linspace(*swept["Q"], 10).tolist()
    all_h0 = [fixed["h0"]] if "h0" in fixed else np.linspace(*swept["h0"], 10).tolist()

    v_star_min = 4 * min(all_Q) / (3.14159265 * nozzle_id**2 * max(all_v_stage))
    v_star_max = 4 * max(all_Q) / (3.14159265 * nozzle_id**2 * min(all_v_stage))
    h0_id_min = min(all_h0) / nozzle_id
    h0_id_max = max(all_h0) / nozzle_id

    print(f"  v* range:     {round(v_star_min, 4)} → {round(v_star_max, 4)}  (Boley: 0.05–1)")
    print(f"  h0/ID range:  {round(h0_id_min, 4)} → {round(h0_id_max, 4)}  (Boley: 0.03–0.21)")

    print()
    return input("Proceed? (y/n): ").strip().lower() == "y"