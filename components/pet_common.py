"""Helpers for rendering static pet illustrations on e-paper."""
from PIL import Image, ImageChops, ImageOps

from .common import ROOT, WHITE


def draw_pet(asset_name):
    with Image.open(ROOT / 'assets' / asset_name) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
        # Ignore near-white background when framing the character.
        difference = ImageChops.difference(image, Image.new('RGB', image.size, WHITE))
        mask = difference.convert('L').point(lambda value: 255 if value > 24 else 0)
        bounds = mask.getbbox()
        if bounds:
            image = image.crop(bounds)
        image.thumbnail((176, 129), Image.Resampling.LANCZOS)
        # The device has no gray or orange ink. Dither to its black/white palette.
        image = image.convert('L').convert('1', dither=Image.Dither.FLOYDSTEINBERG).convert('RGB')
    canvas = Image.new('RGB', (200, 141), WHITE)
    canvas.paste(image, ((200 - image.width) // 2, (141 - image.height) // 2))
    return canvas
