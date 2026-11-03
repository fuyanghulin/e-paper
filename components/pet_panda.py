"""Static quarter-screen cartoon panda."""
from .pet_common import draw_pet


def fetch(cfg):
    return None


def draw(data, cfg):
    return draw_pet('pet_panda.png')


COMPONENT = {'id': 'pet_panda', 'label': '卡通熊猫', 'size': 'quarter', 'fetch': fetch, 'draw': draw}
