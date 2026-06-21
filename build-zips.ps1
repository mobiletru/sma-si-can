# Build local HAOS app zip (dev fallback — production installs use GitHub repo)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$slug = "local_sunny_island_can"
$repoAddon = Join-Path $root "haos-addon-modbus\$slug"

if (-not (Test-Path $repoAddon)) {
    Write-Host "Missing haos-addon-modbus/ — run .\clone-repos.ps1 first"
    exit 1
}
$addonDir = Join-Path $root "addon\$slug"
$dist = Join-Path $root "dist"
$zipPath = Join-Path $dist "$slug.zip"

# Remove stale zip names from prior slugs / multi-app builds
$staleZipPatterns = @(
    "sma-sunny-island.zip",
    "sma-si-*.zip"
)
foreach ($pattern in $staleZipPatterns) {
    Get-ChildItem -Path $dist -Filter $pattern -ErrorAction SilentlyContinue | Remove-Item -Force
}

# Remove stale extracted repo folders that confuse local installs
$staleDirs = @(
    (Join-Path $dist "sma-si-can-addons"),
    (Join-Path $root "repo-build\sma-si-can-addons"),
    (Join-Path $root "haos-addons-local")
)
foreach ($dir in $staleDirs) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force
        Write-Host "Removed stale: $dir"
    }
}

Copy-Item "$repoAddon\*" $addonDir -Recurse -Force

if (-not (Test-Path (Join-Path $addonDir "config.yaml"))) {
    throw "Missing add-on folder: $addonDir"
}

New-Item -ItemType Directory -Force -Path $dist | Out-Null
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Compress-Archive -Path $addonDir -DestinationPath $zipPath -Force

Write-Host "Built: $zipPath"
Write-Host ""
Write-Host "GitHub app repo (Settings -> Apps -> Repositories):"
Write-Host "  https://github.com/mobiletru/sma-si-can-addons"
Write-Host ""
Write-Host "Install on HA OS (Samba addons share):"
Write-Host "  addons/$slug/config.yaml"
Write-Host ""
Write-Host "  WRONG: addons/local/$slug/  (extra local/ folder is not detected)"
Write-Host ""
Write-Host "App dashboard: /$slug"
