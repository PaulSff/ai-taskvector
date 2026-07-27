# Graceful shutdown order:
# 1) stop GUI first
# 2) then stop server
# Uses the venv python explicitly.

param(
  [string]$VenvPython = ".\venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Assert-VenvPython {
  if (-not (Test-Path $VenvPython)) {
    throw "Missing venv python at: $VenvPython"
  }
}
Assert-VenvPython

# Start server (background)
$server = Start-Process -FilePath $VenvPython `
  -ArgumentList @("-u","services/server/workflow_server.py") `
  -NoNewWindow -PassThru
$server_pid = $server.Id

# Start GUI in foreground (so you can see logs)
$gui = Start-Process -FilePath $VenvPython `
  -ArgumentList @("-m","gui.main") `
  -NoNewWindow -PassThru
$gui_pid = $gui.Id

function Send-GracefulInt {
  param([int]$Pid)

  if ($Pid -le 0) { return }

  # Stop-Process -Id defaults to a hard kill; we want graceful.
  # Send Ctrl+C to the target console process isn't trivial cross-version,
  # so we use taskkill without /F (graceful).
  # This maps to the closest "SIGINT-like" behavior on Windows.
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
