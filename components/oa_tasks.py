"""OA 我的任务：后台读取及不同尺寸的墨水屏组件。"""
import json
import threading
import time
from pathlib import Path
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageDraw
from .common import BLACK, WHITE, RED, font

ROOT = Path(__file__).resolve().parent.parent
SESSION = ROOT / 'output' / 'oa_session.json'
OA_URL = "https://oa.int.shenzhouintl.com/"
LIST_ID = "1025200520246919169"
FIELDS = ("id", "task_name", "manager", "project", "task_type", "priority", "task_status", "progress", "plan_start_time", "plan_finish_time", "actual_start_time", "actual_finish_time", "update_time")

_fetch_lock = threading.Lock()
_cache = {}
CACHE_TTL = 20  # 只需覆盖同一轮更新，避免多个 OA 组件各自启动浏览器。


def get_tasks(username, password, size):
    """登录并读取所有分页，返回适合其他 Python 程序调用的列表。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            context = browser.new_context(storage_state=str(SESSION) if SESSION.exists() else None)
            page = context.new_page()
            page.set_default_timeout(90000)
            page.goto(OA_URL, wait_until="domcontentloaded", timeout=90000)
            login = page.get_by_placeholder("请输入用户名/手机号/邮箱")
            menu = page.get_by_text("项目管理", exact=True).first
            deadline = time.monotonic() + 90
            while not menu.is_visible():
                if login.is_visible():
                    login.fill(username)
                    page.get_by_placeholder("请输入密码").fill(password)
                    page.get_by_text("立即登录", exact=True).click()
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("OA 页面加载超时，未出现登录框或主菜单")
                page.wait_for_timeout(500)
            menu.wait_for()
            SESSION.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(SESSION))
            menu.click()
            page.get_by_text("任务管理", exact=True).first.wait_for()
            page.get_by_text("任务管理", exact=True).first.click()
            page.get_by_text("我的任务", exact=True).first.wait_for()
            # 新版页面把列表 ID 放在页面 URL 中，请求体内只有视图 listId，两者都兼容。
            with page.expect_response(lambda r: "getListDatas" in r.url and r.request.method == "POST" and (LIST_ID in (r.request.post_data or "") or LIST_ID in page.url), timeout=90000) as response_info:
                page.get_by_text("我的任务", exact=True).first.click()
            response = response_info.value
            url = response.url
            payload = json.loads(response.request.post_data)
            result = response.json()
            tasks = []
            seen = set()
            while True:
                if result.get("code") != 200 or not result.get("status"):
                    raise RuntimeError("任务接口返回失败：" + str(result.get("msg")))
                data = result.get("data") or {}
                rows = data.get("displayData")
                if not isinstance(rows, list):
                    raise RuntimeError("任务接口缺少 displayData，页面可能已更新")
                for row in rows:
                    task = {key: row.get(key, "") for key in FIELDS}
                    try:
                        people = json.loads(task["manager"] or "[]")
                        task["manager"] = ", ".join(x.get("name", "") for x in people)
                    except (ValueError, TypeError):
                        pass
                    task_id = task.get("id")
                    if not task_id or task_id in seen:
                        raise RuntimeError("任务分页出现重复或缺少 ID，已停止读取")
                    seen.add(task_id)
                    tasks.append(task)
                page_size = int(data.get("pageSize") or 20)
                if len(rows) < page_size:
                    break
                payload["current"] = int(payload.get("current", 1)) + 1
                result = page.evaluate("""async ({url, payload}) => {
                    const r = await fetch(url, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return await r.json();
                }""", {"url": url, "payload": payload})
            # 只读取实际会绘制在屏幕上的任务详情，页面内并发请求。
            if size != 'quarter':
                selected = ordered_tasks(tasks)[:task_capacity(size)]
                requests = []
                for task in selected:
                    task_id = task['id']
                    payload = {'terminalType': 'PC', 'dataId': task_id, 'formId': '1020270486210527233',
                               'module': 'ebuilderform', 'newLayout': True, 'layoutId': '1027383802561011715',
                               'layoutMultiId': '1320525834662125578', 'dataCrossLayout': False,
                               'permissionId': '', 'allReadOnly': True, 'initialDatas': [], 'dynamicData': False,
                               'cost': False, 'customParam': {'objId': '1020270486210527232', 'dataId': task_id},
                               'orgAsyncPageQuery': True}
                    requests.append({'id': task_id, 'payload': payload})
                details = page.evaluate("""async (requests) => {
                    return await Promise.all(requests.map(async ({id, payload}) => {
                        const url = '/api/ebuilder/form/form/core/getFormDataAndLayout?formId=1020270486210527233&dataId=' + encodeURIComponent(id);
                        const r = await fetch(url, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return await r.json();
                    }));
                }""", requests)
                for task, detail in zip(selected, details):
                    if detail.get('code') != 200 or not detail.get('status'):
                        raise RuntimeError('任务详情读取失败：' + str(detail.get('msg')))
                    form = (detail.get('data') or {}).get('formData')
                    if not isinstance(form, dict) or not isinstance(form.get('dataDetails'), list):
                        raise RuntimeError('任务详情格式异常')
                    values = {str(x.get('fieldId')): x.get('content', '') for x in form['dataDetails']}
                    task['sp'] = values.get('1313123522968756232', '')
                    task['plan_duration'] = values.get('1020344553064210439', '')
            return tasks
        finally:
            browser.close()


def fetch(cfg, size):
    # 持锁抓取：并行更新时多个 OA 组件串行执行，后者直接命中缓存。
    with _fetch_lock:
        now = time.monotonic()
        keys = ('detailed', 'plain') if size == 'quarter' else ('detailed',)
        for key in keys:
            entry = _cache.get(key)
            if entry and now - entry[0] < CACHE_TTL:
                return entry[1]
        path = ROOT / 'oa_credentials.json'
        try:
            credentials = json.loads(path.read_text(encoding='utf-8-sig'))
            username, password = credentials['username'], credentials['password']
        except (OSError, ValueError, KeyError) as exc:
            raise RuntimeError('请在 oa_credentials.json 中配置 OA 用户名和密码') from exc
        if not username or not password:
            raise RuntimeError('OA 用户名或密码为空')
        tasks = get_tasks(username, password, size)
        _cache['plain' if size == 'quarter' else 'detailed'] = (time.monotonic(), tasks)
        return tasks


def fit(draw, value, face, width):
    value = ' '.join(str(value or '').split())
    if draw.textlength(value, font=face) <= width:
        return value
    while value and draw.textlength(value + '…', font=face) > width:
        value = value[:-1]
    return value + '…'


def format_number(value):
    if value is None or str(value).strip() == '':
        return '--'
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return str(value)
        text = format(number, 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    except InvalidOperation:
        return str(value)


def ordered_tasks(tasks):
    active = [item for item in tasks if item.get('task_status') not in ('已完成', '已取消', '已终止')]
    closed = [item for item in tasks if item.get('task_status') in ('已完成', '已取消', '已终止')]
    return active + closed


def task_capacity(size):
    return (282 - 55) // 74 if size in ('half', 'full') else 0


def draw_tasks(tasks, cfg, size):
    width, height = {'quarter': (200, 141), 'half': (200, 282), 'full': (400, 282)}[size]
    im = Image.new('RGB', (width, height), WHITE)
    d = ImageDraw.Draw(im)
    title, body, small = font(26, True), font(18), font(15)
    accent = RED if cfg.get('color_mode') == 'bwr' else BLACK
    d.text((5, 0), '我的任务', font=title, fill=BLACK)
    if tasks is None:
        d.text((5, 48), fit(d, '任务数据不可用', body, width - 10), font=body, fill=BLACK)
        return im
    if size == 'quarter':
        unfinished = sum(item.get('task_status') not in ('已完成', '已取消', '已终止') for item in tasks)
        completed = sum(item.get('task_status') == '已完成' for item in tasks)
        not_started = sum(item.get('task_status') == '未开始' for item in tasks)
        in_progress = sum(item.get('task_status') == '进行中' for item in tasks)
        d.text((145, 9), fit(d, f'共{len(tasks)}项', small, 50), font=small, fill=BLACK)
        large = font(38, True)
        d.text((10, 35), fit(d, str(unfinished), large, 80), font=large, fill=accent if unfinished else BLACK)
        d.text((10, 76), '未完成', font=body, fill=BLACK)
        d.line((99, 39, 99, 100), fill=BLACK)
        d.text((110, 35), fit(d, str(completed), large, 80), font=large, fill=BLACK)
        d.text((110, 76), '已完成', font=body, fill=BLACK)
        d.line((5, 104, 194, 104), fill=BLACK)
        summary = f'未开始 {not_started}  进行中 {in_progress}'
        d.text((5, 110), fit(d, summary, small, width - 10), font=small, fill=BLACK)
        return im
    active = [item for item in tasks if item.get('task_status') not in ('已完成', '已取消', '已终止')]
    items = ordered_tasks(tasks)
    summary = f'待处理 {len(active)}  ·  共 {len(tasks)}'
    d.text((5, 31), fit(d, summary, small, width - 10), font=small, fill=accent if active else BLACK)
    d.line((5, 51, width - 5, 51), fill=BLACK)
    if not items:
        d.text((5, 55), '暂无任务', font=body, fill=BLACK)
        return im
    row_height = 74
    capacity = task_capacity(size)
    for i, item in enumerate(items[:capacity]):
        y = 55 + i * row_height
        name = fit(d, item.get('task_name', ''), body, width - 10)
        d.text((5, y), name, font=body, fill=BLACK)
        status = item.get('task_status') or '未知'
        date = (item.get('plan_finish_time') or '')[:10]
        sp = format_number(item.get('sp'))
        duration = format_number(item.get('plan_duration'))
        # 半屏使用月日，状态和日期与 SP、工期分别显示。
        display_date = date[5:] if size == 'half' and len(date) == 10 else date
        prefix = status + (f' 截止{display_date}' if display_date else '')
        suffix = f'SP:{sp} 工期:{duration}'
        color = accent if status not in ('已完成', '已取消', '已终止') else BLACK
        d.text((5, y + 23), fit(d, prefix, small, width - 10), font=small, fill=color)
        d.text((5, y + 42), fit(d, suffix, small, width - 10), font=small, fill=color)
        if i + 1 < min(capacity, len(items)):
            d.line((5, y + row_height - 3, width - 5, y + row_height - 3), fill=(180, 180, 180))
    return im


def preview_data():
    return [
        {'task_name': '新增试样工资需求表', 'task_status': '未开始', 'plan_finish_time': '2026-11-20', 'sp': '34', 'plan_duration': '3'},
        {'task_name': '产品领料管理优化', 'task_status': '进行中', 'plan_finish_time': '2026-11-25', 'sp': '8', 'plan_duration': '5'},
        {'task_name': '升华生产跟踪增加查询条件', 'task_status': '已完成', 'plan_finish_time': '2026-10-31', 'sp': '5', 'plan_duration': '4'},
        {'task_name': '还布流转数据管理增加查询条件', 'task_status': '已完成', 'plan_finish_time': '2026-10-31', 'sp': '5', 'plan_duration': '4'},
    ]


def component(size, label):
    return {'id': 'oa_tasks_' + size, 'label': label, 'size': size, 'fetch': lambda cfg: fetch(cfg, size),
            'draw': lambda data, cfg: draw_tasks(data, cfg, size), 'preview_data': preview_data}


COMPONENTS = (component('quarter', '我的任务 1/4'), component('half', '我的任务 1/2'),
              component('full', '我的任务 全屏'))
