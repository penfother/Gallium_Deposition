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

    # v_plunger = Q / (π × (D_barrel/2)²) -> continuity equation
    v_plunger = Q / (3.14159265 * ((SYRINGE["barrel_inner_diameter_mm"] / 2) ** 2))

    # Set speeds
    stage_x.set_speed(v_stage)
    stage_y.set_speed(v_stage)
    stage_z.set_speed(0.2)
    syringe.set_speed(v_plunger)

    # Move XY to start position
    stage_x.move_abs(start_pos[0], wait=True)
    stage_y.move_abs(start_pos[1], wait=True)

    # Calculate Z position
    if substrate_map and substrate_map.is_complete():
        x0, y0 = start_pos[0], start_pos[1]
        if direction == "x":
            x1, y1 = x0 + line_length, y0
        else:
            x1, y1 = x0, y0 + line_length

        a, b, c = substrate_map.plane
        z_start, z_end, v_z = z_velocity_for_line(a, b, c, x0, y0, x1, y1, h0, v_stage)

        stage_z.move_abs(z_start, wait=True)
    else:
        z_start = h0
        v_z = None
        stage_z.move_abs(h0, wait=True)

    syringe.syringe_dispense(line_length, wait=False)

    # Start Z tracking if plane is mapped
    if v_z and v_z != 0:
        stage_z.set_speed(abs(v_z))
        stage_z.move_abs(z_end, wait=False)

    match direction:
        case "x":
            if not stage_x.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_x.move_rel(line_length, wait=True)
        case "y":
            if not stage_y.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_y.move_rel(line_length, wait=True)
        case _:
            print("Invalid direction.")
            syringe.stop()
            stage_z.stop()
            stage_z.move_rel(-1, wait=True)
            return

    # Stop syringe and raise Z
    syringe.stop()
    stage_z.move_rel(-5, wait=True)

# -----------------------------------------------------------------------------------
# SWEEP
# -----------------------------------------------------------------------------------
def sweep(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
          start_pos: list, line_length: float, direction: str,
          split: float, fixed: dict, swept: dict,
          substrate_map: SubstrateMap = None) -> None:
    '''Runs a 2-parameter sweep of deposition lines.
    fixed: dict of fixed parameters e.g. {"v_stage": 2}
    swept: dict of swept parameters e.g. {"Q": (0.001, 0.01), "h0": (0.005, 0.015)}
    Always 10 steps per parameter = 100 lines total.'''

    gap_width = 3 * SYRINGE["nozzle_inner_diameter_mm"]

    v_stage = fixed.get("v_stage")
    Q       = fixed.get("Q")
    h0      = fixed.get("h0")

    outer_name, inner_name = swept.keys()

    outer_start, outer_end = swept[outer_name]
    inner_start, inner_end = swept[inner_name]

    outer_range = np.linspace(outer_start, outer_end, 10)
    inner_range = np.linspace(inner_start, inner_end, 10)

    # Check if sweep fits within safe area
    perp_span = 10 * (9 * gap_width) + 9 * split

    if substrate_map and substrate_map.safe_area:
        x_min, y_min, x_max, y_max = substrate_map.safe_area

        if direction == "x":
            if abs(line_length) > (x_max - x_min):
                print(f"Line length {line_length} mm exceeds safe area width {round(x_max - x_min, 3)} mm.")
                return
            if perp_span > (y_max - y_min):
                print(f"Sweep height {round(perp_span, 3)} mm exceeds safe area height {round(y_max - y_min, 3)} mm.")
                return
            if not (x_min <= start_pos[0] <= x_max and y_min <= start_pos[1] <= y_max):
                print("Start position is outside the safe area.")
                return
        elif direction == "y":
            if abs(line_length) > (y_max - y_min):
                print(f"Line length {line_length} mm exceeds safe area height {round(y_max - y_min, 3)} mm.")
                return
            if perp_span > (x_max - x_min):
                print(f"Sweep width {round(perp_span, 3)} mm exceeds safe area width {round(x_max - x_min, 3)} mm.")
                return
            if not (x_min <= start_pos[0] <= x_max and y_min <= start_pos[1] <= y_max):
                print("Start position is outside the safe area.")
                return

        print(f"Sweep footprint: {abs(line_length)} x {round(perp_span, 3)} mm — fits within safe area.")

    current_pos = start_pos.copy()
    params = {"v_stage": v_stage, "Q": Q, "h0": h0}
    n = 0

    # Starts the sweep
    for outer_val in outer_range:
        params[outer_name] = outer_val

        for inner_val in inner_range:
            params[inner_name] = inner_val

            actual_length = line_length if n % 2 == 0 else -line_length

            make_line(stage_x, stage_y, stage_z, syringe,
                      current_pos, actual_length, direction,
                      params["v_stage"], params["Q"], params["h0"],
                      substrate_map)

            if direction == "x":
                current_pos[1] += gap_width
            elif direction == "y":
                current_pos[0] += gap_width

            n += 1

        if direction == "x":
            current_pos[1] += split
        elif direction == "y":
            current_pos[0] += split 