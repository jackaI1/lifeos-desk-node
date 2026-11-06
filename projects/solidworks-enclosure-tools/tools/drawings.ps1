$ErrorActionPreference='Stop'
$interop='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $interop
Add-Type -Path (Join-Path $PSScriptRoot 'DrawingDetails.cs') -ReferencedAssemblies $interop
[DrawingDetails]::Run([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../cad/A')))
