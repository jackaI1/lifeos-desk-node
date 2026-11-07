param([string]$Spec=(Join-Path $PSScriptRoot '../specs/enclosure-B.json'),[string]$Output=(Join-Path $PSScriptRoot '../cad/B'))
$ErrorActionPreference='Stop'
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path ($dll.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path @((Join-Path $PSScriptRoot 'CadCore.cs'),(Join-Path $PSScriptRoot 'SensorEnclosure.cs')) -ReferencedAssemblies @($dll,$dll.Replace('sldworks.dll','swconst.dll'),'System.Web.Extensions.dll')
[SensorEnclosure]::Build((Get-Content $Spec -Raw),[IO.Path]::GetFullPath($Output))
