$ErrorActionPreference='Stop'
$interop='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $interop
Add-Type -Path @((Join-Path $PSScriptRoot 'AssemblyCheck.cs'),(Join-Path $PSScriptRoot 'HatchStates.cs')) -ReferencedAssemblies $interop
[AssemblyCheck]::Run([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../cad/A')))
