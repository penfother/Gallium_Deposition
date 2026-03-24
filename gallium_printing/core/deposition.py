import numpy as np

from gallium_printing.core.zaber_wrapper import ZaberDevice
from gallium_printing.config.constants import SYRINGE

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
              v_stage: float, Q: float, h0: float) -> None:
    '''Deposits a line from start_pos in given direction.
    v_stage: XY stage speed (mm/s)
    Q: flow rate (mm³/s)
    h0: standoff distance (mm)'''

    # TODO: Implement the touch sensor for the height adjustment
    # TODO: 

    # v_plunger = Q / (π × (D_barrel/2)²) -> continuity equation
    v_plunger = Q / (3.14159265 * ((SYRINGE["barrel_inner_diameter"] / 2) ** 2))

    # Set speeds
    stage_x.set_speed(v_stage)
    stage_y.set_speed(v_stage)
    stage_z.set_speed(0.2)
    syringe.set_speed(v_plunger)

    # Move XY to start position
    stage_x.move_abs(start_pos[0], wait=True)
    stage_y.move_abs(start_pos[1], wait=True)

    # Drop Z to h0
    stage_z.move_abs(h0, wait=True)

    # Start syringe and line simultaneously
    syringe.syringe_dispense(line_length, wait=False)

    match direction:
        case "x":
            if not stage_x.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_x.move_rel(line_length, wait=True)
        case "y":
            if not stage_y.check_limit(line_length, relative=True):
                syringe.stop()
                stage_z.move_rel(-1, wait=True)
                return
            stage_y.move_rel(line_length, wait=True)
        case _:
            print("Invalid direction.")
            syringe.stop()
            stage_z.move_rel(-1, wait=True)
            return

    # Stop syringe and raise Z
    syringe.stop()
    stage_z.move_rel(-5, wait=True)

# -----------------------------------------------------------------------------------
# SWEEP -> not fully implemented
# -----------------------------------------------------------------------------------
def sweep(stage_x: ZaberDevice, stage_y: ZaberDevice, stage_z: ZaberDevice, syringe: ZaberDevice,
          start_pos: list, line_length: float, direction: str,
          split: float, fixed: dict, swept: dict) -> None:
    '''Runs a 2-parameter sweep of deposition lines.
    fixed: dict of fixed parameters e.g. {"v_stage": 2}
    swept: dict of swept parameters e.g. {"Q": (0.001, 0.01, 0.001), "h0": (0.005, 0.015, 0.001)}'''

    # gap between lines within a group
    gap_width = 3 * SYRINGE["nozzle_inner_diameter_mm"]

    # unpack fixed parameter
    v_stage = fixed.get("v_stage", 1.0)
    Q       = fixed.get("Q", 0.001)
    h0      = fixed.get("h0", 0.01)

    # unpack swept parameters
    param_names = list(swept.keys())
    if len(param_names) != 2:
        print("Sweep requires exactly 2 swept parameters.")
        return

    # outer and inner parameter ranges
    outer_name = param_names[0]
    inner_name = param_names[1]

    outer_start, outer_end, outer_step = swept[outer_name]
    inner_start, inner_end, inner_step = swept[inner_name]

    outer_range = np.arange(outer_start, outer_end + outer_step, outer_step)
    inner_range = np.arange(inner_start, inner_end + inner_step, inner_step)

    current_pos = start_pos.copy()
    n = 0

    for outer_val in outer_range:
        # set outer parameter
        if outer_name == "v_stage": v_stage = outer_val
        elif outer_name == "Q":     Q = outer_val
        elif outer_name == "h0":    h0 = outer_val

        for inner_val in inner_range:
            # set inner parameter
            if inner_name == "v_stage": v_stage = inner_val
            elif inner_name == "Q":     Q = inner_val
            elif inner_name == "h0":    h0 = inner_val

            # alternate direction for serpentine
            actual_length = line_length if n % 2 == 0 else -line_length

            make_line(stage_x, stage_y, stage_z, syringe,
                      current_pos, actual_length, direction,
                      v_stage, Q, h0)

            # reposition by gap_width perpendicular to direction
            if direction in ["x", "X"]:
                current_pos[1] += gap_width
            elif direction in ["y", "Y"]:
                current_pos[0] += gap_width

            n += 1

        # split between outer groups
        if direction in ["x", "X"]:
            current_pos[1] += split
        elif direction in ["y", "Y"]:
            current_pos[0] += split
        