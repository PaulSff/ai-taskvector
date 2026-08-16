param(
  [string]$VenvPython = ".\venv\Scripts\python.exe",
  [switch]$Web,
  [int]$Port = 0
)

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

# Start ZMQ subscriber service (background)
# (Adjust VenvPython path is already handled by $VenvPython above)
$subscriber = Start-Process -FilePath $VenvPython `
  -ArgumentList @("-u","messengers_integrations/telegram/telegram_bot_api/tg_zmq_subscriber.py") `
  -NoNewWindow -PassThru
$subscriber_pid = $subscriber.Id

# Start Ollama (background, like "ollama serve")
# If you run Ollama from PATH it should work; if you need a fixed path, set it here.
$ollama = Start-Process -FilePath "ollama" -ArgumentList @("serve") `
  -NoNewWindow -PassThru
$ollama_pid = $ollama.Id

# Start GUI in foreground (so you can see logs)
if ($Web) {
  $args = @("run","gui/main.py","--web")

  # Mirror bash behavior:
  # if --web is set but no -p/--port is provided (Port == 0), default to 8550
  if ($Port -gt 0) {
    $args += @("-p", $Port.ToString())
  } else {
    $args += @("-p", "8550")
  }

  $gui = Start-Process -FilePath $fletCmd `
    -ArgumentList $args `
    -NoNewWindow -PassThru
} else {
  $gui = Start-Process -FilePath $fletCmd `
    -ArgumentList @("run","gui/main.py") `
    -NoNewWindow -PassThru
}

$gui_pid = $gui.Id

function Send-GracefulInt {
  param([int]$Pid)
  if ($Pid -le 0) { return }

  try {
    Start-Process -FilePath "taskkill" -ArgumentList @("/PID","$Pid") -WindowStyle Hidden -Wait | Out-Null
  } catch {}
}

function Shutdown-GuiThenServices {
  Write-Host "Shutting down..."

  # GUI first
  if ($null -ne $gui_pid -and $gui_pid -gt 0) {
    Send-GracefulInt -Pid $gui_pid
    try { $gui.WaitForExit() } catch {}
  }

  # Then subscriber
  if ($null -ne $subscriber_pid -and $subscriber_pid -gt 0) {
    Send-GracefulInt -Pid $subscriber_pid
    try { $subscriber.WaitForExit() } catch {}
  }

  # Then server
  if ($null -ne $server_pid -and $server_pid -gt 0) {
    Send-GracefulInt -Pid $server_pid
    try { $server.WaitForExit() } catch {}
  }

  # Then ollama
  if ($null -ne $ollama_pid -and $ollama_pid -gt 0) {
    Send-GracefulInt -Pid $ollama_pid
    try { $ollama.WaitForExit() } catch {}
  }
}

# Ensure shutdown on Ctrl+C / termination
$script:didShutdown = $false
$action = {
  if (-not $script:didShutdown) {
    $script:didShutdown = $true
    Shutdown-GuiThenServices
  }
}

$sub = Register-ObjectEvent -InputObject $Host -EventName CancelKeyPress -Action $action

try {
  # Block until GUI exits; then shut down everything
  $gui.WaitForExit()
  Shutdown-GuiThenServices
}
finally {
  if ($sub) {
    Unregister-Event -SubscriptionId $sub.Id -ErrorAction SilentlyContinue | Out-Null
  }
}
