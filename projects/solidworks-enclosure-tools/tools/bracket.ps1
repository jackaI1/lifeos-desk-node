param([string]$Spec=(Join-Path $PSScriptRoot '../specs/bracket.json'),[string]$Output=(Join-Path $PSScriptRoot '../cad/bracket'))
$ErrorActionPreference='Stop'
if(Test-Path (Join-Path $Output 'manifest.csv')){throw 'Released folder protected'}
$p=Get-Content $Spec -Raw | ConvertFrom-Json
$dll='C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/redist/SolidWorks.Interop.sldworks.dll'
Add-Type -Path $dll
Add-Type -Path (Join-Path $PSScriptRoot 'PrintBracket.cs') -ReferencedAssemblies $dll
[PrintBracket]::Build([IO.Path]::GetFullPath($Output),$p.length_mm,$p.width_mm,$p.height_mm,$p.before_wall_mm,$p.after_wall_mm)
