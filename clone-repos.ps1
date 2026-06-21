# Clone or update all SMA Sunny Island GitHub repos into this workspace.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$repos = @(
    @{
        Path = "haos-addon-modbus"
        Url  = "https://github.com/mobiletru/sma-si-can-addons.git"
    },
    @{
        Path = "hacs-sma-sunny-island"
        Url  = "https://github.com/mobiletru/sma-sunny-island.git"
    },
    @{
        Path = "cloud-monitor"
        Url  = "https://github.com/mobiletru/sma-si-cloud-monitor.git"
    }
)

foreach ($repo in $repos) {
    $dir = Join-Path $root $repo.Path
    if (Test-Path (Join-Path $dir ".git")) {
        Write-Host "Updating $($repo.Path)..."
        git -C $dir pull --ff-only origin main
    }
    elseif (Test-Path $dir) {
        Write-Host "SKIP $($repo.Path) — folder exists but is not a git repo"
    }
    else {
        Write-Host "Cloning $($repo.Path)..."
        git clone $repo.Url $dir
    }
}

Write-Host ""
Write-Host "Repos ready. See README.md for install URLs."
