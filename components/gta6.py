"""Official GTA VI logo for a quarter-screen tile."""
from functools import lru_cache

from PIL import Image

from .common import ROOT


def fetch(cfg):
    return None


@lru_cache(maxsize=1)
def _image():
    with Image.open(ROOT / 'assets' / 'gta6.png') as source:
        image = source.convert('RGBA')
        image = image.crop(image.getchannel('A').getbbox())
        image.thumbnail((184, 129), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (200, 141), 'white')
        canvas.alpha_composite(image, ((200 - image.width) // 2, (141 - image.height) // 2))
        return canvas.convert('L').convert('1', dither=Image.Dither.FLOYDSTEINBERG).convert('RGB')


def draw(data, cfg):
    return _image().copy()


COMPONENT = {'id': 'gta6', 'label': 'GTA 6 Logo', 'size': 'quarter', 'fetch': fetch, 'draw': draw}
