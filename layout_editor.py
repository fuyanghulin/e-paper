"""Interactive 2×2 e-paper component layout editor."""
import tkinter as tk
from tkinter import ttk, messagebox

from PIL import Image, ImageTk

import dashboard


class LayoutEditor(tk.Toplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.title('设计屏幕布局')
        self.resizable(False, False)
        self.transient(parent)
        self.on_save = on_save
        self.preview_config = dict(config)
        self.placements = [dict(id=name, x=x, y=y) for name, x, y in dashboard.layout_components(config)]
        self.selected = None
        self.drag = None
        self.drag_offset = (0, 0)
        self.drag_window = None
        self.drag_label = None
        self.drag_visible = False
        self.message = tk.StringVar(value='布局区拖动优先交换位置，空间不足时覆盖；从组件库拖入会覆盖。')
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='组件库（缩略图为示意）').grid(row=0, column=0, sticky='w')
        ttk.Label(outer, text='屏幕布局预览（示意，400 × 282）').grid(row=0, column=1, sticky='w', padx=(14, 0))
        library_frame = ttk.Frame(outer)
        library_frame.grid(row=1, column=0, sticky='nsw', pady=6)
        self.library = tk.Canvas(library_frame, width=238, height=282, bg='white',
                                 highlightthickness=1, highlightbackground='#94a3b8', cursor='hand2')
        scrollbar = ttk.Scrollbar(library_frame, orient='vertical', command=self.library.yview)
        self.library.configure(yscrollcommand=scrollbar.set)
        self.library.pack(side='left', fill='both')
        scrollbar.pack(side='left', fill='y')
        self.names = list(dashboard.COMPONENTS)
        self.preview_images = []
        self.component_previews = {}
        self.draw_library()
        self.library.bind('<MouseWheel>', self.scroll_library)
        self.library.bind('<ButtonPress-1>', self.library_press)
        self.library.bind('<B1-Motion>', self.drag_motion)
        self.library.bind('<ButtonRelease-1>', self.drag_release)
        self.canvas = tk.Canvas(outer, width=400, height=282, bg='white', highlightthickness=1,
                                highlightbackground='#64748b', cursor='hand2')
        self.canvas.grid(row=1, column=1, padx=(14, 0), pady=6)
        self.canvas.bind('<ButtonPress-1>', self.canvas_press)
        self.canvas.bind('<B1-Motion>', self.drag_motion)
        self.canvas.bind('<ButtonRelease-1>', self.drag_release)
        ttk.Label(outer, textvariable=self.message, foreground='#526477', wraplength=660).grid(row=2, column=0,
                                                                                               columnspan=2, sticky='w',
                                                                                               pady=(2, 8))
        actions = ttk.Frame(outer)
        actions.grid(row=3, column=0, columnspan=2, sticky='ew')
        ttk.Button(actions, text='移除选中组件', command=self.remove_selected).pack(side='left')
        ttk.Button(actions, text='保存布局并更新', command=self.save).pack(side='right')
        ttk.Button(actions, text='取消', command=self.destroy).pack(side='right', padx=8)
        self.redraw()

    def redraw(self, target=None):
        self.canvas.delete('all')
        for x in (0, 200):
            for y in (0, 141):
                self.canvas.create_rectangle(x, y, x + 200, y + 141, outline='#cbd5e1', dash=(4, 4))
        for entry in self.placements:
            if self.drag_visible and self.drag and self.drag[0] == 'canvas' and entry['id'] == self.drag[1]:
                continue
            item = dashboard.COMPONENTS[entry['id']]
            x, y = entry['x'], entry['y']
            w, h = dashboard.COMPONENT_SIZES[item['size']]
            selected = self.selected == entry['id']
            preview = self.component_previews.get(entry['id'])
            if preview:
                self.canvas.create_image(x, y, anchor='nw', image=preview)
            else:
                self.canvas.create_rectangle(x, y, x + w, y + h, fill='#e8eef5', outline='')
                self.canvas.create_text(x + w / 2, y + h / 2, text=item['label'] + '\n暂无预览',
                                        font=('Microsoft YaHei UI', 11), fill='#526477', justify='center')
            self.canvas.create_rectangle(x + 1, y + 1, x + w - 2, y + h - 2,
                                         outline='#2563eb' if selected else '#94a3b8',
                                         width=2 if selected else 1)
        if target:
            x, y, w, h = target
            self.canvas.create_rectangle(x + 1, y + 1, x + w - 1, y + h - 1, outline='#2563eb', width=3, dash=(5, 3))

    def draw_library(self):
        row_height = 106
        for index, name in enumerate(self.names):
            item = dashboard.COMPONENTS[name]
            top = index * row_height
            self.library.create_rectangle(4, top + 4, 232, top + row_height - 4,
                                          fill='#f5f8fc', outline='#d6dee8')
            try:
                data = item['preview_data']() if item.get('preview_data') else None
                image = item['draw'](data, self.preview_config).copy()
                if image.size != dashboard.COMPONENT_SIZES[item['size']]:
                    raise ValueError('组件预览尺寸不匹配')
                self.component_previews[name] = ImageTk.PhotoImage(image, master=self)
                image.thumbnail((78, 88), Image.Resampling.LANCZOS)
                preview = ImageTk.PhotoImage(image, master=self)
                self.preview_images.append(preview)
                self.library.create_image(45, top + row_height / 2, image=preview)
            except Exception:
                # A future component without usable preview data must not break the editor.
                self.library.create_text(45, top + row_height / 2, text='暂无\n预览', fill='#64748b')
            self.library.create_text(91, top + 35, anchor='w', text=item['label'],
                                     font=('Microsoft YaHei UI', 10, 'bold'), fill='#1e293b', width=135)
            self.library.create_text(91, top + 62, anchor='w',
                                     text=dashboard.COMPONENT_SIZE_LABELS[item['size']],
                                     font=('Microsoft YaHei UI', 9), fill='#526477')
        self.library.configure(scrollregion=(0, 0, 238, len(self.names) * row_height))

    def scroll_library(self, event):
        self.library.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'

    def library_press(self, event):
        index = int(self.library.canvasy(event.y) // 106)
        if 0 <= index < len(self.names):
            name = self.names[index]
            w, h = dashboard.COMPONENT_SIZES[dashboard.COMPONENTS[name]['size']]
            self.drag_offset = (w // 2, h // 2)
            self.drag = ('library', name)

    def canvas_press(self, event):
        self.selected = next((entry['id'] for entry in reversed(self.placements)
                              if entry['x'] <= event.x < entry['x'] +
                              dashboard.COMPONENT_SIZES[dashboard.COMPONENTS[entry['id']]['size']][0]
                              and entry['y'] <= event.y < entry['y'] +
                              dashboard.COMPONENT_SIZES[dashboard.COMPONENTS[entry['id']]['size']][1]), None)
        self.drag = ('canvas', self.selected) if self.selected else None
        if self.selected:
            entry = next(item for item in self.placements if item['id'] == self.selected)
            self.drag_offset = (event.x - entry['x'], event.y - entry['y'])
        self.redraw()

    def target(self, event):
        if not self.drag:
            return None
        x = event.x_root - self.canvas.winfo_rootx()
        y = event.y_root - self.canvas.winfo_rooty()
        if not (0 <= x < 400 and 0 <= y < 282):
            return None
        w, h = dashboard.COMPONENT_SIZES[dashboard.COMPONENTS[self.drag[1]]['size']]
        return (0 if w == 400 else (x // 200) * 200,
                0 if h == 282 else (y // 141) * 141, w, h)

    def drag_motion(self, event):
        if not self.drag:
            return
        if self.drag_window is None:
            self.drag_window = tk.Toplevel(self)
            self.drag_window.withdraw()
            self.drag_window.overrideredirect(True)
            try:
                self.drag_window.attributes('-alpha', 0.85)
            except tk.TclError:
                pass
            self.drag_label = tk.Label(self.drag_window, borderwidth=2, relief='solid',
                                       bg='white', highlightbackground='#2563eb')
            self.drag_label.pack()
        name = self.drag[1]
        preview = self.component_previews.get(name)
        self.drag_label.configure(image=preview or '', text='' if preview else dashboard.COMPONENTS[name]['label'],
                                  compound='center')
        x = event.x_root - self.drag_offset[0]
        y = event.y_root - self.drag_offset[1]
        self.drag_window.geometry(f'{x:+d}{y:+d}')
        self.drag_window.deiconify()
        self.drag_window.lift()
        self.drag_visible = True
        self.redraw(self.target(event))

    def end_drag(self):
        self.drag_visible = False
        if self.drag_window is not None:
            self.drag_window.withdraw()
        self.drag = None

    def drag_release(self, event):
        target = self.target(event)
        if not self.drag or target is None:
            self.end_drag()
            self.redraw()
            return
        origin, name = self.drag
        x, y, w, h = target
        previous = next((entry for entry in self.placements if entry['id'] == name), None)
        covered = [entry for entry in self.placements if entry['id'] != name and self.overlaps(entry, x, y, w, h)]
        others = [entry.copy() for entry in self.placements if entry['id'] != name and entry not in covered]
        placed = dict(id=name, x=x, y=y)
        swapped = False
        if origin == 'canvas' and previous and covered:
            # Try the corresponding position first, then other free grid positions.
            # This lets a half-screen component occupy an entire free column even
            # when the dragged quarter started in its bottom cell.
            preferred = (previous['x'] - x, previous['y'] - y)
            offsets = [(dx, dy) for dx in (-200, 0, 200) for dy in (-141, 0, 141)]
            offsets.sort(key=lambda offset: abs(offset[0] - preferred[0]) // 200 +
                                            abs(offset[1] - preferred[1]) // 141)
            for dx, dy in offsets:
                replacements = [dict(entry, x=entry['x'] + dx, y=entry['y'] + dy)
                                for entry in covered]
                candidate = others + replacements + [placed]
                try:
                    dashboard.layout_components(
                        {'components': [item['id'] for item in candidate], 'component_layout': candidate})
                except ValueError:
                    continue
                swapped = True
                break
        if not swapped:
            candidate = others + [placed]
        try:
            dashboard.layout_components(
                {'components': [item['id'] for item in candidate], 'component_layout': candidate})
        except ValueError as exc:
            self.message.set(f'无法放置组件：{exc}')
        else:
            self.placements = candidate
            self.selected = name
            if swapped:
                self.message.set('组件已交换位置。点击“保存布局并更新”应用。')
            elif covered:
                labels = '、'.join(dashboard.COMPONENTS[item['id']]['label'] for item in covered)
                self.message.set(f'已覆盖：{labels}。点击“保存布局并更新”应用。')
            else:
                self.message.set('布局已修改，点击“保存布局并更新”应用。')
        self.end_drag()
        self.redraw()

    @staticmethod
    def overlaps(entry, x, y, w, h):
        ew, eh = dashboard.COMPONENT_SIZES[dashboard.COMPONENTS[entry['id']]['size']]
        return x < entry['x'] + ew and entry['x'] < x + w and y < entry['y'] + eh and entry['y'] < y + h

    def remove_selected(self):
        if self.selected:
            self.placements = [entry for entry in self.placements if entry['id'] != self.selected]
            self.selected = None
            self.message.set('组件已移除，点击“保存布局并更新”应用。')
            self.redraw()

    def save(self):
        names = [entry['id'] for entry in self.placements]
        try:
            dashboard.layout_components({'components': names, 'component_layout': self.placements})
        except ValueError as exc:
            messagebox.showwarning('布局无效', str(exc), parent=self)
            return
        if self.on_save([entry.copy() for entry in self.placements]):
            self.destroy()
