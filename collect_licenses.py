from importlib import metadata
from pathlib import Path

packages = ["customtkinter", "requests", "pytz", "python-dotenv", "pycryptodome", "pillow",
            "darkdetect", "packaging", "charset-normalizer", "idna", "urllib3", "certifi"]
texts = ["MiMotion Desktop — third-party notices\n"]
for name in packages:
    dist = metadata.distribution(name)
    texts.append("\n" + "=" * 70 + f"\n{name} {dist.version}\n" + "=" * 70 + "\n")
    licenses = [file for file in (dist.files or [])
                if ".dist-info" in str(file) and file.name.lower().startswith(("license", "copying", "notice"))]
    for file in licenses:
        texts.append("\n" + file.name + "\n" + dist.locate_file(file).read_text(encoding="utf-8", errors="replace"))
    if not licenses:
        texts.append(str(dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See project source."))
webview_license = Path(__file__).with_name("assets") / "sport_host" / "LICENSE-WebView2.txt"
if webview_license.is_file():
    texts.append("\n" + "=" * 70 + "\nMicrosoft.Web.WebView2 SDK 1.0.4314.35\n" + "=" * 70 + "\n")
    texts.append(webview_license.read_text(encoding="utf-8-sig"))
Path(__file__).with_name("assets").joinpath("THIRD-PARTY-LICENSES.txt").write_text("\n".join(texts), encoding="utf-8")
