#!/usr/bin/env python3
"""Finish the two sensor-area connections left by Freerouting 2.1.

Uses a conservative 0.1 mm grid on B.Cu, keeping 0.2 mm electrical clearance
plus rasterization margin. KiCad DRC remains authoritative after zone refill.
Run with KiCad's pcbnew Python; imported by gen_pcb.py after SES import.
"""
import heapq
import math

import pcbnew as p

STEP = 0.1
NX, NY = 501, 551


def route(board, net, start, end):
    blocked = bytearray(NX * NY)

    def raster(x1, y1, x2, y2, hit):
        for iy in range(max(0, math.floor(y1 / STEP)), min(NY, math.ceil(y2 / STEP) + 1)):
            for ix in range(max(0, math.floor(x1 / STEP)), min(NX, math.ceil(x2 / STEP) + 1)):
                if hit(ix * STEP, iy * STEP):
                    blocked[iy * NX + ix] = 1

    def rect(x1, y1, x2, y2, margin):
        a, b, c, d = x1 - margin, y1 - margin, x2 + margin, y2 + margin
        raster(a, b, c, d, lambda x, y: a <= x <= c and b <= y <= d)

    # Board edge/slot constraints; thermal pour exclusion allows signal traces.
    for box in [(0, 0, 50, 0), (0, 55, 50, 55), (0, 0, 0, 55), (50, 0, 50, 55),
                (37, 42, 38, 51.5), (37, 42, 48.5, 43)]:
        rect(*box, 0.46)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if not pad.IsOnLayer(p.B_Cu) or pad.GetNetname() == net:
                continue
            bb = pad.GetBoundingBox()
            rect(p.ToMM(bb.GetLeft()) - 100, p.ToMM(bb.GetTop()) - 100,
                 p.ToMM(bb.GetRight()) - 100, p.ToMM(bb.GetBottom()) - 100, 0.35)
    for track in board.GetTracks():
        if track.GetNetname() == net:
            continue
        if not isinstance(track, p.PCB_VIA) and track.GetLayer() != p.B_Cu:
            continue
        a, b = track.GetStart(), track.GetEnd()
        ax, ay, bx, by = [p.ToMM(v) - 100 for v in (a.x, a.y, b.x, b.y)]
        radius = p.ToMM(track.GetWidth()) / 2 + 0.35

        def hit(x, y):
            dx, dy = bx - ax, by - ay
            t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0
            return (x - ax - t * dx) ** 2 + (y - ay - t * dy) ** 2 <= radius ** 2

        raster(min(ax, bx) - radius, min(ay, by) - radius,
               max(ax, bx) + radius, max(ay, by) + radius, hit)
    sx, sy = [round(v / STEP) for v in start]
    ex, ey = [round(v / STEP) for v in end]
    source, goal = sy * NX + sx, ey * NX + ex
    if blocked[source] or blocked[goal]:
        raise RuntimeError(f"{net}: route endpoint obstructed")
    queue, costs, parents = [(0, source)], {source: 0}, {}
    while queue:
        _, node = heapq.heappop(queue)
        if node == goal:
            break
        x, y = node % NX, node // NX
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            xx, yy = x + dx, y + dy
            if not (0 <= xx < NX and 0 <= yy < NY):
                continue
            nxt = yy * NX + xx
            if blocked[nxt] or (dx and dy and (blocked[y * NX + xx] or blocked[yy * NX + x])):
                continue
            cost = costs[node] + (math.sqrt(2) if dx and dy else 1)
            if cost < costs.get(nxt, float("inf")):
                costs[nxt], parents[nxt] = cost, node
                heapq.heappush(queue, (cost + math.hypot(ex - xx, ey - yy), nxt))
    else:
        raise RuntimeError(f"{net}: no clearance-safe B.Cu path")
    nodes = [goal]
    while nodes[-1] != source:
        nodes.append(parents[nodes[-1]])
    points = [(n % NX * STEP, n // NX * STEP) for n in reversed(nodes)]
    corners = [points[0]]
    for a, b, c in zip(points, points[1:], points[2:]):
        if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) > 1e-8:
            corners.append(b)
    corners.append(points[-1])
    ni = board.FindNet(net)
    for a, b in zip(corners, corners[1:]):
        segment(board, ni, a, b, p.B_Cu)
    print(f"finished {net}: {len(corners) - 1} segments, {costs[goal] * STEP:.1f} mm")


def segment(board, net, a, b, layer):
    track = p.PCB_TRACK(board)
    track.SetStart(p.VECTOR2I_MM(100 + a[0], 100 + a[1]))
    track.SetEnd(p.VECTOR2I_MM(100 + b[0], 100 + b[1]))
    track.SetWidth(p.FromMM(0.25))
    track.SetLayer(layer)
    track.SetNet(net)
    board.Add(track)


def finish(board):
    for name, pad, via, destination in [
        ("/I2C_SCL", (40.2, 15.175), (39.6, 15.2), (21.5, 45.9)),
        ("GND", (45.275, 46.2), (45.8, 46.8), (21.5, 51.0)),
    ]:
        ni = board.FindNet(name)
        v = p.PCB_VIA(board)
        v.SetPosition(p.VECTOR2I_MM(100 + via[0], 100 + via[1]))
        v.SetDrill(p.FromMM(0.3))
        v.SetWidth(p.FromMM(0.6))
        v.SetNet(ni)
        board.Add(v)
        segment(board, ni, pad, via, p.F_Cu)
        route(board, name, via, destination)


if __name__ == "__main__":
    from gen_pcb import PCB
    board = p.LoadBoard(PCB)
    finish(board)
    for text in board.GetDrawings():
        if isinstance(text, p.PCB_TEXT) and text.GetText() == "SPI OLED":
            text.SetPosition(p.VECTOR2I_MM(123, 121.4))
    p.ZONE_FILLER(board).Fill(board.Zones())
    p.SaveBoard(PCB, board)
