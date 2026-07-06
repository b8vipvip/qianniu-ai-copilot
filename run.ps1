$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if (!(Test-Path ".venv")) {
  py -m venv .venv
}
. .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
$env:PYTHONPATH = "$root\src"
python -m qianniu_ai_copilot.main
