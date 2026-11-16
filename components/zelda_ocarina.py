"""Official Ocarina of Time logo for a quarter-screen tile."""
from functools import lru_cache

from PIL import Image, ImageEnhance

from .common import ROOT


def fetch(cfg):
    return None


@lru_cache(maxsize=1)
def _image():
    with Image.open(ROOT / 'assets' / 'zelda_ocarina.png') as source:
        image = source.convert('RGBA')
        image.thumbnail((184, 129), Image.Resampling.LANCZOS)
        # Darken the gold lettering so it remains legible on a monochrome display.
        alpha = image.getchannel('A')
        image = ImageEnhance.Brightness(image.convert('RGB')).enhance(0.65).convert('RGBA')
        image.putalpha(alpha)
        canvas = Image.new('RGBA', (200, 141), 'white')
        canvas.alpha_composite(image, ((200 - image.width) // 2, (141 - image.height) // 2))
        return canvas.convert('L').convert('1', dither=Image.Dither.FLOYDSTEINBERG).convert('RGB')


def draw(data, cfg):
    return _image().copy()


COMPONENT = {'id': 'zelda_ocarina', 'label': '塞尔达 时之笛 Logo', 'size': 'quarter',
             'fetch': fetch, 'draw': draw}
