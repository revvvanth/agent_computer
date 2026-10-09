$ErrorActionPreference = 'Stop'
$researchRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $researchRoot 'source_snapshot/manifest.json'))) { throw 'Bundled source snapshot is missing.' }
Push-Location $researchRoot
try {
    $revision = '4773ef6866544a497c2a33ed2475bb4aa1de0475'
    $vendorPath = Join-Path $researchRoot 'vendor/OpenBot'
    if (-not (Test-Path -LiteralPath $vendorPath)) {
        New-Item -ItemType Directory -Force -Path (Join-Path $researchRoot 'vendor') | Out-Null
        git clone --no-checkout https://github.com/CopilotKit/OpenBot.git $vendorPath
        if ($LASTEXITCODE -ne 0) { throw 'OpenBot clone failed.' }
        git -C $vendorPath checkout --detach $revision
        if ($LASTEXITCODE -ne 0) { throw 'Pinned OpenBot checkout failed.' }
    }
    $actualRevision = git -C $vendorPath rev-parse HEAD
    if ($actualRevision -ne $revision) { throw 'OpenBot revision differs from the pinned pilot. Use a separate checkout; do not overwrite local changes.' }
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        py -3.11 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 virtual environment creation failed.' }
    }
    .venv/Scripts/python.exe -m pip install --cache-dir .cache/pip -r requirements.lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Research dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.template' -Destination '.env'
        Write-Host 'Created .env with blank credentials. Configure it before live inference.'
    }
    docker info --format '{{.ServerVersion}}'
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop Linux engine before running setup.' }
    Push-Location $vendorPath
    try {
        docker build --file agent-computer/Dockerfile --tag kareos-research-openbot:4773ef686654 .
        if ($LASTEXITCODE -ne 0) { throw 'OpenBot computer build failed.' }
    } finally { Pop-Location }
    docker build --tag kareos-research-lab:pilot-v1 .
    if ($LASTEXITCODE -ne 0) { throw 'Research image build failed.' }
    .venv/Scripts/python.exe lab.py check
    if ($LASTEXITCODE -ne 0) { throw 'Project integrity check failed.' }
} finally { Pop-Location }
