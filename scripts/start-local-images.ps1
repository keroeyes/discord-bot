$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$previous = @{}
foreach ($name in @('DISCORD_TOKEN', 'IMAGE_OWNER_ID', 'COMFYUI_CHECKPOINT', 'COMFYUI_PORT')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$secureToken = $null
try {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.11 or later with the Windows py launcher first.'
    }
    & py -3 -c "import sys; assert sys.version_info >= (3, 11)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or later is required.' }
    $rawPort = Read-Host 'ComfyUI local port (Enter = 8188)'
    if ([string]::IsNullOrWhiteSpace($rawPort)) { $rawPort = '8188' }
    $port = 0
    if (-not [int]::TryParse($rawPort, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        throw 'Invalid port.'
    }
    try {
        $info = Invoke-RestMethod -Uri "http://127.0.0.1:$port/object_info/CheckpointLoaderSimple" -TimeoutSec 10 -MaximumRedirection 0
    } catch { throw 'Start ComfyUI locally, then check its port. No connection established.' }
    $models = @($info.CheckpointLoaderSimple.input.required.ckpt_name[0])
    if ($models.Count -eq 0) { throw 'No checkpoint found. Install an SDXL checkpoint in ComfyUI first.' }
    Write-Host 'Installed checkpoints (select an SDXL model):'
    for ($i = 0; $i -lt $models.Count; $i++) { Write-Host "$($i + 1). $($models[$i])" }
    $selection = 0
    if (-not [int]::TryParse((Read-Host 'Model number'), [ref]$selection) -or $selection -lt 1 -or $selection -gt $models.Count) {
        throw 'Invalid model number.'
    }
    $checkpoint = [string]$models[$selection - 1]
    if ($checkpoint.Contains('/') -or $checkpoint.Contains('\')) {
        throw 'Move this checkpoint to the top level of models/checkpoints first.'
    }
    $owner = Read-Host 'Your Discord user ID'
    if ($owner -notmatch '^[0-9]+$' -or $owner -match '^0+$') { throw 'Invalid Discord user ID.' }
    $python = Join-Path $projectRoot '.venv-images\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        & py -3 -m venv .venv-images
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment setup failed.' }
    }
    & $python -m pip install -r requirements-images.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    $secureToken = Read-Host 'Discord bot token (hidden input)' -AsSecureString
    $env:DISCORD_TOKEN = [System.Net.NetworkCredential]::new('', $secureToken).Password
    $env:IMAGE_OWNER_ID = $owner
    $env:COMFYUI_CHECKPOINT = $checkpoint
    $env:COMFYUI_PORT = [string]$port
    Write-Host 'Starting local image worker. Keep ComfyUI and this window open. Stop with Ctrl+C.'
    & $python image_worker.py
    if ($LASTEXITCODE -ne 0) { throw 'Worker stopped with an error.' }
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
    if ($null -ne $secureToken) { $secureToken.Dispose() }
}
