param([string]$Spec=(Join-Path $PSScriptRoot '../specs/clamp.json'),[string]$Output=(Join-Path $PSScriptRoot '../cad/clamp'),[switch]$ParameterCases)
$ErrorActionPreference='Stop'
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path ($dll.Replace('sldworks.dll','swconst.dll'))
Add-Type -Path @((Join-Path $PSScriptRoot 'CadCore.cs'),(Join-Path $PSScriptRoot 'ClampFixture.cs'),(Join-Path $PSScriptRoot 'ClampReadback.cs')) -ReferencedAssemblies @($dll,$dll.Replace('sldworks.dll','swconst.dll'),'System.Web.Extensions.dll')
$json=Get-Content $Spec -Raw
[ClampFixture]::Run($json,[IO.Path]::GetFullPath($Output),$true)
Start-Sleep -Seconds 3
[ClampReadback]::Run([IO.Path]::GetFullPath($Output),$true)
if($ParameterCases){
 $base=$json | ConvertFrom-Json
 foreach($case in $base.parameter_cases){
  Start-Sleep -Seconds 3
  $changed=$json | ConvertFrom-Json
  foreach($prop in $case.overrides.PSObject.Properties){$changed.($prop.Name)=$prop.Value}
  [ClampFixture]::Run(($changed | ConvertTo-Json -Depth 10),[IO.Path]::GetFullPath((Join-Path $Output ('cases/'+$case.name))),$false)
  Start-Sleep -Seconds 3
  [ClampReadback]::Run([IO.Path]::GetFullPath((Join-Path $Output ('cases/'+$case.name))),$false)
 }
}
