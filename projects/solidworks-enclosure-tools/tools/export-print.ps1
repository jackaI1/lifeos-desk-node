param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if(Test-Path (Join-Path $Output 'manifest.csv')){throw 'Released folder protected. Export into scratch.'}
$interop='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $interop
Add-Type -Path (Join-Path $PSScriptRoot 'PrintExport.cs') -ReferencedAssemblies $interop
[PrintExport]::Run([IO.Path]::GetFullPath($Source),[IO.Path]::GetFullPath($Output))
