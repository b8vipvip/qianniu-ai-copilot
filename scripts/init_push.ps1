param(
  [string]$RepoUrl = "https://github.com/b8vipvip/qianniu-ai-copilot.git"
)
$ErrorActionPreference = "Stop"
git init
if (-not (git remote | Select-String '^origin$')) { git remote add origin $RepoUrl }
git add .
git commit -m "init qianniu ai copilot mvp"
git branch -M main
git push -u origin main
