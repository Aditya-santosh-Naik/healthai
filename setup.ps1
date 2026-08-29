<#
    HealthAI - one-command setup (Windows).

        powershell -ExecutionPolicy Bypass -File setup.ps1

    Safe to re-run: every step is idempotent.
#>
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Step($n) { Write-Host "`n=== $n ===" -ForegroundColor Cyan }
function Ok($n)   { Write-Host "  OK  $n" -ForegroundColor Green }
function Warn($n) { Write-Host "  --  $n" -ForegroundColor Yellow }
function Note($n) { Write-Host "      $n" -ForegroundColor Red }
function Die($n)  { Write-Host "  !!  $n" -ForegroundColor Red; exit 1 }

# PowerShell 5.1 turns anything a native command writes to stderr into an
# ErrorRecord, which $ErrorActionPreference = "Stop" then escalates into a
# terminating error -- so a tool that merely printed a warning would kill the
# script, and pip prints warnings constantly. Every native call goes through
# here instead, and success is judged by exit code alone.
function Native {
    param([string]$Exe, [string[]]$Arguments, [switch]$Quiet)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) { & $Exe @Arguments 2>&1 | Out-Null }
        else        { & $Exe @Arguments 2>&1 | ForEach-Object { Write-Host "  $_" } }
    } finally { $ErrorActionPreference = $prev }
    return $LASTEXITCODE
}

Step "Checking prerequisites"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Die "Python not found. Install Python 3.11+ from python.org, ticking 'Add python.exe to PATH'."
}
$pyv = (& python -c "import sys;print('%d.%d'%sys.version_info[:2])")
if ([version]$pyv -lt [version]"3.11") { Die "Python $pyv found, but 3.11+ is required." }
Ok "Python $pyv"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Die "Node not found. Install Node 18+ from nodejs.org." }
Ok "Node $(node --version)"

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Ok "Ollama present"
} else {
    Warn "Ollama not found. The app still runs end to end: every AI surface has a"
    Warn "deterministic fallback. Install from ollama.com for the full demo, then:"
    Warn "  ollama pull qwen2.5:3b"
}

Step "Checking Windows Long Path support"
# PyTorch ships headers whose paths exceed the legacy 260-character limit, so
# pip fails part-way through the install without this. Far cheaper to catch it
# here than after a 700 MB download.
$lp = 0
try {
    $lp = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
           -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
} catch { $lp = 0 }
if ($lp -eq 1) {
    Ok "Long paths enabled"
} elseif ($root.Length -gt 40) {
    Write-Host "  !!  Long Path support is off and this folder's path is long," -ForegroundColor Red
    Note "so pip will fail on PyTorch's header files."
    Note ""
    Note "Fix it: open PowerShell AS ADMINISTRATOR and run"
    Write-Host '        New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force' -ForegroundColor Yellow
    Note "then restart the terminal and re-run setup.ps1."
    Note "Or move the project to a short path such as C:\healthai."
    Die "Stopping before the download rather than failing part-way through it."
} else {
    Warn "Long Path support is off, but this path is short enough to probably be"
    Warn "fine. Enable it if pip fails on a long filename."
}

Step "Backend: virtual environment"
$venvPy = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    if ((Native "python" @("-m","venv",(Join-Path $root "backend\.venv")) -Quiet) -ne 0) {
        Die "Could not create the virtual environment."
    }
}
Native $venvPy @("-m","pip","install","--quiet","--upgrade","pip") -Quiet | Out-Null
Ok "backend\.venv"

Step "Backend: dependencies (~700 MB on first run, mostly PyTorch)"
Write-Host "  This takes a few minutes. Leave it alone." -ForegroundColor DarkGray
if ((Native $venvPy @("-m","pip","install","-r",(Join-Path $root "backend\requirements.txt")) -Quiet) -ne 0) {
    Write-Host "  !!  pip install failed." -ForegroundColor Red
    Note "If the error mentioned a long filename, enable Long Path support"
    Note "(see the instructions above) and run this script again."
    Die "Dependency install did not complete."
}
Ok "requirements.txt installed"

Step "Backend: checking PyTorch actually loads"
# An install can succeed while the import still fails, most often because
# Windows Smart App Control blocks PyTorch's unsigned DLLs. Catching it here
# turns one clear message into what would otherwise be a wall of test failures.
if ((Native $venvPy @("-c","import torch") -Quiet) -ne 0) {
    Write-Host "  !!  PyTorch installed, but will not load on this machine." -ForegroundColor Red
    Note ""
    Note "See the real error with:"
    Write-Host "        backend\.venv\Scripts\python.exe -c ""import torch""" -ForegroundColor Yellow
    Note ""
    Note "If it says 'An Application Control policy has blocked this file'"
    Note "(WinError 4551), Windows Smart App Control is blocking PyTorch's"
    Note "unsigned DLLs. Turn it off in Windows Security > App & browser"
    Note "control > Smart App Control > Off. It has no exclusion list, and it"
    Note "is not intended for development machines. Turning it off is"
    Note "permanent: Windows will not re-enable it without resetting the PC."
    Die "Cannot continue until PyTorch loads."
}
Ok "PyTorch loads"

Step "Backend: demo database"
Push-Location (Join-Path $root "backend")
$code = Native $venvPy @("seed.py") -Quiet
Pop-Location
if ($code -ne 0) { Die "Seeding failed." }
Ok "3 demo patients seeded"

Step "Backend: vector index (downloads a ~130 MB embedding model once)"
Push-Location (Join-Path $root "backend")
$code = Native $venvPy @("-m","rag.index") -Quiet
Pop-Location
if ($code -ne 0) { Die "Building the vector index failed." }
Ok "data\index.npz built"

Step "Frontend: npm install"
Push-Location (Join-Path $root "frontend")
$code = Native "npm" @("install","--silent") -Quiet
Pop-Location
if ($code -ne 0) { Die "npm install failed." }
Ok "node_modules installed"

Write-Host @"

Setup complete. Start the two servers in separate terminals:

  cd backend   ; .venv\Scripts\python.exe -m uvicorn main:app --port 8000
  cd frontend  ; npm run dev

Then open http://localhost:5173

Demo logins - password 'demo123456' for all three:
  rajesh@example.com   48M, hypertension + diabetes, penicillin allergy
  priya@example.com    29F, GERD, NSAID allergy
  arjun@example.com    35M, vegan, smoker, self-medicating

"@ -ForegroundColor Green
