param([Parameter(Mandatory=$true)][string]$Root,[switch]$Drawing)
$ErrorActionPreference='Stop'
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path ($dll.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path (Join-Path $PSScriptRoot 'ClampReadback.cs') -ReferencedAssemblies @($dll,$dll.Replace('sldworks.dll','swconst.dll'),'System.Web.Extensions.dll')
[ClampReadback]::Run([IO.Path]::GetFullPath($Root),$Drawing.IsPresent)
