#!/usr/bin/env python3
"""Generate an SSD1619 dashboard from local Codex and GitHub CLI accounts."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
BLACK, WHITE, RED = (0, 0, 0), (255, 255, 255), (190, 0, 25)
QUERY = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
 user(login:$login) { login contributionsCollection(from:$from,to:$to) {
  contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
  commitContributionsByRepository(maxRepositories: 3) { repository { nameWithOwner } contributions { totalCount } }
 } } }
'''


def executable(name):
    # The npm Windows launcher is a .cmd file; Python must invoke it via cmd.exe.
    path = shutil.which(name + '.cmd') if os.name == 'nt' else None
    path = path or shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} 未安装或不在 PATH 中')
    return [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', path] if path.lower().endswith('.cmd') else [path]


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
        send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'epaper_dashboard', 'title': 'E-paper Dashboard', 'version': '1.0'}}})
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


def github_data(username=''):
    gh = executable('gh')
    if not username:
        p = subprocess.run(gh + ['api', 'user', '--jq', '.login'], capture_output=True, text=True, encoding='utf-8', timeout=20, check=True)
        username = p.stdout.strip()
    today = dt.datetime.now(dt.timezone.utc)
    start = today - dt.timedelta(days=364)
    p = subprocess.run(gh + ['api', 'graphql', '-f', 'query='+QUERY, '-f', 'login='+username,
                             '-f', 'from='+start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                             '-f', 'to='+today.strftime('%Y-%m-%dT%H:%M:%SZ')],
                       capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    payload = json.loads(p.stdout)
    if payload.get('errors') or not payload.get('data', {}).get('user'):
        raise RuntimeError('GitHub 查询失败：用户不存在或无权限')
    user = payload['data']['user']
    return {'login': user['login'], **user['contributionsCollection']}


def font(size, bold=False):
    paths = ([r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf'] if bold else [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simsun.ttc'])
    paths += ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def compact(n):
    if n is None: return '--'
    if n >= 100_000_000: return f'{n/100_000_000:.1f}亿'
    if n >= 10_000: return f'{n/10_000:.1f}万'
    return str(n)


def fit(draw, text, face, max_width):
    if draw.textlength(text, font=face) <= max_width: return text
    while text and draw.textlength(text + '…', font=face) > max_width:
        text = text[:-1]
    return text + '…'


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


def render(codex, github, cfg, errors):
    im = Image.new('RGB', (400, 300), WHITE)
    d = ImageDraw.Draw(im)
    red = RED if cfg.get('color_mode') == 'bwr' else BLACK
    f10, f11, f12, f13, f16, f19, f30 = (font(n, n >= 13) for n in (10, 11, 12, 13, 16, 19, 30))
    for name, x in [('openai', 12), ('github', 208)]:
        with Image.open(ROOT / 'assets' / (name + '.png')) as icon:
            im.paste(icon, (x, 8), icon)
    d.line((198, 8, 198, 281), fill=BLACK, width=1)
    d.text((42, 7), 'Codex', font=f19, fill=BLACK)
    d.text((238, 7), 'GitHub', font=f19, fill=BLACK)
    limits = codex.get('limits', {}) if codex else {}
    for key, y, fallback in [('primary', 41, '短期限额'), ('secondary', 145, '每周限额')]:
        w = limits.get(key) or {}
        used = w.get('usedPercent')
        remaining = max(0, min(100, 100 - used)) if isinstance(used, (int, float)) else None
        mins = w.get('windowDurationMins')
        label = ('每周剩余' if mins == 10080 else f'{mins // 1440}天剩余' if mins and mins >= 1440 and mins % 1440 == 0 else f'{mins // 60}小时剩余' if mins and mins >= 60 and mins % 60 == 0 else f'{mins}分钟剩余' if mins else fallback)
        d.text((11, y), f'{remaining:g}%' if remaining is not None else '--%', font=f30, fill=red)
        d.text((12, y+37), label, font=f13, fill=BLACK)
        draw_progress(im, (12, y+57, 181, y+71), remaining, red)
        reset = w.get('resetsAt')
        stamp = dt.datetime.fromtimestamp(reset).strftime('%m-%d %H:%M') if isinstance(reset, (int, float)) else '--'
        d.text((12, y+74), '重置 ' + stamp, font=f11, fill=BLACK)
    usage = codex.get('usage', {}) if codex else {}
    lifetime = (usage.get('summary') or {}).get('lifetimeTokens')
    buckets = usage.get('dailyUsageBuckets')
    today = dt.date.today()
    values = [b.get('tokens') for b in buckets or [] if (today-dt.timedelta(days=6)).isoformat() <= str(b.get('startDate', ''))[:10] <= today.isoformat() and isinstance(b.get('tokens'), (int, float))]
    recent = sum(values) if buckets is not None else None
    d.line((99, 247, 99, 279), fill=BLACK)
    d.text((11, 244), '累计 Token', font=f11, fill=BLACK)
    d.text((105, 244), '近7日 Token', font=f11, fill=BLACK)
    d.text((11, 258), compact(lifetime), font=f19, fill=BLACK)
    d.text((105, 258), compact(recent), font=f19, fill=BLACK)
    if github:
        cal = github.get('contributionCalendar') or {}
        d.text((209, 43), f"{cal.get('totalContributions', 0)} 次贡献 · 近一年", font=f11, fill=BLACK)
        weeks = cal.get('weeks') or []
        # Like the reference, show larger cells for the most recent 15 weeks.
        for x, week in enumerate(weeks[-15:]):
            for day in week.get('contributionDays', []):
                try: row = (dt.date.fromisoformat(day['date']).weekday()+1) % 7
                except (ValueError, KeyError): continue
                count = day.get('contributionCount', 0)
                x0, y0 = 209+x*12, 61+row*10
                d.rounded_rectangle((x0, y0, x0+9, y0+8), radius=1, outline=BLACK, fill=BLACK if count else WHITE)
        d.text((209, 145), '贡献活动', font=f13, fill=BLACK)
        repos = github.get('commitContributionsByRepository') or []
        if not repos: d.text((209, 169), '暂无仓库贡献', font=f12, fill=BLACK)
        maximum = max((r['contributions']['totalCount'] for r in repos), default=1) or 1
        for i, repo in enumerate(repos[:3]):
            y = 169 + i*37
            name = repo['repository']['nameWithOwner'].split('/')[-1]
            count = repo['contributions']['totalCount']
            d.text((209, y), fit(d, name, f11, 178), font=f11, fill=BLACK)
            d.text((209, y+15), f'{count} commits', font=f10, fill=BLACK)
            length = int(90 * count / maximum)
            if length: d.rounded_rectangle((389-length, y+19, 389, y+25), radius=2, fill=red if i == 0 else BLACK)
    else:
        d.text((209, 55), 'GitHub 数据不可用', font=f12, fill=BLACK)
    d.line((8, 282, 391, 282), fill=BLACK)
    footer = ('数据不完整  ' if errors else '') + '更新 ' + dt.datetime.now().strftime('%m-%d %H:%M') + '    贡献格：近15周'
    d.text((9, 285), footer, font=f10, fill=BLACK)
    return im


def run_once(cfg):
    data, errors = {}, []
    for name, fn in [('Codex', codex_data), ('GitHub', lambda: github_data(cfg.get('github_username', '')))]:
        try:
            data[name] = fn()
            print(name + ' 数据读取成功')
        except Exception as e:
            errors.append(name)
            print(f'{name} 数据读取失败：{e}', file=sys.stderr)
            data[name] = None
    path = Path(cfg.get('output_path', 'output/dashboard.png'))
    if not path.is_absolute(): path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    render(data['Codex'], data['GitHub'], cfg, errors).save(path)
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
    try: sys.exit(main())
    except KeyboardInterrupt: print('\n已停止')
