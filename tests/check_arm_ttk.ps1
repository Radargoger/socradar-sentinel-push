param(
    [Parameter(Mandatory=$true)][string]$ModulePath,
    [string]$TemplatePath = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory=$true)][string]$ResultFile
)
$ErrorActionPreference = 'Stop'
Import-Module $ModulePath -Force
# Capture the error stream as well as verdicts. ErrorVariable also collects
# PowerShell ContinueException control flow from inside the toolkit.
$all = @(Test-AzTemplate -TemplatePath $TemplatePath -ErrorAction Continue 2>&1)
$errors = @($all | Where-Object {$_ -is [System.Management.Automation.ErrorRecord]})
$records = @($all | Where-Object {$_.PSObject.Properties.Name -contains 'Passed'})
$failed = @($records | Where-Object {-not $_.Passed})
$rows = @($records | ForEach-Object {
    @{Name=$_.Name;Passed=$_.Passed;File=$_.File.FullName;
      Errors=@($_.Errors | ForEach-Object {"$_"});
      Warnings=@($_.Warnings | ForEach-Object {"$_"})}
})
ConvertTo-Json -InputObject $rows -Depth 30 | Set-Content $ResultFile
@{total=$records.Count;failed=$failed.Count;errorRecords=$errors.Count;
  templatePath=$TemplatePath;command='Test-AzTemplate -TemplatePath <path>'} |
    ConvertTo-Json | Set-Content ($ResultFile+'.summary.json')
Write-Output "ARM-TTK TOTAL=$($records.Count) FAIL=$($failed.Count) ERRORS=$($errors.Count)"
if ($records.Count -lt 32 -or $failed.Count -gt 0 -or $errors.Count -gt 0) {exit 1}
exit 0
