param(
    [switch]$Rebuild
)

$composeCommand = "docker","compose","-p","lost-and-found"

if ($Rebuild.IsPresent) {
    $composeCommand += @("up","--build")
} else {
    $composeCommand += @("up")
}

$rootPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path "$rootPath/.."
$dataPath = Join-Path $projectRoot "data"

if (-not (Test-Path $dataPath)) {
    New-Item -ItemType Directory -Path $dataPath | Out-Null
}

Write-Host "Running:" ($composeCommand -join " ")
Push-Location $projectRoot
try {
    & $composeCommand
} finally {
    Pop-Location
}
