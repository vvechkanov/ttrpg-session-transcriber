<#
Install WhisperX environment -- fully self-contained inside this project folder.
No external folders are created; everything (venv, ffmpeg, tools) lives here.

Prerequisites: Python 3.10-3.12 x64 in PATH.  Nothing else.
GPU support  : NVIDIA driver >= 12.1 (RTX 30xx/40xx/50xx).

Run:  double-click install.bat  (or from PowerShell below)
  powershell -ExecutionPolicy Bypass -File .\scripts\install_whisperx_windows.ps1

Optional flags:
  -Torch "auto|cpu"  -- auto = CUDA if NVIDIA GPU detected, else CPU
  -SkipFFmpeg        -- skip ffmpeg auto-download
#>

[CmdletBinding()]
param(
  [ValidateSet("auto","cpu")]
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
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$venvDir     = Join-Path $ProjectRoot "venv"
$toolsDir    = Join-Path $ProjectRoot "tools"
$ffDir       = Join-Path $toolsDir   "ffmpeg"

Info "Project root : $ProjectRoot"
Info "venv         : $venvDir"
Info "tools        : $toolsDir"

Ensure-Dir $toolsDir

# -- python ----------------------------------------------------------------
# Find a compatible Python (3.10-3.12) via the py launcher first, then PATH.
$pythonExe = $null
$compatVersions = @("3.12","3.11","3.10")

if(Test-Command "py"){
  foreach($v in $compatVersions){
    try {
      $testVer = (& py -$v --version 2>&1) | Out-String
      if($testVer -match "Python 3\.(1[0-2])"){
        $pythonExe = "py"
        $pyLauncherArg = "-$v"
        Info "Found compatible Python via py launcher: $($testVer.Trim())"
        break
      }
    } catch {}
  }
}

if(-not $pythonExe -and (Test-Command "python")){
  $testVer = (& python --version 2>&1) | Out-String
  if($testVer -match "Python 3\.(1[0-2])"){
    $pythonExe = "python"
    $pyLauncherArg = $null
    Info "Found compatible Python in PATH: $($testVer.Trim())"
  } else {
    Warn "System 'python' is $($testVer.Trim()) -- not compatible (need 3.10-3.12)."
  }
}

if(-not $pythonExe){ Fail "No compatible Python 3.10-3.12 found. Install one and ensure 'py' launcher or 'python' is in PATH." }

# -- venv ------------------------------------------------------------------
if(-not (Test-Path (Join-Path $venvDir "Scripts\python.exe"))){
  Info "Creating venv..."
  if($pyLauncherArg){
    & $pythonExe $pyLauncherArg -m venv $venvDir
  } else {
    & $pythonExe -m venv $venvDir
  }
  if($LASTEXITCODE -ne 0){ Fail "Failed to create venv." }
} else {
  # Verify existing venv is still functional
  $venvTest = Join-Path $venvDir "Scripts\python.exe"
  try {
    $venvVer = (& $venvTest --version 2>&1) | Out-String
    Info "venv already exists ($($venvVer.Trim())) -- reusing."
  } catch {
    Warn "Existing venv is broken (base Python removed?). Recreating..."
    Remove-Item -Recurse -Force $venvDir
    if($pyLauncherArg){
      & $pythonExe $pyLauncherArg -m venv $venvDir
    } else {
      & $pythonExe -m venv $venvDir
    }
    if($LASTEXITCODE -ne 0){ Fail "Failed to recreate venv." }
  }
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip    = Join-Path $venvDir "Scripts\pip.exe"
if(-not (Test-Path $venvPython)){ Fail "venv python not found: $venvPython" }

Info "Upgrading pip..."
& $venvPython -m pip install --upgrade pip setuptools wheel
if($LASTEXITCODE -ne 0){ Warn "pip upgrade had warnings (non-fatal)." }

# -- decide torch mode -----------------------------------------------------
$torchMode = $Torch
if($torchMode -eq "auto"){
  if(Has-Nvidia){
    $torchMode = "cuda"
    Info "NVIDIA GPU detected -> CUDA mode"
  } else {
    $torchMode = "cpu"
    Warn "NVIDIA GPU not detected -> CPU mode (slower)."
  }
}

# -- torch -----------------------------------------------------------------
if($torchMode -eq "cpu"){
  Info "Installing PyTorch (CPU) -- this may take a few minutes..."
  & $venvPip install --no-cache-dir --index-url "https://download.pytorch.org/whl/cpu" torch torchvision torchaudio
  if($LASTEXITCODE -ne 0){ Fail "PyTorch (CPU) install failed." }
} else {
  # cu126 index has torch 2.8+ with CUDA support for Windows
  Info "Installing PyTorch (CUDA, cu126 index) -- this may take several minutes..."
  & $venvPip install --no-cache-dir --index-url "https://download.pytorch.org/whl/cu126" torch torchvision torchaudio
  if($LASTEXITCODE -ne 0){ Fail "PyTorch (CUDA) install failed." }
}

# -- whisperx (from official GitHub repo) ----------------------------------
# PyPI releases are yanked/outdated; GitHub repo is canonical.
Info "Installing whisperx from GitHub..."
& $venvPip install "whisperx @ git+https://github.com/m-bain/whisperX.git"
if($LASTEXITCODE -ne 0){ Fail "whisperx install failed." }

# -- re-pin torch (whisperx may pull a different torch from PyPI) ----------
if($torchMode -ne "cpu"){
  Info "Re-pinning PyTorch CUDA wheels (safety reinstall)..."
  & $venvPip install --force-reinstall --no-cache-dir --no-deps --index-url "https://download.pytorch.org/whl/cu126" torch torchvision torchaudio
  if($LASTEXITCODE -ne 0){ Warn "torch re-pin had warnings (non-fatal)." }
}

# -- verify ----------------------------------------------------------------
Info "Verifying torch installation..."
& $venvPython -c "import torch; print('  torch', torch.__version__); print('  cuda ', torch.cuda.is_available()); print('  device', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
& $venvPython -c "import torch; import sys; sys.exit(0 if torch.cuda.is_available() else 1)"
if(($torchMode -ne 'cpu') -and ($LASTEXITCODE -ne 0)){
  Warn "CUDA torch installed but torch.cuda.is_available() is False."
  Warn "Check NVIDIA driver or rerun with: -Torch cpu"
}

Info "Verifying whisperx..."
& $venvPython -c "import whisperx; print('  whisperx OK')"

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
Info "  Installation complete! ($torchMode mode)"
Info "=========================================="
Info "To launch the GUI, double-click:"
Info "  $ProjectRoot\run.bat"
Write-Host ""
