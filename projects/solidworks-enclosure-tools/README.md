# solidworks-enclosure-tools

I built this to explore solidworks enclosure tools. This is a learning project.

## Open the model

Download the repo and keep `cad/A` together. Open [the assembly](cad/A/ED-000_desk_device_A.SLDASM). `Default` is closed. `Hatch_open_90` shows the hatch at 90 degrees about the reference servo output axis. I use two fixed hatch instances with configuration-specific suppression, with one active at a time. Both positions survive closing and reopening the assembly. These are saved positions, not a motion simulation.

The folder includes seven native parts, the native assembly, two native drawings, their PDFs, seven STL exports and CAD view images. [The case drawing](cad/A/ED-001_case_A.pdf) and [lid drawing](cad/A/ED-002_lid_A.pdf) include nominal dimensions, datum descriptions, geometric tolerance targets and native flatness frames. They're prototype drawings. They don't fully dimension every feature for production.

## Run the automation

I use Windows PowerShell 5.1 in STA mode with the installed SolidWorks .NET interop library. I used early binding because late-bound calls on this installation returned `TYPE_E_ELEMENTNOTFOUND`. No extra Python package is needed for CAD generation.

```powershell
powershell.exe -NoProfile -STA -File tools/build.ps1 -Output cad/scratch -BeamLength 18 -PostHeight 6
```

SolidWorks must be running with no documents open before generation. The script refuses to close existing documents. It also refuses to build into a folder with a release manifest. Its dimensions use metres internally. `BeamLength` accepts 17 to 20 mm and `PostHeight` accepts 4 to 10 mm. The hook location stays fixed, so changing the tail length doesn't change the active snap length. File identifiers currently use A. I change those identifiers when I start a new revision.

`tools/Enclosure.cs` contains the geometry routines and reusable standoff and servo bracket parts. `tools/inspect.ps1` reopens project parts and runs the static snap study. `tools/results.ps1` reads its results. `tools/assembly.ps1` sets and checks the two hatch positions and runs interference detection. `tools/drawings.ps1` adds native flatness frames and exports the PDFs. These inspection scripts currently target `cad/A`.

```powershell
python tools/check.py
powershell.exe -NoProfile -STA -File tools/release.ps1
```

## Fit and printing

The aperture is 40.0 mm wide and the hatch plate is 39.4 mm. At +/-0.2 mm on each size, the total size gap is `39.8 - 39.6 = 0.2 mm` at its minimum and `40.2 - 39.2 = 1.0 mm` at its maximum. Nominal total gap is 0.6 mm. The same calculation applies to the 24.0 mm aperture and 23.4 mm plate height. This is a size stack, not a guarantee of equal clearance on both sides. Shaft position, print distortion and eccentricity still matter. The hatch sits 0.3 mm above the lid.

I used 2.4 mm walls and floor, plus 1.2 mm snap beams. Those correspond to six and three nominal 0.4 mm nozzle widths. All seven STL exports have closed edges. Their volumes match the native parts within the check's 1 percent tessellation allowance. SolidWorks translates these STL exports to positive coordinates. The calculation restores the hatch's native origin before finding its lever arm.

I would print the case on its floor, the lid on its outer top face with the beams pointing up, and the hatch flat. The case catch ledges and square hook undersides need support planning or a chamfer revision. The mesh report counts downward triangles, including bed faces. It doesn't prove support-free printing. I haven't run a slicer, calibrated clearances or printed a fit coupon.

## Drive sizing

I chose the [TowerPro SG90 Digital](https://towerpro.com.tw/product/sg90-7/) as the reference actuator. TowerPro lists 1.8 kgf cm stall torque at 4.8 V, which is 0.1765 N m. I used only 25 percent of that as a screening allowance, not as a vendor continuous rating.

The exported hatch volume gives a calculated mass of 3.07 g at an assumed PETG density of 1,270 kg/m3. Its centroid is 18.96 mm from the output axis. I added an assumed 0.005 N m friction torque and a design factor of three. The worst gravity orientation requires 0.0167 N m. My screening allowance is 0.0441 N m. Horizontal rotation has no gravity torque about the vertical output axis. I still need the actual servo's current, horn attachment, travel limits and friction measurements before calling this a working motorized device.

The servo cradle is a U bracket. It provides packaging support, not a finished vendor mounting-ear interface. The output extension and hatch bore are reference geometry. I haven't specified a spline, retention screw, electronics, cable exit or powered control system.

[The calculated results](cad/A/engineering-results.json) record the assumptions and mesh measurements. I keep the native files, exports and scripts together so I can change the design and check it again.

## Tests and limits

There are 0 test source files in this copy. That source count does not establish an execution result. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Files omitted from this snapshot:

- cad/A/simulation-results.zip (over 10 MB)


The relocated workflow did not complete successfully within the migration batch. Local test sources remain available.

No project-specific GitHub Actions workflow was retained. The local test sources remain in this folder.
