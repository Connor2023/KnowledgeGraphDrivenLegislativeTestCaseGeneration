# Create the virtual environments this project needs, from pinned requirements.
#
#     .\bootstrap.ps1                 # the pipeline only -- enough to build a graph
#     .\bootstrap.ps1 -All            # plus the evaluation and EDC environments
#     .\bootstrap.ps1 -Check          # verify what is already installed, change nothing
#
# Three environments, deliberately separate, because their dependencies conflict:
#
#     .venv-testgen   the pipeline, and the evaluation code that measures it
#     .venv-ontogpt   SPIRES extraction; ontogpt pins linkml and pydantic versions
#                     that the pipeline cannot use
#     .venv-edc       the EDC comparison arm; drags in torch and transformers
#
# Only the first is needed to take a statute to a knowledge graph and generate test
# cases. The other two exist for the comparison arms and for the extraction step.

[CmdletBinding()]
param(
    [switch]$All,        # also build .venv-edc, which pulls ~1 GB of torch
    [switch]$Check,      # report only
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

function Get-VenvPython($venv) {
    $win = Join-Path $root "$venv\Scripts\python.exe"
    if (Test-Path $win) { return $win }
    $nix = Join-Path $root "$venv/bin/python"
    if (Test-Path $nix) { return $nix }
    return $null
}

function Install-Venv($venv, $requirements, $description) {
    Write-Step "$venv  ($description)"
    $py = Get-VenvPython $venv
    if (-not $py) {
        if ($Check) { Write-Warn "not created"; return }
        Write-Host "    creating..."
        & $Python -m venv (Join-Path $root $venv)
        $py = Get-VenvPython $venv
        if (-not $py) { throw "could not create $venv -- is '$Python' on PATH?" }
    }
    if ($Check) {
        $count = (& $py -m pip list --format=freeze 2>$null | Measure-Object -Line).Lines
        Write-Ok "exists, $count package(s)"
        return
    }
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r (Join-Path $root $requirements)
    if ($LASTEXITCODE -ne 0) { throw "pip install failed for $venv" }
    Write-Ok "installed from $requirements"
}

# --- the pipeline ------------------------------------------------------------------
Install-Venv ".venv-testgen" "requirements/evaluation.txt" `
    "pipeline + the code that measures it"

# --- SPIRES extraction --------------------------------------------------------------
Install-Venv ".venv-ontogpt" "requirements/ontogpt.txt" "SPIRES extraction"

# The ontogpt console script has no hook to call truststore, so TLS interception has to
# be handled at interpreter startup. This file used to exist only inside the venv, which
# is gitignored -- so a fresh checkout lost it, and the failure is a
# CERTIFICATE_VERIFY_FAILED on every call with nothing to say why.
$ontogptPy = Get-VenvPython ".venv-ontogpt"
if ($ontogptPy -and -not $Check) {
    $sitePackages = & $ontogptPy -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"
    if ($sitePackages -and (Test-Path $sitePackages)) {
        Copy-Item (Join-Path $root "sitecustomize.py") `
                  (Join-Path $sitePackages "sitecustomize.py") -Force
        Write-Ok "installed sitecustomize.py (TLS via the OS certificate store)"
    }
}

# --- the EDC comparison arm ---------------------------------------------------------
if ($All) {
    Install-Venv ".venv-edc" "requirements/edc.txt" "EDC arm -- pulls ~1 GB of torch"
} else {
    Write-Step ".venv-edc  (EDC comparison arm)"
    Write-Warn "skipped -- pass -All to build it. Only the 'kg' and 'kg-text-only' arms need it."
}

# --- verify -------------------------------------------------------------------------
Write-Step "verifying"
$py = Get-VenvPython ".venv-testgen"
if ($py) {
    & $py (Join-Path $root "check_environment.py")
    if ($LASTEXITCODE -ne 0) { throw "the pipeline environment is incomplete" }
}

Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  . .\setup_env.ps1                      # load credentials into this shell"
Write-Host "  python check_key.py                    # confirm the LLM key, without printing it"
Write-Host "  python build_corpus.py --dry-run       # every free stage and gate"
Write-Host "  python tests\run_all.py -q             # 57 checks, no API calls"
