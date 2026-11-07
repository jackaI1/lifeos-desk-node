# SolidWorks enclosure tools

I wanted to learn how to automate CAD and check a design before making it, so I built small enclosure and fixture tools. I can generate native parts and drawings, inspect saved meshes, and compare fit and printing assumptions.

The examples use practice geometry, assumed material properties and virtual printer settings. They are not physically tested assemblies. The native files carry the SolidWorks Student Edition educational designation.

## Try it

I keep the first enclosure in `cad/A`, a sensor enclosure in `cad/B`, and the bracket, assembly nest, cartridge and clamp examples beside them. Keep each folder together when opening its native files. Design inputs are in `specs/`.

The Python checks use saved geometry and do not need SolidWorks. From this folder with Python 3.12:

```sh
python -m pip install -r requirements-checks.txt
python tools/check.py
PYTHONPATH=tools python -m pytest -q
python tools/manifest.py
```

Native generation needs Windows PowerShell 5.1 in STA mode, SolidWorks and its .NET interop library. For example:

```powershell
powershell.exe -NoProfile -STA -File tools/build.ps1 -Output cad/scratch -BeamLength 18 -PostHeight 6
```

SolidWorks must be running with no documents open. The script refuses to overwrite a folder with a release manifest. Other PowerShell entry points in `tools/` generate the sensor enclosure, fixtures and drawings. `docs/revisions.md` explains the saved revisions.

## How it works

C# geometry helpers drive the SolidWorks COM API. PowerShell scripts build, reopen, inspect and export parts. Python reads saved STL triangles, compares mesh and recorded native volumes, checks closed geometry and evaluates simplified engineering calculations.

`tools/printcheck.py` screens sampled walls, overhangs, build-envelope fit and support estimates. `tools/stackup.py` calculates gasket-compression bounds and reproducible tolerance samples. The fixture, cartridge and clamp checkers read their own specifications. Checked-in meshes and reference records needed by the tests stay with the source.

## Tests and limits

I ran all 30 Python tests locally and all 30 passed in 0.41 seconds. They cover reference meshes, deliberately broken specifications, tolerance corner cases and recorded slicing hashes. The revision A engineering checker completed successfully, and the manifest checker verified 169 files across six saved export folders. The path-filtered hub workflow `.github/workflows/solidworks-enclosure-tools-mesh.yml` runs these Python checks from this folder.

Those checks do not prove physical fit, seal performance, fatigue life or safe printer settings. Native regeneration still needs SolidWorks on Windows; I did not repeat that step on this Mac. The drawings and simulation assumptions need physical review before manufacture.

I left out `cad/A/simulation-results.zip` because it exceeds 10 MB. Installed dependencies, caches and disposable build output are omitted. Committed reference meshes and records used by the tests remain included.
