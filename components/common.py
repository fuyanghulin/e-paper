"""Shared drawing and command helpers for dashboard components."""
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BLACK, WHITE, RED = (0, 0, 0), (255, 255, 255), (190, 0, 25)
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def executable(name):
    # The npm Windows launcher is a .cmd file; Python must invoke it via cmd.exe.
    path = shutil.which(name + '.cmd') if os.name == 'nt' else None
    path = path or shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} 未安装或不在 PATH 中')
    return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', path] if path.lower().endswith('.cmd') else [path]


@lru_cache(maxsize=None)
def font(size, bold=False):
    paths = (
        [r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf'] if bold else [r'C:\Windows\Fonts\msyh.ttc',
                                                                                       r'C:\Windows\Fonts\simsun.ttc'])
    paths += ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def component_canvas(cfg, icon_name, title, icon_x, title_x):
    im = Image.new('RGB', (400, 282), WHITE)
    d = ImageDraw.Draw(im)
    red = RED if cfg.get('color_mode') == 'bwr' else BLACK
    fonts = tuple(font(n, n >= 13) for n in (10, 11, 12, 13, 16, 19, 30))
    with Image.open(ROOT / 'assets' / (icon_name + '.png')) as icon:
        im.paste(icon, (icon_x, 8), icon)
    d.text((title_x, 7), title, font=fonts[5], fill=BLACK)
    return im, d, red, fonts
