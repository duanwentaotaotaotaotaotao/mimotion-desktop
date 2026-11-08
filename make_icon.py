from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

base = Path(__file__).parent / "assets"
base.mkdir(exist_ok=True)
image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((4, 4, 252, 252), radius=58, fill="#193D32")
draw.rounded_rectangle((41, 41, 215, 215), radius=40, fill="#C3EE8E")
font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 152)
draw.text((128, 110), "m", font=font, anchor="mm", fill="#193D32", stroke_width=1)
image.save(base / "mimotion.png")
image.save(base / "mimotion.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
