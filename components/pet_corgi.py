"""Static quarter-screen corgi based on the supplied reference."""
from .pet_common import draw_pet


def fetch(cfg):
    return None


def draw(data, cfg):
    return draw_pet('pet_corgi.png')


COMPONENT = {'id': 'pet_corgi', 'label': '卡通柯基', 'size': 'quarter', 'fetch': fetch, 'draw': draw}
