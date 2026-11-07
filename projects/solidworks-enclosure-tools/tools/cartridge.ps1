param([string]$Spec=(Join-Path $PSScriptRoot '../specs/cartridge.json'),[string]$Output=(Join-Path $PSScriptRoot '../cad/cartridge'))
$ErrorActionPreference='Stop'
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path ($dll.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path @((Join-Path $PSScriptRoot 'CadCore.cs'),(Join-Path $PSScriptRoot 'FluidCartridge.cs')) -ReferencedAssemblies @($dll,$dll.Replace('sldworks.dll','swconst.dll'),'System.Web.Extensions.dll')
[FluidCartridge]::Run((Get-Content $Spec -Raw),[IO.Path]::GetFullPath($Output))
