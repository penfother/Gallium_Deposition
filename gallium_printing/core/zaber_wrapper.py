from zaber_motion import Units

class ZaberDevice:
    ''' Wrapper for the Zaber device'''
    def __init__(self, label: str, axis, connection, device):
        # General information
        self.label = label
        self.axis = axis
        self.connection = connection
        self.device = device
        self.stuck = False
        self.substrate_map = False

        # Start position for deposition
        self.start_position = 0.0

        # Movement limits
        self.min_pos = device.settings.get("limit.min", unit=Units.LENGTH_MILLIMETRES)
        self.max_pos = device.settings.get("limit.max", unit=Units.LENGTH_MILLIMETRES)

        # Speed profiles
        self.speed_profiles = {}
        self.active_profile = None
        self.default_profile()

    # -------------------- SPEED PROFILES -----------------------------
    def default_profile(self):
        '''Create a default speed profile if none exists and activate it.'''
        self.speed_profiles["default"] = {"vel": 10.0, "acc": 0.0, "unit": Units.VELOCITY_MILLIMETRES_PER_SECOND}
        self.active_profile = self.speed_profiles["default"]
        self._push_profile()

    # Create profile
    def set_profile(self, name: str, velocity: float, acceleration: float = 0.0):
        '''Creates a named speed profile.'''
        self.speed_profiles[name] = {"vel": velocity, "acc": acceleration}
    
    # Set profile to use
    def use_profile(self, name: str):
        '''Sets the speed profile to be used.'''
        if name not in self.speed_profiles:
            raise ValueError(f"Speed profile '{name}' not found for {self.label}")
        self.active_profile = self.speed_profiles[name]
        self._push_profile()

    def _push_profile(self):
        '''Pushes active profile to hardware.'''
        self.axis.settings.set(
            "maxspeed",
            self.active_profile["vel"],
            unit = Units.VELOCITY_MILLIMETRES_PER_SECOND
        )
        self.axis.settings.set(
            "accel",
            self.active_profile["acc"],
            unit=Units.ACCELERATION_MILLIMETRES_PER_SECOND_SQUARED
        )

    # Define speed
    def set_speed(self, mm_per_s: float):
        '''Updates active profile speed and pushes to hardware.'''
        self.active_profile["vel"] = mm_per_s
        self._push_profile()

    # Fetch in use speed profile
    def get_speed(self) -> float:
        '''Fetches the in use device speed profile.'''
        if not self.active_profile:
            return 0
        return self.active_profile["vel"]

    # -------------------- MOTION -----------------------------
    def check_limit(self, move: float, relative=True) -> bool:
        '''Verifies if the movement is within possible axis movement.'''
        pos = self.position()
        target = pos + move if relative else move
        if target < self.min_pos or target > self.max_pos:
            print(f"Movement out of bounds: {target} mm")
            return False
        return True

    def move_to(self, position_native: int, wait: bool = True) -> None:
        '''Moves device to defined position in mm away from home.'''
        self.axis.move_absolute(
            position_native,
            unit=Units.LENGTH_MILLIMETRES,
            wait_until_idle =wait,
        )
    
    def move_abs(self, mm: float, wait=False) -> bool:
        if self.stuck and self.label in ("stage_x", "stage_y"):
            x_min, y_min, x_max, y_max = self.substrate_map.safe_area
            original = mm
            if self.label == "stage_x":
                mm = max(x_min, min(x_max, mm))
            else:
                mm = max(y_min, min(y_max, mm))
            if mm != original:
                print(f"[{self.label}] clamped to {mm:.4f} (map)")
        if not self.check_limit(mm, relative=False):
            return False
        self.move_to(mm, wait)
        return True

    def move_rel(self, mm: float, wait=False) -> bool:
        if self.stuck and self.label in ("stage_x", "stage_y"):
            x_min, y_min, x_max, y_max = self.substrate_map.safe_area
            target = self.position() + mm
            if self.label == "stage_x":
                clamped = max(x_min, min(x_max, target))
            else:
                clamped = max(y_min, min(y_max, target))
            if clamped != target:
                print(f"[{self.label}] clamped to {clamped:.4f} (map)")
            mm = clamped - self.position()
        if not self.check_limit(mm, relative=True):
            return False
        self.axis.move_relative(mm, unit=Units.LENGTH_MILLIMETRES, wait_until_idle=wait)
        return True

    def set_current(self, run: float, hold: float = 15) -> None:
        '''Sets motor current.
        run: active current during motion (0-70)
        hold: current when stationary (0-70), default 15'''
        self.device.settings.set("driver.current.run", run)
        self.device.settings.set("driver.current.hold", hold)

    # -------------------- POSITIONING -----------------------------
    def position(self) -> float:
        '''Returns device position in mm.'''
        pos = self.axis.get_position(unit = Units.LENGTH_MILLIMETRES)
        return pos

    def home(self):
        '''Homes device.'''
        if self.stuck:
            print(f"[{self.label}] axis stickied, unstick to home")
            return
        self.axis.home()

    def stop(self):
        '''Stops device.'''
        self.axis.stop()

    def set_home_here(self):
        '''Sets home for the device. Not used currently.'''
        self.axis.set_home()

    def set_start(self):
        self.start_position = self.position()

    def stickied(self, smap):
        self.stuck = True
        self.substrate_map = smap
    
    def unstickied(self):
        self.stuck = False
        self.substrate_map = None
    
    # -------------------- SYRINGE ----------------------------- 
    def is_syringe(self) -> bool:
        '''Returns true if this device is the syringe pump.'''
        return self.label == "stage_s"
    
    def set_pressure(self, run: float, hold: float = 15) -> None:
        '''Sets syringe motor current as pressure proxy.
        run: active current during motion (0-70)
        hold: current when stationary (0-70), default 15'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        self.device.settings.set("driver.current.run", run)
        self.device.settings.set("driver.current.hold", hold)
        print(f"Pressure set -> run: {run}, hold: {hold}")

    def syringe_dispense(self, mm: float, wait: bool = False):
        '''Pump (positive direction). Uses syringe profile.'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        if not self.check_limit(mm, relative=False):
            return False
        self.axis.move_relative(
            mm,
            unit=Units.LENGTH_MILLIMETRES,
        )

    def syringe_retract(self, mm: float, wait: bool = False):
        '''Retract (negative direction). Uses syringe profile.'''
        if not self.is_syringe():
            raise RuntimeError(f"{self.label} is not a syringe device.")
        if not self.check_limit(-abs(mm), relative=True):
            return False
        self.axis.move_relative(
                -abs(mm),
                unit=Units.LENGTH_MILLIMETRES,
                wait_until_idle=wait
        )