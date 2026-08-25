param(
  [string]$VenvPython = ".\venv\Scripts\python.exe",
  [switch]$Web,
  [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$script:shutdownStarted = $false
$script:processes = @{}

function Assert-Executable {
  param(
    [Parameter(Mandatory)]
    [string]$Path,
    [Parameter(Mandatory)]
    [string]$Description
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "Missing $Description at: $Path"
  }
}

function Start-AppProcess {
  param(
    [Parameter(Mandatory)]
    [string]$Name,

    [Parameter(Mandatory)]
    [string]$FilePath,

    [Parameter(Mandatory)]
    [string[]]$ArgumentList
  )

  Write-Host "Starting $Name..."

  try {
    $process = Start-Process `
      -FilePath $FilePath `
      -ArgumentList $ArgumentList `
      -WorkingDirectory (Get-Location).Path `
      -NoNewWindow `
      -PassThru

    $script:processes[$Name] = $process
    return $process
  }
  catch {
    throw "Failed to start $Name`: $($_.Exception.Message)"
  }
}

function Test-ProcessRunning {
  param([System.Diagnostics.Process]$Process)

  if ($null -eq $Process) {
    return $false
  }

  try {
    if ($Process.HasExited) {
      return $false
    }

    return $true
  }
  catch {
    return $false
  }
}

function Stop-AppProcess {
  param(
    [Parameter(Mandatory)]
    [string]$Name,

    [int]$TimeoutSeconds = 10
  )

  if (-not $script:processes.ContainsKey($Name)) {
    return
  }

  $process = $script:processes[$Name]

  if (-not (Test-ProcessRunning -Process $process)) {
    return
  }

  Write-Host "Stopping $Name`: $($process.Id)"

  # Ask GUI-style applications to close normally when possible.
  try {
    if ($process.MainWindowHandle -ne [IntPtr]::Zero) {
      [void]$process.CloseMainWindow()
    }
  }
  catch {
    # Console/Python processes usually do not expose a main window.
  }

  # Give the process time to exit gracefully.
  try {
    if ($process.WaitForExit($TimeoutSeconds * 1000)) {
      return
    }
  }
  catch {
    # Continue to forced cleanup.
  }

  # Fall back to terminating the process tree.
  try {
    Start-Process `
      -FilePath "taskkill.exe" `
      -ArgumentList @("/PID", "$($process.Id)", "/T", "/F") `
      -WindowStyle Hidden `
      -Wait `
      -NoNewWindow `
      -ErrorAction SilentlyContinue | Out-Null
  }
  catch {
    try {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    catch {}
  }
}

function Shutdown-All {
  if ($script:shutdownStarted) {
    return
  }

  $script:shutdownStarted = $true
  Write-Host "Shutting down..."

  # Match the Bash shutdown order:
  #   1. GUI
  #   2. Agentic loop poller
  #   3. Telegram/ZMQ subscriber
  #   4. Workflow server
  #   5. Ollama
  Stop-AppProcess -Name "GUI"
  Stop-AppProcess -Name "Agentic loop poller"
  Stop-AppProcess -Name "Telegram/ZMQ subscriber"
  Stop-AppProcess -Name "Workflow server"
  Stop-AppProcess -Name "Ollama"

  Write-Host "Shutdown complete."
}

Assert-Executable `
  -Path $VenvPython `
  -Description "venv Python"

$fletExe = ".\venv\Scripts\flet.exe"
if (Test-Path -LiteralPath $fletExe) {
  $fletCommand = $fletExe
}
else {
  $fletCommand = "flet"
}

# Start workflow server.
Start-AppProcess `
  -Name "Workflow server" `
  -FilePath $VenvPython `
  -ArgumentList @(
    "-u",
    "services/server/workflow_server.py"
  ) | Out-Null

# Start Telegram/ZMQ subscriber.
Start-AppProcess `
  -Name "Telegram/ZMQ subscriber" `
  -FilePath $VenvPython `
  -ArgumentList @(
    "-u",
    "messengers_integrations/telegram/telegram_bot_api/tg_zmq_subscriber.py"
  ) | Out-Null

# Start the agentic loop poller.
Start-AppProcess `
  -Name "Agentic loop poller" `
  -FilePath $VenvPython `
  -ArgumentList @(
    "-u",
    "-m",
    "services.agentic_loop.loop_poller"
  ) | Out-Null

# Start Ollama.
Start-AppProcess `
  -Name "Ollama" `
  -FilePath "ollama" `
  -ArgumentList @("serve") | Out-Null

# Start Flet.
$fletArguments = @("run", "gui/main.py")

if ($Web) {
  $fletArguments += "--web"

  if ($Port -gt 0) {
    $fletArguments += @("-p", "$Port")
  }
  else {
    $fletArguments += @("-p", "8550")
  }
}

$gui = Start-AppProcess `
  -Name "GUI" `
  -FilePath $fletCommand `
  -ArgumentList $fletArguments

try {
  # Keep the launcher alive while the GUI is running.
  $gui.WaitForExit()
}
finally {
  # Handles normal GUI exit, startup errors, and Ctrl+C cleanup.
  Shutdown-All
}
