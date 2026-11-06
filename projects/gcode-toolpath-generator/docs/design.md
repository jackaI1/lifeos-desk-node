# Dimensions, paths and checking

## Coordinate convention and output

All coordinates are millimetres in the G54 work coordinate system. The lower-left
stock corner is XY zero, the original top is Z zero, and cutting Z values are
negative. Stock is a rectangular block. Before running a program, the operator
must set those work offsets and the correct tool length, and park the cutter at
`(diameter/2, diameter/2, safe_z)`. The checker uses that same explicit initial
position. It cannot discover where a real machine is parked.

The output uses `G21 G17 G90 G94 G40 G49 G80 G54`: millimetres, XY plane,
absolute coordinates, feed per minute, controller radius compensation off,
tool length compensation off, canned cycles cancelled, and G54 work coordinates.
The tool length must therefore already be included in the chosen work setup.
`G0` is rapid travel and `G1` is a straight feed move. `S` sets spindle rpm,
`M3` starts clockwise rotation, `M5` stops it and `M30` ends the program.
These meanings follow the [LinuxCNC G-code reference](https://linuxcnc.org/docs/html/gcode/g-code.html).
No arcs, automatic tool changes, controller compensation, canned drilling cycles,
relative/inch modes, probing or controller macros are emitted or accepted by the checker.
Coordinates and feeds are written to 0.001 resolution. Bounds checks allow 0.001 mm
for the rounding of compensated polygon vertices; this is software tolerance,
not a claim of achievable machining accuracy.

## Input reference

| Field | Meaning |
| --- | --- |
| `stock` | `[width, height, thickness]`, all positive |
| `outline` | Ordered vertices of a convex polygon, no self intersections or inward notches |
| `pocket` | `[xmin, ymin, xmax, ymax]` strictly inside the outline |
| `pocket_depth` | Pocket depth below Z zero |
| `profile_depth` | Outside cut depth; at least 0.2 mm stock must remain below |
| `holes`, `hole_depth` | Centres of cutter-diameter blind holes and their depth |
| `diameter`, `flutes` | One centre-cutting carbide end mill for every operation |
| `stepdown` | Maximum depth increment, limited by material and diameter |
| `stepover` | Maximum row spacing, no greater than half the diameter |
| `safe_z` | Positive rapid-travel height and checked upper height limit |
| `material` | `aluminum_6061`, `acetal` or `mild_steel` |
| `max_rpm` | Machine spindle cap |
| `lead_length` | Straight tangent entry distance for the outline |
| `peck` | Drilling depth increment, further limited by `stepdown` |

Holes must fit within the outline, be separated, and avoid the pocket. Pocket
and hole depths may not exceed profile depth. The compensated outline and its
entire cutter width must fit in the stock; the tangent lead-in must fit as well
and may not cross the finished part. Invalid input fails before generation.
A planning budget rejects estimated jobs above 100,000 moves, including every
ramp traverse, raster row, peck and profile layer. Depths, increments, clearance
and lead length must be at least 0.01 mm. The pocket must leave at least 0.01 mm
of cutter-centre travel on each axis, so the rounded output preserves the ramp.

## Material table and formulas

These are deliberately explicit, illustrative starting assumptions for a small
carbide cutter. They are not manufacturer-qualified recipes or measured results.
The operator must choose suitable cutter data, lubrication, workholding and
machine limits before hardware use. The same table drives milling and the
slower plunge feed for this single-tool example; it is not a twist-drill table.

| Material | Surface m/min | Chip mm/tooth | Plunge / milling feed | Maximum stepdown / diameter |
| --- | ---: | ---: | ---: | ---: |
| 6061 aluminum | 120 | 0.015 | 0.25 | 0.25 |
| Acetal | 150 | 0.035 | 0.30 | 0.50 |
| Mild steel | 30 | 0.008 | 0.20 | 0.15 |

`rpm = min(floor(max_rpm), round(surface_m_min * 1000 / (pi * diameter_mm)))`

`feed_mm_min = rpm * flutes * chip_mm`

`plunge_mm_min = feed_mm_min * plunge_fraction`

The feed uses the integer spindle speed actually emitted, after applying the
machine cap. Feeds are rounded to 0.001 mm/min; inputs that would produce a zero
spindle speed or feed after rounding are rejected.

For the sample, the theoretical spindle speed exceeds the 12,000 rpm limit.
The resulting feed is 360 mm/min and plunge feed is 90 mm/min. Depth increments
are 0.5 mm. The generated program has 427 parsed moves and a roughly 32.27 minute
travel estimate, excluding setup, acceleration, coolant and controller overhead.
The report calls all G1 distance `cutting_mm`; this includes feed withdrawals
and air travel as well as engaged cutting, so it is not a material-removal metric.

## Geometry choices

The pocket's centre path stays one tool radius inside its rectangular bounds.
Rows are divided evenly so their spacing never exceeds `stepover`, including
the final row. Each layer starts with alternating ramp traverses along the first
row; the planner adds traverses when needed to keep the descent below about
3 degrees. It then repeats that row at full depth, clears the remaining rows
and follows all four walls. The actual pocket is a rounded rectangle with
inside radius equal to the cutter radius. The coverage test compares the union
of swept tool disks to that rounded target, not to impossible square corners.

The outside centre path is the polygon's outward radius offset, using mitred
joins. Extra movement around convex corners avoids arc/chord approximation
gouges. Shapely's offset handles the polygon geometry; there is no external CAM
engine. I restrict outlines to convex polygons: an outward buffer can silently
close a narrow inward notch, so concave outlines are rejected before planning.
Acute shapes whose lead-in would hit the part are also rejected.
This is not a general solution for nested islands, arbitrary pocket polygons,
3D surfaces or through-cut tabs. The supplied profile floor retains the part.

The holes use explicit plunges and feed withdrawals, with no canned cycles.
Their diameters are exactly the selected end mill's diameter. They are not
helical bores and there is no independent drill tool or tool change. All three
operations use positive-depth increments capped at their exact requested final
depth. Pocketing and drilling happen before the outside cut.

## Independent simulation and output files

The simulator tokenizes actual output text, checks modes, spindle/feed state,
program termination and linear segment endpoints, and returns line-numbered
errors. In a rectangular stock, a straight segment with both cutter-centre
endpoints in the radius-inset XY bounds remains in those bounds throughout.
This is why endpoint tests check the whole linear sweep, rather than sampling
and potentially skipping an excursion. Z must remain between the stock bottom
and `safe_z`. Every rapid whose start or end is below Z zero is rejected.

There is no material removal model, fixture model, holder envelope or machine
kinematic model. A successful report does not certify a program safe for a mill.
Unknown codes fail closed because an unsupported motion could invalidate the
position model. Feed retractions make the generator compatible with this
conservative rapid rule. `G80` cancels modal motion: a later axis word requires
a new `G0` or `G1`, and either move on the same line as `G80` is rejected as a
conflicting motion group.

`bracket.nc` is the emitted program. `report.json` records checks, travel bounds,
distances, illustrative cutting data and a time estimate. `moves.json` stores
each parsed segment's start/end coordinates, rapid flag, feed and source line.
Both PNGs use those parsed segments, so hand-edited code can be checked through
the same parser used for the preview. The CLI's `check` command prints a report;
it does not overwrite the original bundle or regenerate images.
