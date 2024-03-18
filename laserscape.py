"""laserscape.

Usage:
  laserscape split [--overwrite] <inkscape-file>
  laserscape to-gcode <inkscape-file>
  laserscape -h | --help
  laserscape --version

Options:
  -h --help     Show this screen.
  --version     Show version.
"""

__version__ = "1.0.0"

from docopt import docopt
from pathlib import PurePath
import sys
import functools
import copy
import re

from svg_to_gcode.svg_parser import parse_file
from svg_to_gcode.compiler import Compiler, interfaces

# Patch Compiler to allow changing laser power
# TODO: propose this change to library maintainers
from svg_to_gcode.compiler.interfaces import Interface
from svg_to_gcode.geometry import Curve, Line
from svg_to_gcode.geometry import LineSegmentChain
from svg_to_gcode import UNITS, TOLERANCES

def patched_append_line_chain(self, line_chain, laser_power=1):
    if line_chain.chain_size() == 0:
        warnings.warn("Attempted to parse empty LineChain")
        return []

    code = []

    start = line_chain.get(0).start

    # Don't dwell and turn off laser if the new start is at the current position
    if self.interface.position is None or abs(self.interface.position - start) > TOLERANCES["operation"]:

        code = [self.interface.laser_off(), self.interface.set_movement_speed(self.movement_speed),
                self.interface.linear_move(start.x, start.y), self.interface.set_movement_speed(self.cutting_speed),
                self.interface.set_laser_power(laser_power)]

        if self.dwell_time > 0:
            code = [self.interface.dwell(self.dwell_time)] + code

    for line in line_chain:
        code.append(self.interface.linear_move(line.end.x, line.end.y))

    self.body.extend(code)

Compiler.append_line_chain = patched_append_line_chain

def patched_append_curves(self, curves, laser_power=1):
    for curve in curves:
        line_chain = LineSegmentChain()

        approximation = LineSegmentChain.line_segment_approximation(curve)

        line_chain.extend(approximation)

        self.append_line_chain(line_chain, laser_power)

Compiler.append_curves = patched_append_curves


# Looks like there is a bug in the library allowing one to generate M3 code
# with float S value (which is not possible? to confirm).
# TODO: report this bug to maintainers.
from svg_to_gcode import formulas
import math

def patched_set_laser_power(self, power):
    if power < 0 or power > 1:
        raise ValueError(f"{power} is out of bounds. Laser power must be given between 0 and 1. "
                            f"The interface will scale it correctly.")

    return f"M3 S{math.floor(formulas.linear_map(0, 255, power))};"

interfaces.Gcode.set_laser_power = patched_set_laser_power

## End of svg_to_gcode patching

from pyinkscape import Canvas


class NoPriorityDefined(Exception):
    pass


@functools.total_ordering
class Layer(object):
    label_regex = re.compile(
        r"(engrave|cut)(?P<priority>-\d+)?(?P<passes>x\d+)?(?P<cut_speed>f\d+)?(?P<laser_power>s\d+)?"
    )
    def __init__(self, inkscape_layer):
        self._inkscape_layer = inkscape_layer

    @property
    def ID(self):
        return self._inkscape_layer.ID

    @property
    def label(self):
        return self._inkscape_layer.label

    def is_engrave_layer(self):
        return self.label.lower().startswith("engrave")

    def is_cut_layer(self):
        return self.label.lower().startswith("cut")

    def _parse_priority(self):
        matches = self.label_regex.search(self.label.lower())
        m = matches.group("priority")
        if m is None:
            raise ValueError()
        return int(m[1:])

    @property
    def priority(self):
        """Returns the priority of the layer to be engraved/cut by the laser
        engraver. The lower the integer, the higher the priority.

        If not specified in the label, the layer gets the lowest priority.
        If multiple layers have not priority specified in their labels, the
        order in which those layers will be engraved/cut is not specified.
        """
        try:
            return self._parse_priority()
        except ValueError as e:
            return float("inf")

    def _parse_passes(self):
        matches = self.label_regex.search(self.label.lower())
        m = matches.group("passes")
        if m is None:
            raise ValueError()
        return int(m[1:])

    @property
    def passes(self):
        """Returns the number of path the laser do on the layer to be
        engraved/cut.

        If not specified in the label, the layer gets 1 laser pass.
        """
        try:
            return self._parse_passes()
        except ValueError as e:
            return 1

    def _parse_laser_power(self):
        matches = self.label_regex.search(self.label.lower())
        m = matches.group("laser_power")
        if m is None:
            raise ValueError()
        return int(m[1:])/1000

    def _is_valid_operand(self, other):
        return hasattr(other, "priority")

    def __lt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.priority < other.priority


def split_layers(layers):
    engrave_layers = []
    cut_layers = []
    ignored_layers = []
    for layer in map(Layer, layers):
        if layer.is_cut_layer():
            cut_layers.append(layer)
        elif layer.is_engrave_layer():
            engrave_layers.append(layer)
        else:
            ignored_layers.append(layer)
    engrave_layers.sort()
    cut_layers.sort()
    return engrave_layers, cut_layers, ignored_layers


def copy_with_only_this_layer(canvas, layer):
    new_canva = copy.deepcopy(canvas)
    for l in new_canva.layers():
        if l.ID != layer.ID:
            l.delete()
    return new_canva


def split(inkscape_file_path, overwrite=False, output_directory=None):
    if output_directory is None:
        output_directory = inkscape_file_path.parent
    base_name = inkscape_file_path.stem
    canvas = Canvas(inkscape_file_path)
    layers = canvas.layers()
    engrave, cut, ignored = split_layers(layers)
    print("engrave:")
    for i, layer in enumerate(engrave):
        print("  ", layer.label)
        c = copy_with_only_this_layer(canvas, layer)
        output_path = output_directory/(base_name+"-"+layer.label+".svg")
        print("  rendering", output_path)
        c.render(output_path, overwrite=overwrite)
    print("cut:")
    for i, layer in enumerate(cut):
        print("  ", layer.label)
        c = copy_with_only_this_layer(canvas, layer)
        output_path = output_directory/(base_name+"-"+layer.label+".svg")
        print("  rendering", output_path)
        c.render(output_path, overwrite=overwrite)
    print("ignored:")
    for l in ignored:
        print("  ", l.label)


def to_gcode(inkscape_file_path):
    print(inkscape_file_path, str())
    gcode_compiler = Compiler(interfaces.Gcode, movement_speed=1000, cutting_speed=300, pass_depth=0)
    curves = parse_file(inkscape_file_path)
    print(curves)

    gcode_compiler.append_curves(curves, 5)
    gcode_compiler.compile_to_file("drawing.gcode", passes=2)

def main(arguments):
    if arguments["split"]:
        return split(PurePath(arguments["<inkscape-file>"]),
                     arguments["--overwrite"])
    elif arguments["to-gcode"]:
        return to_gcode(PurePath(arguments["<inkscape-file>"]))

    return 0


if __name__ == "__main__":
    arguments = docopt(__doc__, version=__version__)
    sys.exit(main(arguments))
