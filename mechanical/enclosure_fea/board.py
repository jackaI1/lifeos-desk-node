"""Desk-node board data and the parametric case dimensions built from it.

Board coordinates are millimetres from the board's top-left corner, with x to the
right and y toward the bottom edge. The values come from hardware/desk-node.kicad_pcb:
the Edge.Cuts outline spans x 100-150 and y 100-155 in KiCad coordinates, and the
four M3 holes and the connectors are read from their footprints.
"""
from dataclasses import dataclass
import math

BOARD_W = 50.0
BOARD_D = 55.0
BOARD_THICKNESS = 1.6
# M3 mounting holes (MountingHole_3.2mm_M3 footprints H1-H4).
MOUNT_HOLES = ((4.0, 11.0), (4.0, 51.0), (34.3, 51.0), (46.5, 31.0))
MOUNT_HOLE_DIAMETER = 3.2
# Connector positions on the bottom edge (+y side): USB-C J1 and the 1x04 header J2.
USB_CENTRE_X = 14.0
USB_OPENING = (9.0, 3.2)          # width along x, height above the board
HEADER_CENTRE_X = 21.5
HEADER_SLOT_WIDTH = 13.0


@dataclass(frozen=True)
class CaseParams:
    """Every dimension of the case, in millimetres. Change a value and rebuild."""
    wall: float = 2.0             # side walls and floor
    cavity_height: float = 12.0   # floor top to rim top
    standoff_height: float = 5.0  # floor top to underside of the board
    side_clearance: float = 5.0   # board edge to cavity wall on the -x, +x and -y sides
    usb_clearance: float = 1.0   # board edge to cavity wall on the +y side (connector side)
    standoff_radius: float = 3.0  # 6 mm bosses under the four mounting holes
    post_radius: float = 2.5      # 5 mm corner posts for the lid screws
    screw_hole_radius: float = 1.25  # M3 tapping pilot
    post_inset: float = 3.0       # post centre to the inside of the two walls it sits between

    @property
    def cavity_width(self):
        return BOARD_W + 2 * self.side_clearance

    @property
    def cavity_depth(self):
        return BOARD_D + self.side_clearance + self.usb_clearance

    @property
    def outer_width(self):
        return self.cavity_width + 2 * self.wall

    @property
    def outer_depth(self):
        return self.cavity_depth + 2 * self.wall

    @property
    def outer_height(self):
        return self.wall + self.cavity_height

    def board_origin(self):
        """Case coordinates of the board's top-left corner."""
        return (self.wall + self.side_clearance, self.wall + self.side_clearance)

    def board_to_case(self, x, y):
        ox, oy = self.board_origin()
        return (ox + x, oy + y)

    def standoff_centres(self):
        return [self.board_to_case(x, y) for x, y in MOUNT_HOLES]

    def post_centres(self):
        t, w, d, r = self.wall, self.cavity_width, self.cavity_depth, self.post_inset
        return [(t + r, t + r), (t + w - r, t + r), (t + r, t + d - r), (t + w - r, t + d - r)]

    def validate(self):
        values = [self.wall, self.cavity_height, self.standoff_height, self.side_clearance,
                  self.usb_clearance, self.standoff_radius, self.post_radius, self.screw_hole_radius,
                  self.post_inset]
        if not all(math.isfinite(v) and v > 0 for v in values):
            raise ValueError('all case dimensions must be positive and finite')
        if self.standoff_height >= self.cavity_height:
            raise ValueError('standoffs must be shorter than the cavity')
        if self.screw_hole_radius >= self.post_radius or self.standoff_radius <= self.screw_hole_radius:
            raise ValueError('screw holes must fit inside posts and standoffs')
        # Posts and bosses must not touch the board outline, and the board must not touch a wall.
        if self.side_clearance < 0.5 or self.usb_clearance < 0.5:
            raise ValueError('board needs at least 0.5 mm clearance to the walls')
        corners = [(0, 0), (BOARD_W, 0), (0, BOARD_D), (BOARD_W, BOARD_D)]
        for cx, cy in self.post_centres():
            for bx, by in corners:
                kx, ky = self.board_to_case(bx, by)
                if math.hypot(kx - cx, ky - cy) < self.post_radius + 0.25:
                    raise ValueError('a corner post is too close to the board')
        for sx, sy in self.standoff_centres():
            if sx - self.standoff_radius < self.wall or sy - self.standoff_radius < self.wall:
                raise ValueError('a standoff reaches the wall')
            if (sx + self.standoff_radius > self.wall + self.cavity_width
                    or sy + self.standoff_radius > self.wall + self.cavity_depth):
                raise ValueError('a standoff reaches the wall')
        return self
