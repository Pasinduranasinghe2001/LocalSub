"""Generates assets/icon.ico (run automatically by build.ps1)."""
import os

from PIL import Image, ImageDraw, ImageFont

os.makedirs("assets", exist_ok=True)
S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(37, 99, 235))
# "screen"
d.rounded_rectangle((80, 110, S - 80, 330), radius=36, fill=(255, 255, 255))
d.polygon([(220, 160), (220, 280), (320, 220)], fill=(37, 99, 235))
# subtitle bars
d.rounded_rectangle((90, 370, S - 90, 400), radius=15, fill=(255, 255, 255))
d.rounded_rectangle((150, 420, S - 150, 450), radius=15, fill=(191, 219, 254))
img.save("assets/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save("assets/icon.png")
print("icon created")
