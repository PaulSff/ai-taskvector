param(
  [string]$VenvPython = ".\venv\Scripts\python.exe",
  [switch]$Web,
  [int]$Port = 0
)

# Run GUI app: .\run.ps1
# Run GUI web: .\run.ps1 -Web -Port 9999

$ErrorActionPreference = "Stop"

function Assert-VenvPython {
  if (-not (Test-Path $VenvPython)) {
    throw "Missing venv python at: $VenvPython"
  }
}
Assert-VenvPython

# Use venv flet if available; fall back to "flet" on PATH
$fletExe = ".\venv\Scripts\flet.exe"
if ($Web -and (Test-Path $fletExe)) {
  $fletCmd = $fletExe
} elseif ($Web) {
  $fletCmd = "flet"
}

# Start server (background)
$server = Start-Process -FilePath $VenvPython `
  -ArgumentList @("-u","services/server/workflow_server.py") `
  -NoNewWindow -PassThru
$server_pid = $server.Id

# Start GUI in foreground (so you can see logs)
if ($Web) {
  $args = @("run","gui/main.py","--web")
  if ($Port -gt 0) {
    $args += @("-p", $Port.ToString())
  }
  $gui = Start-Process -FilePath $fletCmd `
    -ArgumentList $args `
    -NoNewWindow -PassThru
} else {
  # normal mode
  $gui = Start-Process -FilePath $fletCmd `
    -ArgumentList @("run","gui/main.py") `
    -NoNewWindow -PassThru
}

$gui_pid = $gui.Id

function Send-GracefulInt {
  param([int]$Pid)
  if ($Pid -le 0) { return }

  # taskkill without /F = graceful-ish (Ctrl+C-like behavior isn't fully consistent on Windows).
  try {
    Start-Process -FilePath "taskkill" -ArgumentList @("/PID","$Pid") -WindowStyle Hidden -Wait | Out-Null
  } catch {}
}

function Shutdown-GuiThenServer {
  Write-Host "Shutting down..."

  # GUI first
  if ($null -ne $gui_pid -and $gui_pid -gt 0) {
    Send-GracefulInt -Pid $gui_pid
    try { $gui.WaitForExit() } catch {}
  }

  # Then server
  if ($null -ne $server_pid -and $server_pid -gt 0) {
    Send-GracefulInt -Pid $server_pid
    try { $server.WaitForExit() } catch {}
  }
}

# Ensure shutdown on Ctrl+C / termination
$script:didShutdown = $false
$action = {
  if (-not $script:didShutdown) {
    $script:didShutdown = $true
    Shutdown-GuiThenServer
  }
}

$sub = Register-ObjectEvent -InputObject $Host -EventName CancelKeyPress -Action $action

try {
  # Block until GUI exits; then shut down server
  $gui.WaitForExit()
  Shutdown-GuiThenServer
}
finally {
  if ($sub) {
    Unregister-Event -SubscriptionId $sub.Id -ErrorAction SilentlyContinue | Out-Null
  }
}
