import threading
import serial
import keyboard
import time
import msvcrt

from gallium_printing.core.logging import log_move
from gallium_printing.core.zaber_wrapper import ZaberDevice

# ----------------------------------------------------------------------------------
# ARDUINO
# ----------------------------------------------------------------------------------
_contact_event = threading.Event()
_contact_enabled = False


def _listen_arduino(ser, axis):
    global _contact_enabled
    while True:
        line = ser.readline().decode("utf-8").strip()
        if line == "READY":
            continue
        if line:
            print(f"[Arduino] {line}")
        if line == "CONTACT" and _contact_enabled:
            axis.stop()
            _contact_event.set()
# -----------------------------------------------------------------------------------
# APPROACH
# -----------------------------------------------------------------------------------
def approach(stage: ZaberDevice, step_mm: float) -> None:
    '''Manual fine control for stage'''
    print("Manual approach mode activated. Use W/S to move, X to exit.")

    # Loop
    while True:
        event = keyboard.read_event()

        if event.event_type != "down":
            continue

        key = event.name

        match key:
            case "w":
                if not stage.check_limit(step_mm):
                    return
                stage.move_rel(step_mm, wait=True)
            case "s":
                if not stage.check_limit(-step_mm):
                    return
                stage.move_rel(-step_mm, wait=True)
            case "x":
                break
    
    while msvcrt.kbhit():
        msvcrt.getch()

# ----------------------------------------------------------------------------------
# SUBSTRATE CONTACT
# ----------------------------------------------------------------------------------
def run_approach(stage_z: ZaberDevice, arduino: serial.Serial, log_path: str) -> float:
    '''
    Full substrate approach sequence.
    1. Connects to Arduino.
    2. Manual approach with W/S until user is satisfied.
    3. Automatic precision contact detection, 3 measurements, returns average.

    Args:
        stage_z:  ZaberDevice for the Z axis
        log_path: path to the session log file

    Returns:
        average contact position in mm
    '''
    
    # Enables contact detection
    global _contact_enabled
    _contact_enabled = True

    # Manual approach
    print("\nManual approach — use W/S to move Z, X when done.")
    approach(stage_z, step_mm=1)

    # Precision measurement
    print("\nStarting precision contact detection...")
    measurements = []

    # Probe pass
    _contact_event.clear()
    arduino.reset_input_buffer()
    arduino.write(b'r')
    time.sleep(0.2)
    stage_z.set_current(20)
    stage_z.set_speed(0.05)
    remaining = stage_z.max_pos - stage_z.position()
    stage_z.move_rel(remaining, wait=False)
    _contact_event.wait()
    probe_pos = stage_z.position()
    print(f"Probe contact at: {probe_pos:.4f} mm")
    stage_z.set_speed(1.0)
    stage_z.move_rel(-0.5, wait=True)

    for i in range(3):
        print(f"Measurement {i + 1}/3...")
        _contact_event.clear()
        arduino.reset_input_buffer()
        arduino.write(b'r')
        time.sleep(0.2)

        stage_z.set_current(6.7)
        stage_z.set_speed(0.01)
        remaining = stage_z.max_pos - stage_z.position()
        stage_z.move_rel(remaining, wait=False)

        _contact_event.wait()

        pos = stage_z.position()
        measurements.append(pos)
        log_move(log_path, "stage_z", "contact", pos)
        print(f"  Contact at: {pos:.4f} mm")

        if i < 2:
            stage_z.set_current(30)
            stage_z.set_speed(1.0)
            stage_z.move_rel(-0.5, wait=True)
            
    _contact_enabled = False
    arduino.reset_input_buffer()
    stage_z.set_current(30)
    stage_z.default_profile()
    arduino.write(b'r')
    time.sleep(0.2)

    average = sum(measurements) / len(measurements)
    spread = max(measurements) - min(measurements)

    print(f"\n--- Results ---")
    for i, m in enumerate(measurements):
        print(f"  Measurement {i + 1}: {m:.4f} mm")
    print(f"  Average:       {average:.4f} mm")
    print(f"  Spread:        {spread:.4f} mm")
    log_move(log_path, "stage_z", "contact_avg", average)

    return average