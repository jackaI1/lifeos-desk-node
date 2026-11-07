param([string]$Spec=(Join-Path $PSScriptRoot '../specs/fixture.json'),[string]$Output=(Join-Path $PSScriptRoot '../cad/fixture'))
$ErrorActionPreference='Stop'
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path ($dll.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path @((Join-Path $PSScriptRoot 'CadCore.cs'),(Join-Path $PSScriptRoot 'AssemblyFixture.cs')) -ReferencedAssemblies @($dll,$dll.Replace('sldworks.dll','swconst.dll'),'System.Web.Extensions.dll')
[AssemblyFixture]::Run((Get-Content $Spec -Raw),[IO.Path]::GetFullPath($Output))
