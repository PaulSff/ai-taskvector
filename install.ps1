param(
  [string]$RepoUrl = "https://github.com/PaulSff/ai-taskvector.git",
  [string]$DirName = "ai-taskvector",
  [string]$Extras  = "rag,gui,llm-integrations,messengers-integrations,units-web,units-semantics,units-messengers,units-time,units-network,units-coding,mcp-integrations",
  [string]$PyMin = "3.12.6",
  [string]$Model = "gemma4:31b-cloud"
)

$ErrorActionPreference = "Stop"

function Test-Python {
  $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $py) { return $false }
  try {
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,12,6) else 1)" | Out-Null
    return $true
  } catch { return $false }
}

function Install-Python {
  Write-Host "Python (>= $PyMin) not found. Installing..."

  $installer = "$env:TEMP\python-installer.exe"
  $url = "https://www.python.org/ftp/python/3.12.6/python-3.12.6-amd64.exe"

  Invoke-WebRequest -Uri $url -OutFile $installer

  Start-Process -FilePath $installer -ArgumentList @(
    "/quiet",
    "InstallAllUsers=1",
    "PrependPath=1",
    "Include_test=0"
  ) -Wait -NoNewWindow

  if (-not (Test-Python)) {
    throw "Python installed, but python >= $PyMin is still not available."
  }
}

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Missing required tool: $name"
  }
}

function Install-OllamaAndModel {
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Ollama..."
    Invoke-Expression ( "irm https://ollama.com/install.ps1 | iex" )
  }

  Write-Host "Pulling Ollama model: $Model"
  ollama pull $Model
}

Assert-Command "git"

if (-not (Test-Python)) {
  Install-Python
}

# venv + pip deps
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}
. .\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel

# clone
if (-not (Test-Path $DirName)) {
  git clone $RepoUrl $DirName
}

Set-Location $DirName
python -m pip install -e ".[$Extras]"

Install-OllamaAndModel

Write-Host "Done."
