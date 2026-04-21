import numpy as np

# -----------------------------------------------------------------------------------
# SUBSTRATE MAP STATE
# -----------------------------------------------------------------------------------
class SubstrateMap:
    '''Holds the substrate mapping state across the session.
    Corners are collected one at a time via mappoint, then
    plane + safe area are auto-computed once all 4 are in.'''
    
    def __init__(self):
        self.corners = []
        self.plane = None
        self.safe_area = None

    def is_complete(self) -> bool:
        return len(self.corners) == 4 and self.plane is not None

    def add_corner(self, x: float, y: float, z: float) -> int:
        '''Add a probed corner point. Returns the new count.
        Auto-fits plane and safe area when 4th point is added.'''
        if len(self.corners) >= 4:
            raise ValueError("Already have 4 corners. Use 'mapclear' to reset.")
        self.corners.append((round(x, 4), round(y, 4), round(z, 4)))

        if len(self.corners) == 4:
            self.plane = fit_plane(self.corners)
            self.safe_area = deposition_area(self.corners)

        return len(self.corners)

    def clear(self) -> None:
        '''Reset the map.'''
        self.corners.clear()
        self.plane = None
        self.safe_area = None

    def z_at(self, x: float, y: float) -> float:
        '''Returns the substrate surface z at an arbitrary (x, y) point.'''
        if self.plane is None:
            raise ValueError("No plane fitted yet — need 4 corners.")
        a, b, c = self.plane
        return a * x + b * y + c

    def __str__(self) -> str:
        lines = [f"Substrate Map ({len(self.corners)}/4 corners)"]
        for i, (x, y, z) in enumerate(self.corners, 1):
            lines.append(f"  Corner {i}: x={x:.4f}  y={y:.4f}  z={z:.4f}")
        if self.plane:
            a, b, c = self.plane
            lines.append(f"  Plane:  z = {a}·x + {b}·y + {c}")
        if self.safe_area:
            x0, y0, x1, y1 = self.safe_area
            lines.append(f"  Safe area: x=[{x0}, {x1}]  y=[{y0}, {y1}]")
            lines.append(f"  Safe area size: {round(x1-x0, 3)} x {round(y1-y0, 3)} mm")
        return "\n".join(lines)

    def pop_corner(self) -> int:
        '''Remove the last corner. Returns remaining count.'''
        if not self.corners:
            raise ValueError("No corners to remove.")
        self.corners.pop()
        self.plane = None
        self.safe_area = None
        return len(self.corners)
# -----------------------------------------------------------------------------------
# PLANE FIT
# -----------------------------------------------------------------------------------
def fit_plane(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    '''Fits a least squares plane z = ax + by + c through 4 points. 
    Input is a list of (x, y, z) tuples in mm, returns (a, b, c) coefficients.'''
    A = np.array([[x, y, 1] for x, y, z in points])
    z = np.array([z for x, y, z in points])

    a, b, c = np.linalg.lstsq(A, z, rcond=None)[0]

    return round(a, 3), round(b, 3), round(c, 3)

# -----------------------------------------------------------------------------------
# Z VELOCITY FOR LINE
# -----------------------------------------------------------------------------------
def z_velocity_for_line(
    a: float, b: float, c: float,
    x0: float, y0: float,
    x1: float, y1: float,
    h0: float, v_stage: float
) -> tuple[float, float, float]:
    '''Calculates Z start, end and velocity to follow 
    the substrate plane during a line move.'''
    z_start = round(a * x0 + b * y0 + c + h0, 3)
    z_end   = round(a * x1 + b * y1 + c + h0, 3)

    xy_distance = np.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    travel_time = xy_distance / v_stage
    v_z = round((z_end - z_start) / travel_time, 3)

    return z_start, z_end, v_z

# -----------------------------------------------------------------------------------
# DEPOSITION AREA
# -----------------------------------------------------------------------------------
def deposition_area(
    corners: list[tuple[float, float, float]],
    margin: float = 0.25
) -> tuple[float, float, float, float]:
    '''Returns an axis-aligned safe deposition rectangle (x_min, y_min, x_max, y_max)
    inscribed within the 4 probed substrate corners, inset by margin (mm).
    
    Takes the 4 probed (x, y, z) corner points and computes the largest
    axis-aligned box guaranteed to lie inside the substrate boundary.'''
    
    xs = sorted([x for x, y, z in corners])
    ys = sorted([y for x, y, z in corners])
    
    # Inner pair on each axis = safe bounds
    x_min = xs[1] + margin
    x_max = xs[2] - margin
    y_min = ys[1] + margin
    y_max = ys[2] - margin
    
    if x_min >= x_max or y_min >= y_max:
        raise ValueError(
            f"No safe area: margin {margin} mm too large or corners too skewed. "
            f"Available x: {round(xs[2]-xs[1], 3)} mm, y: {round(ys[2]-ys[1], 3)} mm"
        )
    
    return round(x_min, 3), round(y_min, 3), round(x_max, 3), round(y_max, 3)

