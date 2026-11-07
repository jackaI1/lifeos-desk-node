# freecad-design-tools

I built a small toolkit for making mounting parts to learn how the underlying idea works. This is a learning project.

I use illustrative part dimensions and generated example geometry.

## What I get

- Six editable part variants from [the dimension table](examples/dimensions.csv).
- An assembly containing two plates, two brackets and four spacers.
- A bill of materials (BOM), meaning a parts list with quantities, in CSV and Excel.
- A reuse report that catches a plate only 0.1 mm longer than another, while checking hole locations as well as size and volume.
- A draft, review and released workflow that saves the exact checked-in file and rejects invalid state changes.

The CAD files use millimetres. All dimensions in the CSV are numbers, without units or formulas. Open the CSV in Excel or LibreOffice to edit it, then save it as CSV again. The hole pitch is the distance between the two hole centres. Each bracket has two holes through its foot; each spacer has one central bore.

## Set up and run

FreeCAD supplies the solid-modelling engine; installing a package named FreeCAD from pip is not a replacement. I test with FreeCAD 1.1 on macOS and the packaged FreeCAD runtime on Ubuntu 24.04.

### macOS

### Ubuntu 24.04

This uses the FreeCAD maintainers' stable package archive, because Ubuntu 24.04 does not include FreeCAD in its default package list.

```sh
sudo add-apt-repository --yes ppa:freecad-maintainers/freecad-stable
sudo apt-get update
sudo apt-get install freecad-python3 python3-pytest python3-openpyxl
export PYTHONPATH="/usr/lib/freecad-python3/lib:/usr/lib/freecad/lib:/usr/share/freecad/Mod:$PWD"
/usr/bin/python3 -m freecad_tools generate examples/dimensions.csv build/demo
```

The output folder must be empty. I use a new folder for another run so an existing design never gets overwritten. It contains `library/*.FCStd`, `assembly.FCStd`, `bom.csv`, `bom.xlsx` and `reuse.csv`. A [complete sample run](examples/sample-output) is included so I can inspect the native files and reports immediately. Downloadable outputs are also attached to each successful [CI run](https://github.com/jackaI1/freecad-design-tools/actions).

### Run as a FreeCAD macro

To open an existing assembly, execute [macros/OpenAssembly.FCMacro](macros/OpenAssembly.FCMacro) through **Macro > Macros**, then select this checkout and its `assembly.FCStd`. This restores the editable code and displays the eight occurrences, with library definitions hidden. Headless exports do not contain desktop display settings, so I use this opener to set the view.

Install `openpyxl` into `.freecad-deps` as above, then open [macros/MountingToolkit.FCMacro](macros/MountingToolkit.FCMacro) through **Macro > Macros** in FreeCAD. Execute it and select this checkout, the CSV, and an empty output folder. It opens the generated assembly for inspection.

Keep this checkout on FreeCAD's Python path when reopening files. In FreeCAD's Python console, run the following once before opening a part, replacing the example path:

```python
import sys

sys.path.insert(0, "/path/to/freecad-design-tools")
import freecad_tools.parts
```

FreeCAD 1.1 restricts which Python modules a saved file can load automatically. Importing this trusted checkout first restores the editable part code; the toolkit macro does this for me. I do not need to change FreeCAD's security settings.

Each native part includes a spreadsheet named `Dimensions_...`. Edit a number in column B and recompute the document to change the solid. The Python proxy, a small class that rebuilds the shape, restores when I reopen the file. If dimensions become impossible, it clears the old shape and records `GenerationError`. The BOM also rejects dependency errors and changes awaiting recomputation so an outdated solid cannot slip into an export.

## Keep a reviewed revision

PDM means product data management: keeping a design's saved files and revision history in order. This is a local imitation of that workflow, not a shared engineering approval system.

```sh
python -m freecad_tools check-in .pdm PL-80 build/demo/library/PL-80.FCStd --expected 0
python -m freecad_tools transition .pdm PL-80 review --expected 1
python -m freecad_tools transition .pdm PL-80 released --expected 2
python -m freecad_tools history .pdm PL-80
```

A new part starts at draft revision 1. A draft can go to review; review can return to draft for changes or become released. Check-in is blocked during review. A released revision cannot go backwards or be overwritten; checking in another file starts the next draft revision. `--expected` is the last version number I saw in the command output or history. Each check-in and state change advances this version, even within one draft revision, so stale edits and approvals are rejected. Design revision numbers only advance when I start a new draft after release.

The vault locks its index while writing, saves files by their SHA-256 content hash (a fingerprint of the bytes), and checks the saved fingerprint before transitions. I release the saved snapshot, not a live working file. If I change my working file after check-in, I must check it in again before asking someone to review it. The vault cannot authenticate reviewers or prevent someone who can edit the vault from rewriting its index; it is intended for one machine on a local filesystem.

## Inside the project

The [design notes](docs/design.md) cover the geometry, assembly layout and workflow limits. [freecad_tools/parts.py](freecad_tools/parts.py) builds solids using FreeCAD's [Part scripting API](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Part_scripting.md) and native [spreadsheet expressions](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Spreadsheet_Workbench.md). The other modules handle BOMs, reuse comparison and the revision vault. There is no SolidWorks automation or SolidWorks file compatibility here; these are FreeCAD Python macros and design tools.

## Tests and limits

There are 7 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.



Retained project workflows: `freecad-design-tools-ci.yml`. Their commands use this folder and their triggers use its paths.
