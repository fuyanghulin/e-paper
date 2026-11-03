"""GitHub contributions, displayed in a half-screen slot."""
import datetime as dt
import json
import subprocess

from .common import BLACK, WHITE, component_canvas, executable

QUERY = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
 user(login:$login) { login contributionsCollection(from:$from,to:$to) {
  contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
  commitContributionsByRepository(maxRepositories: 3) { repository { nameWithOwner } contributions { totalCount } }
 } } }
'''


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


def fit(draw, text, face, max_width):
    if draw.textlength(text, font=face) <= max_width: return text
    while text and draw.textlength(text + '…', font=face) > max_width:
        text = text[:-1]
    return text + '…'


def draw_github(github, cfg):
    im, d, red, fonts = component_canvas(cfg, 'github', 'GitHub', 208, 238)
    f10, f11, f12, f13, f16, f19, f30 = fonts
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
    return im.crop((200, 0, 400, 282))


def fetch(cfg):
    return github_data(cfg.get('github_username', ''))


def preview_data():
    start = dt.date.today() - dt.timedelta(days=104)
    weeks = [{'contributionDays': [{'date': (start + dt.timedelta(days=week * 7 + day)).isoformat(),
                                    'contributionCount': int((week * 3 + day * 5) % 7 < 3)}
                                   for day in range(7)]} for week in range(15)]
    repos = [{'repository': {'nameWithOwner': 'example/' + name},
              'contributions': {'totalCount': count}}
             for name, count in [('project-a', 36), ('project-b', 21), ('project-c', 12)]]
    return {'contributionCalendar': {'totalContributions': 128, 'weeks': weeks},
            'commitContributionsByRepository': repos}


COMPONENT = {'preview_data': preview_data, 'id': 'github', 'label': 'GitHub', 'size': 'half', 'fetch': fetch, 'draw': draw_github}
