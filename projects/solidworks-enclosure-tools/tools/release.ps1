param([string]$Revision='A')
$ErrorActionPreference='Stop'
if($Revision -notmatch '^[A-Z]$'){throw 'Use a single letter revision.'}
$root=Join-Path $PSScriptRoot "../cad/$Revision"
$files=Get-ChildItem $root -File | Where-Object {$_.Name -notlike '~$*' -and $_.Name -ne 'manifest.csv' -and $_.Extension -notin '.CWR','.gsz','.LOG' -and $_.Name -notlike '*Solver.txt' -and $_.Name -ne 'PerformanceLog.txt'}
if(-not ($files.Name -contains "ED-000_desk_device_$Revision.SLDASM")){throw 'Assembly missing'}
$files | Sort-Object Name | ForEach-Object {
 [pscustomobject]@{file=$_.Name; revision=$Revision; status='PROTOTYPE'; bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}
} | Export-Csv (Join-Path $root 'manifest.csv') -NoTypeInformation
Write-Output "Manifest created for revision $Revision. Review before committing."
