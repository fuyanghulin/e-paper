#!/usr/bin/env python3
"""Generate an SSD1619 dashboard from local Codex and GitHub CLI accounts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw

from components import COMPONENTS
from components.common import BLACK, WHITE, font

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
# Sizes are pixel dimensions of the content area (the footer occupies 18 px).
COMPONENT_SIZES = {'full': (400, 282), 'half': (200, 282), 'quarter': (200, 141)}
COMPONENT_SIZE_LABELS = {'full': '满屏', 'half': '左右半屏', 'quarter': '四分之一屏'}
DEFAULT_COMPONENTS = ['codex', 'github']


def layout_components(cfg):
    names = cfg.get('components', DEFAULT_COMPONENTS)
    if not isinstance(names, list) or not names:
        raise ValueError('请至少选择一个组件')
    if any(not isinstance(name, str) or name not in COMPONENTS for name in names):
        raise ValueError('components 包含未知组件')
    if len(names) != len(set(names)):
        raise ValueError('不能重复选择组件')
    explicit = cfg.get('component_layout')
    if explicit is not None:
        if not isinstance(explicit, list) or len(explicit) != len(names):
            raise ValueError('布局与所选组件不一致')
        placements, occupied = [], set()
        for entry in explicit:
            if not isinstance(entry, dict):
                raise ValueError('组件位置格式无效')
            name, x, y = entry.get('id'), entry.get('x'), entry.get('y')
            if name not in names or any(item[0] == name for item in placements):
                raise ValueError('布局中的组件与所选组件不一致')
            if type(x) is not int or type(y) is not int or x not in (0, 200) or y not in (0, 141):
                raise ValueError('组件位置必须对齐屏幕网格')
            width, height = COMPONENT_SIZES[COMPONENTS[name]['size']]
            if x + width > 400 or y + height > 282:
                raise ValueError('组件超出屏幕范围')
            cells = {(col, row) for col in range(x // 200, (x + width) // 200)
                     for row in range(y // 141, (y + height) // 141)}
            if occupied & cells:
                raise ValueError('组件位置重叠')
            occupied.update(cells)
            placements.append((name, x, y))
        return placements
    grid = [[None, None], [None, None]]

    def place(index):
        if index == len(names):
            return []
        name = names[index]
        size = COMPONENTS[name]['size']
        if size not in COMPONENT_SIZES:
            raise ValueError(f'组件 {name} 的尺寸无效')
        cols, rows = {'full': (2, 2), 'half': (1, 2), 'quarter': (1, 1)}[size]
        for y in range(3 - rows):
            for x in range(3 - cols):
                cells = [(xx, yy) for yy in range(y, y + rows) for xx in range(x, x + cols)]
                if any(grid[yy][xx] is not None for xx, yy in cells):
                    continue
                for xx, yy in cells: grid[yy][xx] = name
                rest = place(index + 1)
                if rest is not None:
                    return [(name, x * 200, y * 141)] + rest
                for xx, yy in cells: grid[yy][xx] = None
        return None

    result = place(0)
    if result is None:
        raise ValueError('所选组件无法放入一个屏幕，请减少组件')
    return result


def render(data, cfg, errors):
    layout = layout_components(cfg)
    im = Image.new('RGB', (400, 300), WHITE)
    for name, x, y in layout:
        component = COMPONENTS[name]
        image = component['draw'](data.get(name), cfg)
        if image.size != COMPONENT_SIZES[component['size']]:
            raise ValueError(f"组件 {component['label']} 返回了错误的图片尺寸：{image.size}")
        im.paste(image, (x, y))
    d = ImageDraw.Draw(im)
    # Draw only boundaries between occupied components, never through a larger component.
    cells = [[None, None], [None, None]]
    for name, x, y in layout:
        w, h = COMPONENT_SIZES[COMPONENTS[name]['size']]
        for row in range(y // 141, (y + h) // 141):
            for col in range(x // 200, (x + w) // 200):
                cells[row][col] = name
    for row in range(2):
        if cells[row][0] and cells[row][1] and cells[row][0] != cells[row][1]:
            d.line((198, max(8, row * 141), 198, min(281, (row + 1) * 141)), fill=BLACK)
    for col in range(2):
        if cells[0][col] and cells[1][col] and cells[0][col] != cells[1][col]:
            d.line((col * 200 + 8, 140, col * 200 + 191, 140), fill=BLACK)
    d.line((8, 282, 391, 282), fill=BLACK)
    footer = ('数据不完整  ' if errors else '') + '更新 ' + dt.datetime.now().strftime('%m-%d %H:%M')
    if any(name == 'github' for name, _, _ in layout):
        footer += '    贡献格：近15周'
    d.text((9, 285), footer, font=font(10), fill=BLACK)
    return im


def run_once(cfg):
    layout = layout_components(cfg)
    data, errors = {}, []
    for name, _, _ in layout:
        component = COMPONENTS[name]
        try:
            data[name] = component['fetch'](cfg)
            print(component['label'] + ' 数据读取成功')
        except Exception as e:
            errors.append(name)
            print(f"{component['label']} 数据读取失败：{e}", file=sys.stderr)
            data[name] = None
    path = Path(cfg.get('output_path', 'output/dashboard.png'))
    if not path.is_absolute(): path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    render(data, cfg, errors).save(path)
    print(f'图片已生成：{path}')
    return not errors


def main():
    parser = argparse.ArgumentParser(description='生成 400×300 墨水屏仪表盘')
    parser.add_argument('--watch', action='store_true', help='按配置间隔循环生成')
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding='utf-8'))
    if (cfg.get('width'), cfg.get('height')) != (400, 300):
        parser.error('当前画面布局只支持 400×300')
    if cfg.get('color_mode') not in ('bw', 'bwr'):
        parser.error('color_mode 必须是 bw 或 bwr')
    while True:
        ok = run_once(cfg)
        if not args.watch: return 0 if ok else 1
        delay = max(1, float(cfg.get('refresh_minutes', 30))) * 60
        print(f'{int(delay / 60)} 分钟后更新，按 Ctrl+C 停止。', flush=True)
        time.sleep(delay)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n已停止')
