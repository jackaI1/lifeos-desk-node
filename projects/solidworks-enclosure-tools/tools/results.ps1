$ErrorActionPreference='Stop'
$base='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/'
Add-Type -Path ($base+'SolidWorks.Interop.sldworks.dll')
Add-Type -Path ($base+'SolidWorks.Interop.cosworks.dll')
Add-Type -Path (Join-Path $PSScriptRoot 'Inspect.cs') -ReferencedAssemblies @(($base+'SolidWorks.Interop.sldworks.dll'),($base+'SolidWorks.Interop.cosworks.dll'))
[Inspect]::ReadResults([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../cad/A')))
