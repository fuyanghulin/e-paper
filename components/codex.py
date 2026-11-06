"""Codex rate limits and token usage, displayed in a half-screen slot."""
import datetime as dt
import json
import queue
import subprocess
import sys
import threading
import time

from PIL import Image, ImageDraw

from .common import BLACK, component_canvas, executable, font


def codex_data():
    proc = subprocess.Popen(executable('codex') + ['app-server'], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding='utf-8', errors='replace', bufsize=1)
    lines = queue.Queue()

    def read_lines():
        for line in proc.stdout:
            lines.put(line)

    threading.Thread(target=read_lines, daemon=True).start()

    def send(message):
        proc.stdin.write(json.dumps(message, ensure_ascii=False) + '\n')
        proc.stdin.flush()

    def receive(request_id, timeout=25):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Codex app-server 响应超时')
            try:
                obj = json.loads(lines.get(timeout=remaining))
            except queue.Empty:
                raise TimeoutError('Codex app-server 响应超时') from None
            if obj.get('id') == request_id:
                if 'error' in obj:
                    raise RuntimeError(obj['error'].get('message', 'Codex 请求失败'))
                return obj.get('result', {})

    try:
        send({'id': 1, 'method': 'initialize',
              'params': {'clientInfo': {'name': 'epaper_dashboard', 'title': 'E-paper Dashboard', 'version': '1.0'}}})
        receive(1)
        send({'method': 'initialized', 'params': {}})
        send({'id': 2, 'method': 'account/rateLimits/read'})
        limits = receive(2).get('rateLimits') or {}
        try:
            send({'id': 3, 'method': 'account/usage/read'})
            usage = receive(3)
        except (RuntimeError, TimeoutError) as e:
            print(f'Codex Token 数据不可用：{e}', file=sys.stderr)
            usage = {}
        return {'limits': limits, 'usage': usage}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def compact(n):
    if n is None: return '--'
    if n >= 100_000_000: return f'{n / 100_000_000:.1f}亿'
    if n >= 10_000: return f'{n / 10_000:.1f}万'
    return str(n)


def draw_progress(im, bounds, remaining, fill):
    """Clip the fill to the same rounded outline so its left edge fits exactly."""
    x0, y0, x1, y1 = bounds
    if remaining is not None and remaining > 0:
        mask = Image.new('1', im.size, 0)
        shape = ImageDraw.Draw(mask)
        shape.rounded_rectangle(bounds, radius=7, fill=1)
        width = max(1, round((x1 - x0 + 1) * remaining / 100))
        cutoff = min(x1, x0 + width - 1)
        if cutoff < x1:
            shape.rectangle((cutoff + 1, y0, x1, y1), fill=0)
        im.paste(fill, (0, 0, im.width, im.height), mask)
    ImageDraw.Draw(im).rounded_rectangle(bounds, radius=7, outline=BLACK, width=1)


def draw_codex(codex, cfg):
    im, d, red, fonts = component_canvas(cfg, 'openai', 'Codex', 12, 42)
    f10, f11, f12, f13, f16, f19, f30 = fonts
    limits = codex.get('limits', {}) if codex else {}
    for key, y, fallback in [('primary', 41, '短期限额'), ('secondary', 135, '每周限额')]:
        w = limits.get(key) or {}
        used = w.get('usedPercent')
        remaining = max(0, min(100, 100 - used)) if isinstance(used, (int, float)) else None
        mins = w.get('windowDurationMins')
        label = (
            '每周剩余' if mins == 10080 else f'{mins // 1440}天剩余' if mins and mins >= 1440 and mins % 1440 == 0 else f'{mins // 60}小时剩余' if mins and mins >= 60 and mins % 60 == 0 else f'{mins}分钟剩余' if mins else fallback)
        d.text((11, y), f'{remaining:g}%' if remaining is not None else '--%', font=f30, fill=red)
        reset = w.get('resetsAt')
        stamp = dt.datetime.fromtimestamp(reset).strftime('%m-%d %H:%M') if isinstance(reset, (int, float)) else '--'
        detail = f'{label}  重置 {stamp}'
        detail_font = f13
        for size in (12, 11, 10):
            if d.textlength(detail, font=detail_font) <= 176:
                break
            detail_font = font(size, bold=True)
        d.text((12, y + 37), detail, font=detail_font, fill=BLACK)
        draw_progress(im, (12, y + 57, 181, y + 71), remaining, red)
    usage = codex.get('usage', {}) if codex else {}
    lifetime = (usage.get('summary') or {}).get('lifetimeTokens')
    buckets = usage.get('dailyUsageBuckets')
    today = dt.date.today()
    values = [b.get('tokens') for b in buckets or [] if
              (today - dt.timedelta(days=6)).isoformat() <= str(b.get('startDate', ''))[
                  :10] <= today.isoformat() and isinstance(b.get('tokens'), (int, float))]
    recent = sum(values) if buckets is not None else None
    d.text((11, 229), '累计 Token', font=f13, fill=BLACK)
    d.text((105, 229), '近7日 Token', font=f13, fill=BLACK)
    left_edge = 11 + d.textlength('累计 Token', font=f13)
    for x, value, width in ((11, lifetime, 84), (105, recent, 84)):
        text = compact(value)
        value_font = font(22, bold=True)
        for size in range(21, 9, -1):
            if d.textlength(text, font=value_font) <= width:
                break
            value_font = font(size, bold=True)
        d.text((x, 251), text, font=value_font, fill=BLACK)
        if x == 11:
            left_edge = max(left_edge, x + d.textlength(text, font=value_font))
    divider_x = round((left_edge + 105) / 2)
    d.line((divider_x, 232, divider_x, 279), fill=BLACK)
    return im.crop((0, 0, 200, 282))


def fetch(cfg):
    return codex_data()


def preview_data():
    return {'limits': {'primary': {'usedPercent': 35, 'windowDurationMins': 300},
                       'secondary': {'usedPercent': 20, 'windowDurationMins': 10080}},
            'usage': {'summary': {'lifetimeTokens': 1200000}, 'dailyUsageBuckets': []}}


COMPONENT = {'preview_data': preview_data, 'id': 'codex', 'label': 'Codex', 'size': 'half', 'fetch': fetch,
             'draw': draw_codex}
