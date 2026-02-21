<#
Install WhisperX environment -- fully self-contained inside this project folder.
No external folders are created; everything (venv, ffmpeg, tools) lives here.

Prerequisites: Python 3.10-3.12 x64 in PATH.  Nothing else.

Run (PowerShell):
  powershell -ExecutionPolicy Bypass -File .\scripts\install_whisperx_windows.ps1

Optional flags:
  -Torch "auto|cu121|cu124|cpu"   -- force a specific PyTorch build
  -SkipFFmpeg                     -- skip ffmpeg auto-download (if you already have it in PATH)
#>

[CmdletBinding()]
param(
  [ValidateSet("auto","cu121","cu124","cpu")]
  [string]$Torch = "auto",
  [switch]$SkipFFmpeg
)

$ErrorActionPreference = "Stop"

# -- helpers ---------------------------------------------------------------
function Info($m){ Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m){ Write-Host "[FAIL] $m" -ForegroundColor Red; exit 2 }
function Test-Command($name){ return [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Ensure-Dir($p){ if(-not (Test-Path $p)){ New-Item -ItemType Directory -Force -Path $p | Out-Null } }

function Has-Nvidia(){
  if(Test-Command "nvidia-smi"){
    try { & nvidia-smi | Out-Null; return $true } catch { return $false }
  }
  return $false
}

function Install-Torch($venvPip, $mode){
  Info "Removing old torch/torchvision/torchaudio (if any)..."
  try { & $venvPip uninstall -y torch torchvision torchaudio 2>$null | Out-Null } catch {}

  Info "Installing PyTorch ($mode) -- this may take several minutes..."
  if($mode -eq "cpu"){
    & $venvPip install --upgrade --no-cache-dir --index-url "https://download.pytorch.org/whl/cpu" torch torchvision torchaudio
    if($LASTEXITCODE -ne 0){ Fail "PyTorch (CPU) install failed." }
    return
  }
  $extra = ""
  if($mode -eq "cu121"){ $extra = "https://download.pytorch.org/whl/cu121" }
  elseif($mode -eq "cu124"){ $extra = "https://download.pytorch.org/whl/cu124" }
  else { Fail "Unknown torch mode: $mode" }

  & $venvPip install --upgrade --no-cache-dir --index-url $extra torch torchvision torchaudio
  if($LASTEXITCODE -ne 0){ Fail "PyTorch ($mode) install failed." }
}

function Download-FFmpeg($destDir){
  $url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
  $tmpZip = Join-Path $env:TEMP "ffmpeg-release-essentials.zip"
  $tmpExtract = Join-Path $env:TEMP ("ffmpeg_extract_" + [guid]::NewGuid().ToString("N"))
  Info "Downloading ffmpeg: $url"
  Invoke-WebRequest -Uri $url -OutFile $tmpZip -UseBasicParsing
  Info "Extracting..."
  Ensure-Dir $tmpExtract
  Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force
  Remove-Item -Force $tmpZip
  $top = Get-ChildItem -Path $tmpExtract | Where-Object { $_.PSIsContainer } | Select-Object -First 1
  if(-not $top){ Fail "ffmpeg archive layout unexpected -- download manually into tools\ffmpeg." }
  if(Test-Path $destDir){ Remove-Item -Recurse -Force $destDir }
  Move-Item -Force $top.FullName $destDir
  Remove-Item -Recurse -Force $tmpExtract
  Info "ffmpeg installed to: $destDir"
}

# -- paths -----------------------------------------------------------------
# Project root = parent of the scripts/ folder that contains this file.
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$venvDir     = Join-Path $ProjectRoot "venv"
$toolsDir    = Join-Path $ProjectRoot "tools"
$ffDir       = Join-Path $toolsDir   "ffmpeg"

Info "Project root : $ProjectRoot"
Info "venv         : $venvDir"
Info "tools        : $toolsDir"

Ensure-Dir $toolsDir

# -- python ----------------------------------------------------------------
if(-not (Test-Command "python")){ Fail "Python not found. Install Python 3.10-3.12 x64 and make sure 'python' is in PATH." }
$pyVer = (& python --version) 2>&1
Info "System Python: $pyVer"

# -- venv ------------------------------------------------------------------
if(-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))){
  Info "Creating venv..."
  & python -m venv $venvDir
  if($LASTEXITCODE -ne 0){ Fail "Failed to create venv." }
} else {
  Info "venv already exists -- reusing."
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip    = Join-Path $venvDir "Scripts\pip.exe"
if(-not (Test-Path $venvPython)){ Fail "venv python not found: $venvPython" }

Info "Upgrading pip..."
& $venvPython -m pip install --upgrade pip setuptools wheel
if($LASTEXITCODE -ne 0){ Warn "pip upgrade had warnings (non-fatal)." }

# -- whisperx (install FIRST -- it pulls torch from PyPI as a dependency) --
Info "Installing whisperx..."
# Pin to 3.1.5 (last version compatible with torch 2.0-2.6).
# whisperx 3.8+ requires torch 2.8 which doesn't have CUDA wheels yet.
& $venvPip install "whisperx==3.1.5"
if($LASTEXITCODE -ne 0){ Fail "whisperx install failed." }

# -- torch (reinstall from the correct index AFTER whisperx) --------------
# whisperx pulls torch from PyPI (CPU-only / generic).
# We now force-reinstall torch+torchvision+torchaudio from the
# official PyTorch wheel index so versions match and GPU works.
$torchMode = $Torch
if($torchMode -eq "auto"){
  if(Has-Nvidia){
    $torchMode = "cu124"
    Info "NVIDIA GPU detected -> using CUDA wheels: $torchMode"
  } else {
    $torchMode = "cpu"
    Warn "NVIDIA GPU not detected -> CPU-only torch. Transcription will be slower."
  }
}
Install-Torch $venvPip $torchMode

Info "Verifying torch installation..."
& $venvPython -c "import torch; print('  torch', torch.__version__); print('  cuda ', torch.cuda.is_available()); print('  device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
if(($torchMode -ne 'cpu') -and (-not (& $venvPython -c "import torch; import sys; sys.exit(0 if torch.cuda.is_available() else 1)"))){
  Warn "CUDA torch installed but torch.cuda.is_available() is False. Check NVIDIA driver or rerun with -Torch cu121."
}

# -- ffmpeg ----------------------------------------------------------------
if($SkipFFmpeg){
  Info "Skipping ffmpeg download (-SkipFFmpeg)."
} else {
  $ffExe = Join-Path $ffDir "bin\ffmpeg.exe"
  if(Test-Path $ffExe){
    Info "ffmpeg already present: $ffExe"
  } elseif(Test-Command "ffmpeg"){
    Info "ffmpeg found in system PATH -- skipping download."
  } else {
    Warn "ffmpeg not found anywhere -- downloading..."
    Download-FFmpeg $ffDir
  }
}

# -- done ------------------------------------------------------------------
Write-Host ""
Info "=========================================="
Info "  Installation complete!"
Info "=========================================="
Info "To launch the GUI, double-click:"
Info "  $ProjectRoot\run.bat"
Write-Host ""
