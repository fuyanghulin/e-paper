"""Windows desktop controller for the e-paper dashboard."""
import asyncio
import datetime as dt
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk
from bleak import BleakScanner

import dashboard
from bluetooth_send import EpaperConnection
from layout_editor import LayoutEditor

ROOT = Path(__file__).resolve().parent
RECORDS = ROOT / 'output' / 'history.jsonl'
INTERVAL = 300


class Worker:
    def __init__(self, events, config):
        self.events = events
        self.config = dict(config)
        self.loop = None
        self.commands = None
        self.thread = threading.Thread(target=self._start, daemon=True)
        self.thread.start()

    def _start(self):
        asyncio.run(self.run())

    def emit(self, kind, value):
        self.events.put((kind, value))

    def command(self, kind, value=None):
        if self.loop and self.commands:
            self.loop.call_soon_threadsafe(self.commands.put_nowait, (kind, value))

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.commands = asyncio.Queue()
        conn = None
        next_connect = 0
        next_update = float('inf')
        stopping = False
        no_address_reported = False

        async def update(send_to_device):
            started = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.emit('status', '正在获取所选组件的数据…')
            try:
                success = await asyncio.to_thread(dashboard.run_once, dict(self.config))
                self.emit('preview', None)
                if not success:
                    self.emit('record', (started, '获取失败或数据不完整，未发送'))
                    self.emit('status', '部分组件获取失败，已生成不完整的预览')
                    return False
                if send_to_device:
                    if not conn or not conn.connected:
                        raise RuntimeError('获取完成后蓝牙已断开，未发送')
                    self.emit('status', '正在通过蓝牙传图…')
                    path = Path(self.config['output_path'])
                    if not path.is_absolute(): path = ROOT / path
                    with Image.open(path) as image:
                        await conn.send_image(image)
                    self.emit('record', (started, '获取成功，刷新命令已发送'))
                else:
                    self.emit('record', (started, '获取成功，已生成预览（未传图）'))
                return True
            except Exception as exc:
                self.emit('record', (started, f'更新失败：{exc}'))
                self.emit('status', f'更新失败：{exc}')
                if send_to_device:
                    raise
                return False

        try:
            while not stopping:
                now = time.monotonic()
                if conn and not conn.connected:
                    await conn.close()
                    conn = None
                    self.emit('connection', '蓝牙已断开，准备重连')
                    next_connect = now
                    next_update = float('inf')
                if not conn and self.config.get('bluetooth_address') and now >= next_connect:
                    self.emit('connection', '正在连接蓝牙…')
                    candidate = EpaperConnection(self.config['bluetooth_address'], self.config.get('color_mode', 'bwr'))
                    try:
                        await candidate.connect()
                        conn = candidate
                        self.emit('connection', '蓝牙已连接')
                        self.emit('status', '连接成功，准备更新')
                        next_update = time.monotonic()
                    except Exception as exc:
                        await candidate.close()
                        self.emit('connection', '连接失败，30 秒后重试')
                        self.emit('status', str(exc))
                        next_connect = time.monotonic() + 30
                elif not conn and not self.config.get('bluetooth_address'):
                    if not no_address_reported:
                        self.emit('connection', '未配置设备，请扫描或填写地址')
                        no_address_reported = True
                if conn and time.monotonic() >= next_update:
                    try:
                        await update(True)
                    except Exception as exc:
                        self.emit('status', f'传输异常：{exc}')
                        await conn.close()
                        conn = None
                        self.emit('connection', '蓝牙已断开，30 秒后重试')
                        next_connect = time.monotonic() + 30
                    next_update = time.monotonic() + INTERVAL
                    if conn:
                        self.emit('status', '等待下一次更新（5 分钟）')
                try:
                    kind, value = await asyncio.wait_for(self.commands.get(), timeout=1)
                except asyncio.TimeoutError:
                    continue
                if kind == 'stop':
                    stopping = True
                elif kind == 'settings':
                    if conn:
                        await conn.close()
                        conn = None
                    self.config.update(value)
                    no_address_reported = False
                    next_connect = 0
                    next_update = float('inf')
                elif kind == 'components':
                    self.config.update(value)
                    if conn:
                        next_update = 0
                    elif await update(False):
                        self.emit('status', '预览已更新；连接设备后自动传图')
                elif kind == 'refresh':
                    if conn:
                        next_update = 0
                    else:
                        if await update(False):
                            self.emit('status', '预览已更新；连接设备后自动传图')
                elif kind == 'scan':
                    self.emit('scan_state', True)
                    try:
                        found = await BleakScanner.discover(timeout=8)
                        items = [(d.name or '(无名称)', d.address) for d in found]
                        self.emit('scan_results', items)
                    except Exception as exc:
                        self.emit('status', f'扫描失败：{exc}')
                    finally:
                        self.emit('scan_state', False)
        finally:
            if conn:
                await conn.close()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('墨水屏仪表盘')
        self.geometry('980x740')
        self.minsize(900, 680)
        self.config_data = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        self.events = queue.Queue()
        self.address = tk.StringVar(value=self.config_data.get('bluetooth_address', ''))
        self.mode = tk.StringVar(value=self.config_data.get('color_mode', 'bwr'))
        self.connection = tk.StringVar(value='正在启动…')
        self.status = tk.StringVar(value='首次使用请扫描设备并保存地址')
        self._build()
        self.load_history()
        self.show_preview()
        self.worker = Worker(self.events, self.config_data)
        self.after(150, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def _build(self):
        self.configure(bg='#f3f5f7')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 17, 'bold'), background='#f3f5f7')
        style.configure('Sub.TLabel', font=('Microsoft YaHei UI', 9), background='#f3f5f7', foreground='#64748b')
        style.configure('TFrame', background='#f3f5f7')
        style.configure('Card.TLabelframe', background='#f3f5f7', padding=12)
        style.configure('Card.TLabelframe.Label', font=('Microsoft YaHei UI', 10, 'bold'), background='#f3f5f7')
        style.configure('TLabel', background='#f3f5f7')
        outer = ttk.Frame(self, padding=(20, 15))
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='墨水屏仪表盘', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='4.2 英寸 · 400 × 300 · SSD1619    /    连接后每 5 分钟自动更新', style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        setup = ttk.LabelFrame(outer, text='蓝牙设备', style='Card.TLabelframe')
        setup.pack(fill='x')
        ttk.Label(setup, text='设备地址').grid(row=0, column=0, sticky='w', padx=(0, 8))
        self.device_list = ttk.Combobox(setup, textvariable=self.address, width=33)
        self.device_list.grid(row=0, column=1, sticky='ew')
        self.device_list.bind('<<ComboboxSelected>>', self.select_device)
        self.scan_button = ttk.Button(setup, text='扫描设备', command=lambda: self.worker.command('scan'))
        self.scan_button.grid(row=0, column=2, padx=7)
        ttk.Label(setup, text='屏幕颜色').grid(row=0, column=3, padx=(6, 5))
        ttk.Combobox(setup, textvariable=self.mode, values=('bwr', 'bw'), state='readonly', width=6).grid(row=0, column=4)
        ttk.Button(setup, text='保存并连接', command=self.save_settings).grid(row=0, column=5, padx=(8, 0))
        setup.columnconfigure(1, weight=1)
        ttk.Label(setup, textvariable=self.connection, foreground='#176a45').grid(row=1, column=0, columnspan=6, sticky='w', pady=(9, 0))
        ttk.Label(setup, textvariable=self.status, foreground='#5c6874', wraplength=820).grid(row=2, column=0, columnspan=6, sticky='w', pady=(3, 0))
        content = ttk.Frame(outer)
        content.pack(fill='both', expand=True, pady=(12, 0))
        left = ttk.LabelFrame(content, text='屏幕预览', style='Card.TLabelframe')
        left.pack(side='left', fill='both', expand=True, padx=(0, 10))
        preview_frame = tk.Frame(left, width=402, height=302, bg='white', relief='solid', borderwidth=1)
        preview_frame.pack(pady=(0, 8))
        preview_frame.pack_propagate(False)
        self.preview = tk.Label(preview_frame, text='暂无预览', bg='white')
        self.preview.pack(fill='both', expand=True)
        ttk.Button(left, text='立即更新', command=lambda: self.worker.command('refresh')).pack(anchor='w')
        ttk.Label(left, text='未连接时仅生成预览；连接后自动传图。', style='Sub.TLabel', wraplength=400).pack(anchor='w', pady=5)
        right = ttk.Frame(content)
        right.pack(side='left', fill='both', expand=True)
        components = ttk.LabelFrame(right, text='显示组件', style='Card.TLabelframe')
        components.pack(fill='x', pady=(0, 8))
        ttk.Label(components, text='拖拽组件，按网格安排屏幕位置。', style='Sub.TLabel').pack(anchor='w')
        ttk.Button(components, text='设计布局…', command=self.open_layout_editor).pack(anchor='w', pady=(8, 0))
        history_frame = ttk.LabelFrame(right, text='获取记录', style='Card.TLabelframe')
        history_frame.pack(fill='both', expand=True)
        self.history = ttk.Treeview(history_frame, columns=('time', 'result'), show='headings', height=13)
        self.history.heading('time', text='获取时间')
        self.history.heading('result', text='结果')
        self.history.column('time', width=145, minwidth=125, stretch=False)
        self.history.column('result', width=190, minwidth=100)
        scroll = ttk.Scrollbar(history_frame, orient='vertical', command=self.history.yview)
        self.history.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.history.pack(fill='both', expand=True)

    def open_layout_editor(self):
        try:
            LayoutEditor(self, self.config_data, self.save_components)
        except ValueError as exc:
            messagebox.showerror('布局无效', str(exc))

    def save_components(self, placements):
        names = [entry['id'] for entry in placements]
        layout_settings = {'components': names, 'component_layout': placements}
        try:
            dashboard.layout_components(layout_settings)
        except ValueError as exc:
            messagebox.showwarning('布局无效', str(exc))
            return False
        config = dict(self.config_data, **layout_settings)
        try:
            (ROOT / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('保存失败', str(exc))
            return False
        self.config_data = config
        self.worker.command('components', layout_settings)
        self.status.set('布局已保存，正在更新。')
        return True

    def select_device(self, _event):
        value = self.address.get()
        if ' | ' in value:
            self.address.set(value.rsplit(' | ', 1)[1])

    def save_settings(self):
        address = self.address.get().strip()
        if not address:
            messagebox.showwarning('设备地址', '请先扫描选择设备或填写蓝牙地址。')
            return
        self.config_data.update(bluetooth_address=address, color_mode=self.mode.get(), refresh_minutes=5)
        try:
            (ROOT / 'config.json').write_text(json.dumps(self.config_data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('保存失败', str(exc))
            return
        self.worker.command('settings', {'bluetooth_address': address, 'color_mode': self.mode.get()})

    def show_preview(self):
        path = Path(self.config_data.get('output_path', 'output/dashboard.png'))
        if not path.is_absolute(): path = ROOT / path
        if path.exists():
            with Image.open(path) as image:
                self.preview_image = ImageTk.PhotoImage(image.copy())
            self.preview.configure(image=self.preview_image, width=400, height=300, text='')

    def load_history(self):
        if not RECORDS.exists(): return
        try:
            for line in RECORDS.read_text(encoding='utf-8').splitlines()[-200:]:
                try:
                    record = json.loads(line)
                    self.history.insert('', 0, values=(record['time'], record['result']))
                except (ValueError, KeyError):
                    continue
        except OSError as exc:
            self.status.set(f'读取历史记录失败：{exc}')

    def add_record(self, timestamp, result):
        self.history.insert('', 0, values=(timestamp, result))
        try:
            RECORDS.parent.mkdir(parents=True, exist_ok=True)
            with RECORDS.open('a', encoding='utf-8') as file:
                file.write(json.dumps({'time': timestamp, 'result': result}, ensure_ascii=False) + '\n')
        except OSError as exc:
            self.status.set(f'保存历史记录失败：{exc}')

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'connection': self.connection.set(value)
                elif kind == 'status': self.status.set(value)
                elif kind == 'preview': self.show_preview()
                elif kind == 'record': self.add_record(*value)
                elif kind == 'scan_state': self.scan_button.configure(state='disabled' if value else 'normal')
                elif kind == 'scan_results':
                    self.device_list['values'] = [f'{name} | {address}' for name, address in value]
                    self.status.set(f'扫描到 {len(value)} 个设备，请在下拉列表中选择并保存。')
        except queue.Empty:
            pass
        self.after(150, self.poll)

    def close(self):
        self.worker.command('stop')
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
