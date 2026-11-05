"""OA 我的任务：后台读取及不同尺寸的墨水屏组件。"""
import json
from pathlib import Path
from decimal import Decimal, InvalidOperation

from PIL import Image, ImageDraw
from .common import BLACK, WHITE, RED, font

ROOT = Path(__file__).resolve().parent.parent
OA_URL = "https://oa.int.shenzhouintl.com/"
LIST_ID = "1025200520246919169"
FIELDS = ("id", "task_name", "manager", "project", "task_type", "priority", "task_status", "progress", "plan_start_time", "plan_finish_time", "actual_start_time", "actual_finish_time", "update_time")

def get_tasks(username, password, size):
    """登录并读取所有分页，返回适合其他 Python 程序调用的列表。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(90000)
            page.goto(OA_URL, wait_until="domcontentloaded", timeout=90000)
            page.get_by_placeholder("请输入用户名/手机号/邮箱").fill(username)
            page.get_by_placeholder("请输入密码").fill(password)
            page.get_by_text("立即登录", exact=True).click()
            page.get_by_text("项目管理", exact=True).first.wait_for()
            page.get_by_text("项目管理", exact=True).first.click()
            page.get_by_text("任务管理", exact=True).first.wait_for()
            page.get_by_text("任务管理", exact=True).first.click()
            page.get_by_text("我的任务", exact=True).first.wait_for()
            with page.expect_response(lambda r: "getListDatas" in r.url and r.request.method == "POST" and LIST_ID in (r.request.post_data or ""), timeout=90000) as response_info:
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
            # 只读取实际会绘制在屏幕上的任务详情。
            if size != 'quarter':
                for task in ordered_tasks(tasks)[:task_capacity(size)]:
                    task_id = task['id']
                    payload = {'terminalType': 'PC', 'dataId': task_id, 'formId': '1020270486210527233',
                               'module': 'ebuilderform', 'newLayout': True, 'layoutId': '1027383802561011715',
                               'layoutMultiId': '1320525834662125578', 'dataCrossLayout': False,
                               'permissionId': '', 'allReadOnly': True, 'initialDatas': [], 'dynamicData': False,
                               'cost': False, 'customParam': {'objId': '1020270486210527232', 'dataId': task_id},
                               'orgAsyncPageQuery': True}
                    detail = page.evaluate("""async ({id, payload}) => {
                        const url = '/api/ebuilder/form/form/core/getFormDataAndLayout?formId=1020270486210527233&dataId=' + encodeURIComponent(id);
                        const r = await fetch(url, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
                        if (!r.ok) throw new Error('HTTP ' + r.status);
                        return await r.json();
                    }""", {'id': task_id, 'payload': payload})
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
    path = ROOT / 'oa_credentials.json'
    try:
        credentials = json.loads(path.read_text(encoding='utf-8-sig'))
        username, password = credentials['username'], credentials['password']
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeError('请在 oa_credentials.json 中配置 OA 用户名和密码') from exc
    if not username or not password:
        raise RuntimeError('OA 用户名或密码为空')
    return get_tasks(username, password, size)


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
    return (282 - 53) // 46 if size in ('half', 'full') else 0


def draw_tasks(tasks, cfg, size):
    width, height = {'quarter': (200, 141), 'half': (200, 282), 'full': (400, 282)}[size]
    im = Image.new('RGB', (width, height), WHITE)
    d = ImageDraw.Draw(im)
    title, body, small = font(17, True), font(12), font(10)
    accent = RED if cfg.get('color_mode') == 'bwr' else BLACK
    d.text((9, 6), '我的任务', font=title, fill=BLACK)
    if tasks is None:
        d.text((9, 42), '任务数据不可用', font=body, fill=BLACK)
        return im
    if size == 'quarter':
        unfinished = sum(item.get('task_status') not in ('已完成', '已取消', '已终止') for item in tasks)
        completed = sum(item.get('task_status') == '已完成' for item in tasks)
        not_started = sum(item.get('task_status') == '未开始' for item in tasks)
        in_progress = sum(item.get('task_status') == '进行中' for item in tasks)
        d.text((135, 11), f'共 {len(tasks)} 项', font=small, fill=BLACK)
        d.line((9, 32, 190, 32), fill=BLACK)
        large = font(25, True)
        d.text((18, 39), str(unfinished), font=large, fill=accent if unfinished else BLACK)
        d.text((18, 72), '未完成', font=body, fill=BLACK)
        d.line((99, 42, 99, 91), fill=BLACK)
        d.text((112, 39), str(completed), font=large, fill=BLACK)
        d.text((112, 72), '已完成', font=body, fill=BLACK)
        d.line((9, 99, 190, 99), fill=BLACK)
        d.text((9, 109), f'未开始 {not_started}   进行中 {in_progress}', font=small, fill=BLACK)
        return im
    active = [item for item in tasks if item.get('task_status') not in ('已完成', '已取消', '已终止')]
    items = ordered_tasks(tasks)
    summary = f'待处理 {len(active)}  ·  共 {len(tasks)}'
    d.text((9, 31), summary, font=small, fill=accent if active else BLACK)
    d.line((9, 48, width - 10, 48), fill=BLACK)
    if not items:
        d.text((9, 58), '暂无任务', font=body, fill=BLACK)
        return im
    row_height = 46
    capacity = task_capacity(size)
    for i, item in enumerate(items[:capacity]):
        y = 53 + i * row_height
        name = fit(d, item.get('task_name', ''), body, width - 20)
        d.text((9, y), name, font=body, fill=BLACK)
        status = item.get('task_status') or '未知'
        date = (item.get('plan_finish_time') or '')[:10]
        sp = format_number(item.get('sp'))
        duration = format_number(item.get('plan_duration'))
        # 半屏使用月日，确保日期、SP 和工期都能在同一行显示。
        display_date = date[5:] if size == 'half' and len(date) == 10 else date
        prefix = status + (f' 截止{display_date}' if display_date else '')
        suffix = f' SP:{sp} 工期:{duration}'
        suffix_width = d.textlength(suffix, font=small)
        prefix = fit(d, prefix, small, max(0, width - 20 - suffix_width))
        d.text((9, y + 18), prefix + suffix, font=small,
               fill=accent if status not in ('已完成', '已取消', '已终止') else BLACK)
        if i + 1 < min(capacity, len(items)):
            d.line((9, y + row_height - 3, width - 10, y + row_height - 3), fill=(180, 180, 180))
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
