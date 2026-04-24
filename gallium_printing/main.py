import sys
import keyboard
import serial
import serial.tools.list_ports
import threading

from typing import Dict

from zaber_motion.ascii import Connection
from zaber_motion import Tools

from gallium_printing.config.constants import DEVICES, ARDUINO, STARTUP_POS
from gallium_printing.core.zaber_wrapper import ZaberDevice
from gallium_printing.core.deposition import make_dots, make_line, sweep
from gallium_printing.core.logging import log_move, setup_logging
from gallium_printing.core.contact import _contact_event, _listen_arduino, run_approach, approach
from gallium_printing.core.substrate_mapping import SubstrateMap

# ----------------------------------------------------------------------------------
# EMERGENCY STOP
# ----------------------------------------------------------------------------------
def emergency_stop(connection: Connection) -> None:
    '''Stops all axes immediately.'''
    print("\n EMERGENCY STOP triggered! Stopping all motion...")
    connection.stop_all()

def setup_escape_listener(connection: Connection) -> None:
    '''Bind ESC to immediate stop. Runs in-process''' 
    def on_escape():
        emergency_stop(connection)

    keyboard.add_hotkey("esc", on_escape)
    print("Emergency stop enabled - press ESC anytime.")

# ----------------------------------------------------------------------------------
#  CONNECTION
# ----------------------------------------------------------------------------------
def connect_auto() -> Connection:
    '''Scans available serial ports for Zaber devices, skipping any
    ports occupied by Arduino to avoid locking them.'''
    ports = Tools.list_serial_ports()
    arduino_ports = [p.device for p in serial.tools.list_ports.comports() if p.vid == 0x2341]
    for port in ports:
        if port in arduino_ports:
            continue
        try:
            conn = Connection.open_serial_port(port)
            devices = conn.detect_devices()
            if devices:
                print(f"Zaber device found on {port}")
                return conn
            conn.close()
        except Exception:
            pass
    raise RuntimeError("No Zaber devices detected on any port.")

def connect_arduino() -> serial.Serial:
    '''Scans available ports and returns the one where Arduino is connected.'''
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid == 0x2341:
            ser = serial.Serial(port.device, ARDUINO["baud"], timeout=5)
            print(f"Arduino found on {port.device}")
            return ser
    raise RuntimeError("No Arduino detected on any port.")

# -----------------------------------------------------------------------------------
#  HELP
# -----------------------------------------------------------------------------------
def print_help() -> None:
    '''Prints available commands.'''
    print("Commands:")
    print("  move x 10                      -> relative move")
    print("  move abs x 50                  -> absolute move")
    print("  home x                         -> home axis")
    print("  home all                       -> home all stages")
    print("  sethome x                      -> mark current pos as home")
    print("  speed x 2.5                    -> set speed mm/s")
    print("  getspeed x                     -> read speed")
    print("  pos                            -> print current XYZ + syringe positions")
    print("  syringe dispense 1             -> dispense syringe")
    print("  syringe retract 1              -> retract syringe")
    print("  syringe speed 2                -> set syringe speed")
    print("  syringe pressure 30            -> set syringe pressure (0-70)")
    print("  setstart                       -> saves the current position for x y and z axis for later deposition")
    print("  makeline 10 x 2 0.001 0.01     -> line 10mm in x, v_stage=2mm/s, Q=0.001mm³/s, h0=0.01mm")
    print("  approach x 0.05                -> approach stage x in increment 0.05")
    print("  touchdown                      -> measure substrate contact height (3x average)")
    print("  mappoint                       -> store current XYZ as a substrate corner")
    print("  mapshow                        -> show current substrate map")
    print("  mapclear                       -> reset substrate map")
    print("  mapundo                        -> remove last substrate corner")
    print("  mapredo                        -> re-measure last corner at current XY")
    print("  stick                          -> lock XY movement within mapped safe area")
    print("  unstick                        -> release stick mode")
    print("  exit                           -> quit")

# -----------------------------------------------------------------------------------
# COMMAND HANDLING
# -----------------------------------------------------------------------------------
def handle_command(line: str, stages: Dict[str, ZaberDevice], log_path: str, arduino: serial.Serial, substrate_map: SubstrateMap) -> bool:
    '''Parse and execute a single-line command. Returns False to exit loop.'''

    # Clean input
    partcmd = line.strip().split()
    if not partcmd:
        return True

    # Look at first part of input
    cmd = partcmd[0].lower()

    match cmd:

        # Exit
        case "exit":
            print("Exiting program...")
            return False
        
        # Help
        case "help":
            print_help()
            return True
        
        # Move
        case "move":
            if len(partcmd) < 3:  # Wrong usage
                print("Usage: move <axis label> <units> OR move abs <axis> <mm>")
                return True
            
            if partcmd[1] == "abs":  # Absolute movement
                axis = str(partcmd[2])
                mm = float(partcmd[3])
                dev = stages[f"stage_{axis}"]
                log_move(log_path, f"stage_{axis}", "absolute", mm)
                dev.move_abs(mm)
                print(f"Moved {axis} to abs {mm} mm")
                return True

            else:  # Relative movement
                axis = partcmd[1]
                mm = float(partcmd[2])
                dev = stages[f"stage_{axis}"]
                log_move(log_path, f"stage_{axis}", "relative", mm)
                dev.move_rel(mm)
                print(f"Moved {axis} relative {mm} mm")
                return True

        # Home
        case "home":
            if len(partcmd) == 2 and partcmd[1] == "all": # All devices
                log_move(log_path, "all", "home")
                for dev in stages.values():
                    dev.home()
                print("All devices homed.")
                return True
            
            axis = partcmd[1] # One device
            log_move(log_path, f"stage_{axis}", "home")
            dev = stages[f"stage_{axis}"]
            dev.home()
            return True
        
        # Set Home Position
        case "sethome":
            axis = partcmd[1]
            dev = stages[f"stage_{axis}"]
            dev.set_home_here()
            print(f"Set home for {axis}")
            return True
        
        # Set Start
        case "setstart":
            if len(substrate_map.corners) != 4:
                print(f"[setstart] rejected: need 4 mapped corners, have {len(substrate_map.corners)}")
                return True
            x_now = stages["stage_x"].position()
            y_now = stages["stage_y"].position()
            x_min, y_min, x_max, y_max = substrate_map.safe_area
            if not (x_min <= x_now <= x_max and y_min <= y_now <= y_max):
                print(f"[setstart] rejected: position ({x_now:.3f}, {y_now:.3f}) outside "
                    f"safe area x=[{x_min}, {x_max}] y=[{y_min}, {y_max}]")
                return True
            for stage in stages.values():
                stage.set_start()
            print("Start position set for all stages.")
            return True

        # Speed set in mm/s
        case "speed":
            axis = partcmd[1]
            speed = float(partcmd[2])
            dev = stages[f"stage_{axis}"]
            dev.set_speed(speed)
            print(f"Set speed of {axis} to {speed} mm/s")
            return True

        # Speed get
        case "getspeed":
            axis = partcmd[1]
            dev = stages[f"stage_{axis}"]
            print(dev.get_speed())
            return True
        
        # Get position
        case "pos":
            for label, dev in stages.items():
                print(f"  {label}: {dev.position():.4f} mm")
            return True
        # Syringe
        case "syringe":
            if len(partcmd) < 3:
                print("Usage: syringe <dispense/retract/speed> <value>")
                return True

            action = partcmd[1].lower()
            dev = stages["stage_s"]  # always target syringe

            match action:
                # Dispense (positive)
                case "dispense":
                    mm = float(partcmd[2])
                    log_move(log_path, "stage_s", "dispense", mm)
                    dev.syringe_dispense(mm)
                    print(f"Syringe dispensed {mm} units.")
                    return True

                # Retract (negative)
                case "retract":
                    mm = float(partcmd[2])
                    log_move(log_path, "stage_s", "retract", mm)
                    dev.syringe_retract(mm)
                    print(f"Syringe retracted {mm} units.")
                    return True

                # Set syringe speed (update active profile velocity)
                case "speed":
                    speed = float(partcmd[2])
                    dev.set_speed(speed)
                    print(f"Syringe speed set to {speed} mm/s.")
                    return True
                
                # Syring e presure
                case "pressure":
                    run = float(partcmd[2])
                    dev.set_pressure(run)
                    print(f"Syringe pressure set to {run}")
                    return True

                # Unknown syringe action
                case _:
                    print(f"Unknown syringe command: {action}")
                    return True

        # Approach
        case "approach":
            dev = stages[f"stage_{partcmd[1]}"]
            step_mm = float(partcmd[2])
            approach(dev, step_mm)
            return True
        
        # Touchdown
        case "touchdown":
            z_contact = run_approach(stages["stage_z"], arduino, log_path)
            stages["stage_z"].set_current(30)
            stages["stage_z"].default_profile()
            stages["stage_z"].move_rel(-5, wait=True)
            print(f"Substrate contact reference: {z_contact:.4f} mm")
            return True
        
        # Make dots -> makedots 1 2 3
        case "makedots":
            number_of_dots = int(partcmd[1])
            dots_spacing = float(partcmd[2])
            dot_amount = float(partcmd[3])
            make_dots(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"], int(number_of_dots), float(dots_spacing), float(dot_amount))
            # TODO: add sethome connection to determine the starting position for the device
            # TODO: add error handling for list index out of range
            return True
        
        # Make line -> makeline 
        case "makeline":
            n_corners = len(substrate_map.corners)

            if n_corners == 2:
                # Line mode — v_stage, Q, h0 from user; start_pos/direction/length from map.
                if len(partcmd) != 4:
                    print("Usage (2-corner line mode): makeline <v_stage> <Q> <h0>")
                    return True
                v_stage = float(partcmd[1])
                Q       = float(partcmd[2])
                h0      = float(partcmd[3])
                start_pos, direction, line_length = substrate_map.get_line_params()

            elif n_corners == 4:
                if len(partcmd) != 8:
                    print("Usage (4-corner mode): makeline <x_start> <y_start> <length> <direction> <v_stage> <Q> <h0>")
                    return True
                x_start     = float(partcmd[1])
                y_start     = float(partcmd[2])
                line_length = float(partcmd[3])
                direction   = str(partcmd[4])
                v_stage     = float(partcmd[5])
                Q           = float(partcmd[6])
                h0          = float(partcmd[7])

                # Validate start and endpoint against safe area
                x_min, y_min, x_max, y_max = substrate_map.safe_area
                if not (x_min <= x_start <= x_max and y_min <= y_start <= y_max):
                    print(f"[makeline] start ({x_start}, {y_start}) outside safe area "
                        f"x=[{x_min}, {x_max}] y=[{y_min}, {y_max}]")
                    return True
                x_end = x_start + line_length if direction == "x" else x_start
                y_end = y_start + line_length if direction == "y" else y_start
                if not (x_min <= x_end <= x_max and y_min <= y_end <= y_max):
                    print(f"[makeline] endpoint ({x_end}, {y_end}) outside safe area")
                    return True

                start_pos = [x_start, y_start, 0.0]  # z is recomputed from plane inside make_line

            else:
                print(f"[makeline] rejected: need 2 or 4 mapped corners, have {n_corners}")
                return True

            make_line(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"],
                    start_pos, line_length, direction, v_stage, Q, h0, substrate_map)
            return True

        # Sweep
        case "sweep":
            if len(substrate_map.corners) != 4:
                print(f"[sweep] rejected: need 4 mapped corners, have {len(substrate_map.corners)}")
                return True
            try:
                line_length = float(input("  Line length (mm): "))
                direction = input("  Direction (x/y): ").strip().lower()
                if direction not in ["x", "y"]:
                    print("Invalid direction. Use x or y.")
                    return True

                fixed = {}
                swept = {}
                for param in ["v_stage", "Q", "h0"]:
                    raw = input(f"  {param} — fixed <value> or sweep <start> <end> <step>: ").strip().split()
                    if raw[0] == "fixed":
                        fixed[param] = float(raw[1])
                    elif raw[0] == "sweep":
                        swept[param] = (float(raw[1]), float(raw[2]), float(raw[3]))
                    else:
                        print(f"Invalid input for {param}. Use 'fixed <value>' or 'sweep <start> <end> <step>'.")
                        return True

                if len(swept) != 2:
                    print(f"Need exactly 2 swept parameters, got {len(swept)}.")
                    return True

                split = float(input("  Gap between groups (mm): "))

                x_min, y_min, _, _ = substrate_map.safe_area
                start_pos = [x_min, y_min, 0.0]

                sweep(stages["stage_x"], stages["stage_y"], stages["stage_z"], stages["stage_s"],
                    start_pos, line_length, direction, split, fixed, swept, substrate_map)

            except (ValueError, IndexError) as e:
                print(f"Invalid input: {e}")

            return True
        
        # Map point
        case "mappoint":
            x = stages["stage_x"].position()
            y = stages["stage_y"].position()
            z_contact = run_approach(stages["stage_z"], arduino, log_path)
            stages["stage_z"].set_current(30)
            stages["stage_z"].default_profile()
            stages["stage_z"].move_rel(-5, wait=True)
            count = substrate_map.add_corner(x, y, z_contact)
            print(f"Corner {count}/4 stored: x={x:.4f}  y={y:.4f}  z={z_contact:.4f}")
            if substrate_map.is_complete():
                print(substrate_map)
            return True

        # Map show
        case "mapshow":
            print(substrate_map)
            return True

        # Map clear
        case "mapclear":
            substrate_map.clear()
            print("Substrate map cleared.")
            return True
        
        # Undo last map point
        case "mapundo":
            try:
                remaining = substrate_map.pop_corner()
                print(f"Last corner removed. {remaining}/4 corners remaining.")
            except ValueError as e:
                print(e)
            return True

        # Redo last map point (remove + re-measure at same XY)
        case "mapredo":
            try:
                substrate_map.pop_corner()
            except ValueError as e:
                print(e)
                return True
            x = stages["stage_x"].position()
            y = stages["stage_y"].position()
            z_contact = run_approach(stages["stage_z"], arduino, log_path)
            count = substrate_map.add_corner(x, y, z_contact)
            stages["stage_z"].set_speed(2.0)
            stages["stage_z"].move_rel(-5, wait=True)
            print(f"Corner {count}/4 re-measured: x={x:.4f}  y={y:.4f}  z={z_contact:.4f}")
            stages["stage_z"].set_speed(2.0)
            stages["stage_z"].move_rel(-5, wait=True)
            if substrate_map.is_complete():
                print(substrate_map)
            return True
        
        # Sticks the nozzle movement only to substrate map
        case "stick":
            if len(substrate_map.corners) != 4:
                print(f"[stick] map not complete (need 4 corners, have {len(substrate_map.corners)})")
                return True
            for stage in stages.values():
                stage.stickied(substrate_map)
            print("[stick] on")
            return True

        # Unsticks the nozzle movement from the substrate map
        case "unstick":
            for stage in stages.values():
                stage.unstickied()
            print("[stick] off")
            return True

        # Unknown
        case _:
            print(f"Unknown command: {line}")
            return True 

# -----------------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------------
def main() -> None:
    
    # starts logging session
    log_path = setup_logging()
    print(f"Logging to {log_path}")

    # Creates empty substrate map for deposition
    substrate_map = SubstrateMap()

    try:
        conn = connect_auto()  # Find connection
        # keep the connection open for the session
        with conn:
            devices = conn.detect_devices()
            stages: Dict[str, ZaberDevice] = {}

    #  Label devices according to their serial numbers
            for device in devices:
                serial = device.serial_number
                if serial in DEVICES["serial_to_label"]:
                    label = DEVICES["serial_to_label"][serial]
                    DEVICES["label_to_address"][label] = device.device_address
                    stages[label] = ZaberDevice(label, device.get_axis(1), conn, device)

            # Check for any missing devices
            missing = [label for label in DEVICES["serial_to_label"].values() if label not in stages]
            if missing:
                raise RuntimeError(f"Missing devices: {missing}")

            # EMERGENCY STOP & HELP
            setup_escape_listener(conn)
            print_help()

            # Home at start
            conn.home_all(wait_until_idle=True)

            # # Home at start
            conn.home_all(wait_until_idle=True)

            # Move to startup position
            for label, target in STARTUP_POS.items():
                stages[label].move_abs(target, wait=False)
            # Wait for all to arrive
            for label in STARTUP_POS:
                stages[label].axis.wait_until_idle()
            print(f"Startup position reached: X={STARTUP_POS['stage_x']}  Y={STARTUP_POS['stage_y']}  Z={STARTUP_POS['stage_z']}")
    
            # Arduino connection
            arduino = connect_arduino()
            listener = threading.Thread(target=_listen_arduino, args=(arduino, stages["stage_z"]), daemon=True)
            listener.start()

        # Command loop
            while True:
                user_input = input("Command > ")
                if not handle_command(user_input, stages, log_path, arduino, substrate_map):
                    break

    # Escape pressed
    except KeyboardInterrupt:
        print("\nInterrupted. Stopping all devices...")
        emergency_stop(conn)
        sys.exit(0)

    # Error handling
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)

# ----------------------------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------------------------
if __name__ == "__main__":
    main()
