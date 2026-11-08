from pathlib import Path
from PIL import Image

base = Path(__file__).parent / "assets"
base.mkdir(exist_ok=True)
# The original alpha PNG is generated with the built-in image_gen tool.
# This script only writes the Windows icon container; it does not redraw it.
image = Image.open(base / "mimotion.png").convert("RGBA")
image.save(base / "mimotion.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
