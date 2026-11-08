param([string]$SdkDirectory = '')
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$output = Join-Path $appRoot 'assets\sport_host'
New-Item -ItemType Directory -Path $output -Force | Out-Null
if ($SdkDirectory) {
    $sdk = (Resolve-Path -LiteralPath $SdkDirectory).Path
    Copy-Item -LiteralPath (Join-Path $sdk 'lib\net462\Microsoft.Web.WebView2.Core.dll') -Destination $output -Force
    Copy-Item -LiteralPath (Join-Path $sdk 'lib\net462\Microsoft.Web.WebView2.WinForms.dll') -Destination $output -Force
    Copy-Item -LiteralPath (Join-Path $sdk 'runtimes\win-x64\native\WebView2Loader.dll') -Destination $output -Force
    Copy-Item -LiteralPath (Join-Path $sdk 'LICENSE.txt') -Destination (Join-Path $output 'LICENSE-WebView2.txt') -Force
}
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw '.NET Framework compiler not found.' }
$core = Join-Path $output 'Microsoft.Web.WebView2.Core.dll'
$forms = Join-Path $output 'Microsoft.Web.WebView2.WinForms.dll'
$executable = Join-Path $output 'MiMotion.SportHost.exe'
$icon = Join-Path $appRoot 'assets\mimotion.ico'
& $compiler /nologo /target:winexe /platform:x64 /optimize+ /langversion:5 "/out:$executable" "/win32icon:$icon" "/reference:$core" "/reference:$forms" /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Web.Extensions.dll (Join-Path $PSScriptRoot 'SportHost.cs')
if ($LASTEXITCODE -ne 0) { throw 'WebView2 host compilation failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'MiMotion.SportHost.exe.config') -Destination $output -Force
Write-Output $executable
