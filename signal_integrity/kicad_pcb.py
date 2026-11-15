"""Read the board's stackup, net names, tracks and vias from a KiCad .kicad_pcb file.

A .kicad_pcb file is a text tree of parenthesised records. This module parses
that tree with a small reader instead of a KiCad install, so CI and a Mac with
no KiCad can read the board. The net list is the board's own: every track and
via names its net by number, and the file maps those numbers to names.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

Node = Union[str, List["Node"]]


def parse_sexpr(text: str) -> List[Node]:
    """Parse KiCad's S-expression text into nested lists of atoms (strings)."""
    tokens: List[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append('"' + "".join(buf))  # quoted atoms keep a marker
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            tokens.append(text[i:j])
            i = j
    stack: List[List[Node]] = [[]]
    for tok in tokens:
        if tok == "(":
            stack.append([])
        elif tok == ")":
            if len(stack) == 1:
                raise ValueError("unbalanced ')' in board file")
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok)
    if len(stack) != 1:
        raise ValueError("unbalanced '(' in board file")
    return stack[0]


def _unquote(atom: Node) -> Node:
    if isinstance(atom, str) and atom.startswith('"'):
        return atom[1:]
    return atom


def _children(node: List[Node], key: str) -> List[List[Node]]:
    return [child for child in node if isinstance(child, list) and child and child[0] == key]


def _first(node: List[Node], key: str) -> Optional[List[Node]]:
    found = _children(node, key)
    return found[0] if found else None


def _number(node: Optional[List[Node]], index: int = 1) -> Optional[float]:
    if node is None:
        return None
    return float(node[index])


@dataclass(frozen=True)
class Track:
    net: str
    layer: str
    width_mm: float
    length_mm: float


@dataclass(frozen=True)
class Via:
    net: str
    pad_mm: float
    drill_mm: float


@dataclass(frozen=True)
class Board:
    thickness_mm: float
    net_names: Dict[int, str]
    tracks: Tuple[Track, ...]
    vias: Tuple[Via, ...]
    ground_clearance_mm: float   # clearance of the GND copper pour

    def net_name(self, number: int) -> str:
        return self.net_names.get(number, "")

    def track_widths(self, net: Optional[str] = None) -> Dict[float, float]:
        """Total track length in mm for each width, optionally for one net."""
        totals: Dict[float, float] = {}
        for track in self.tracks:
            if net is None or track.net == net:
                totals[round(track.width_mm, 4)] = totals.get(round(track.width_mm, 4), 0.0) + track.length_mm
        return totals

    def nets_with_tracks(self) -> List[str]:
        return sorted({t.net for t in self.tracks if t.net})


def parse_board(path: Union[str, Path]) -> Board:
    top = parse_sexpr(Path(path).read_text(encoding="utf-8"))
    if not top or not isinstance(top[0], list) or top[0][0] != "kicad_pcb":
        raise ValueError(f"{path} is not a KiCad board file")
    board = top[0]
    general = _first(board, "general")
    thickness = _number(_first(general, "thickness")) if general else None
    if thickness is None:
        raise ValueError("board file has no (general (thickness ...)) entry")

    net_names: Dict[int, str] = {}
    for net in _children(board, "net"):
        if len(net) >= 3:
            net_names[int(net[1])] = str(_unquote(net[2]))

    def name_of(node: List[Node]) -> str:
        net = _first(node, "net")
        if net is None:
            return ""
        return net_names.get(int(net[1]), "")

    tracks: List[Track] = []
    for seg in _children(board, "segment"):
        start, end = _first(seg, "start"), _first(seg, "end")
        width = _number(_first(seg, "width"))
        layer = str(_unquote(_first(seg, "layer")[1]))
        length = math.hypot(_number(end, 1) - _number(start, 1), _number(end, 2) - _number(start, 2))
        tracks.append(Track(name_of(seg), layer, width, length))

    vias: List[Via] = []
    for via in _children(board, "via"):
        vias.append(Via(name_of(via), _number(_first(via, "size")), _number(_first(via, "drill"))))

    clearance = None
    for zone in _children(board, "zone"):
        zone_net = _first(zone, "net_name")
        if zone_net is not None and _unquote(zone_net[1]) == "GND":
            pads = _first(zone, "connect_pads")
            clearance = _number(_first(pads, "clearance")) if pads else None
            break
    if clearance is None:
        raise ValueError("board file has no GND zone clearance")

    return Board(thickness_mm=thickness, net_names=net_names, tracks=tuple(tracks),
                 vias=tuple(vias), ground_clearance_mm=clearance)
