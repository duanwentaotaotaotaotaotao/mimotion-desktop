# MiMotion WebView2 host

The host embeds the live original `https://sport.gyvv.top/` website as a top-level WebView2 document. It does not copy or alter the website's source, origin, API, map keys or attribution.

Build on Windows with .NET Framework 4.8 and the bundled WebView2 assemblies:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-host.ps1
```

To refresh the WebView2 SDK inputs, download Microsoft's official `Microsoft.Web.WebView2` NuGet package, extract it, and pass `-SdkDirectory <extracted-package>`.

Required binaries are emitted to `../assets/sport_host/`: `MiMotion.SportHost.exe`, its `.config`, `Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`, `WebView2Loader.dll`, and the SDK license. The SDK version supplied for this build is 1.0.4314.35. The separately installed Evergreen WebView2 runtime is used.

CLI contract:

```text
MiMotion.SportHost.exe --parent <decimal HWND> --project <absolute directory> --status-file <absolute JSON path> --quit-file <per-instance quit path>
```

Omit `--parent` for a standalone window. The embedded host is a real native child, follows the parent size and visibility, and closes if its parent is destroyed or the quit file appears. The status report includes its HWND, loading/ready/error state, a query-free source URL and download names/states. There is no JavaScript/native object bridge and no desktop account data is supplied to the website.

`--export-dir` optionally overrides the default `<project>/轨迹导出`. The toolbar lets the user choose and remember a different directory. Downloads are saved under safe unique basenames and never automatically opened. Website drawing state uses the isolated `<project>/.mimotion-desktop/sport-web-profile` browser profile.

`--self-test <report.json>` uses a local virtual-host page to check JavaScript, persistent local storage and a generated Blob CSV download, then exits. It makes no website API submissions. `--inspect-report <report.json>` keeps the normal website open and captures only public UI readiness after ten seconds: title, readyState, Leaflet/map/tile presence, and a short body-text excerpt; no cookies, credentials or storage are captured. It also captures only the webpage surface to a sibling `.png` using WebView2's native capture API, without requiring the user's foreground or photographing other desktop windows.
