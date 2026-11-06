param([string]$Output = (Join-Path $PSScriptRoot '../cad/A'), [double]$BeamLength=18, [double]$PostHeight=6)
$ErrorActionPreference = 'Stop'
if(Test-Path (Join-Path $Output 'manifest.csv')) { throw 'This revision has a manifest. Build into an unreleased folder.' }
$interop = 'C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $interop
Add-Type -Path ($interop.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path @((Join-Path $PSScriptRoot 'Enclosure.cs'),(Join-Path $PSScriptRoot 'HatchStates.cs')) -ReferencedAssemblies $interop
if ($BeamLength -lt 17 -or $BeamLength -gt 20) { throw 'BeamLength must be 17 to 20 mm for this hook location.' }
if ($PostHeight -lt 4 -or $PostHeight -gt 10) { throw 'PostHeight must be 4 to 10 mm.' }
[Enclosure]::BeamLength=$BeamLength
[Enclosure]::PostHeight=$PostHeight
[Enclosure]::Build([IO.Path]::GetFullPath($Output))
