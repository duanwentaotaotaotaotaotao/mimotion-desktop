$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$buildRoot = Join-Path $PSScriptRoot '.build'
$buildTemp = Join-Path $buildRoot 'tmp'
New-Item -ItemType Directory -Path $buildTemp -Force | Out-Null
$env:TEMP = $buildTemp
$env:TMP = $buildTemp
$env:PYINSTALLER_CONFIG_DIR = Join-Path $buildRoot 'cache'
$buildPython = Join-Path $buildRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    python -m venv (Join-Path $buildRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create build venv.' }
}
& $buildPython -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Unable to install dependencies.' }
& $buildPython collect_licenses.py
& $buildPython make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon conversion failed.' }
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sport_host_src\build-host.ps1')
if ($LASTEXITCODE -ne 0) { throw 'WebView2 host build failed.' }
& $buildPython -m unittest discover -s . -p test_backend.py -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name move --icon (Join-Path $PSScriptRoot 'assets\mimotion.ico') --collect-all customtkinter --add-data ((Join-Path $PSScriptRoot 'assets')+';assets') --add-data ((Join-Path $PSScriptRoot 'LICENSE-mimotion.txt')+';.') --add-data ((Join-Path $PSScriptRoot 'NOTICE.txt')+';.') --distpath dist --workpath (Join-Path $buildRoot 'pyinstaller') --specpath $buildRoot (Join-Path $PSScriptRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Output (Join-Path $PSScriptRoot 'dist\move.exe')
