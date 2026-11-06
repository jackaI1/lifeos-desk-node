$ErrorActionPreference='Stop'
$interop='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $interop
Add-Type -Path (Join-Path $PSScriptRoot 'Readback.cs') -ReferencedAssemblies $interop
[Readback]::Run([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../cad/A')))
