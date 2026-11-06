# 墨水屏仪表盘

适配 EPD-nRF5 固件、4.2 英寸 400×300 SSD1619 的电脑端 Python 程序。读取本机 Codex CLI 和 GitHub CLI 数据，生成图片。蓝牙功能已按上游协议编写，尚未实机验证。

## 安装及生成图片

要求 Windows、Python 3.10+、已登录的 Codex CLI 和 GitHub CLI。

### 图形界面

双击 `启动仪表盘.bat`（或运行 `python -X utf8 app.py`）。首次使用点击「扫描设备」，在下拉框选择设备，确认屏幕颜色后点「保存并连接」。也可以直接填写地址。连接信息保存在本地 `config.json`，以后启动会自动尝试连接。蓝牙未连接时每 30 秒重试；连接成功后立即获取数据并发送，以后每次完成后间隔 5 分钟更新。断线后重连成功会立即更新。

在「显示组件」点击「设计布局」，从组件库拖入屏幕网格，也可以拖动已放置的组件；从组件库放置时会覆盖目标区域内的组件；拖动布局中的组件时，如果目标区域的组件能整体移到可用空间就交换，否则覆盖目标区域。组件库缩略图和右侧布局预览使用示意数据，不会联网；保存布局后生成的屏幕预览使用实际数据。点击组件后可将其移除。点击「保存布局并更新」会保存位置并生成预览，已连接设备时自动传图。未使用的位置留白，组件不能重叠；满屏、半屏组件只能占据对应的完整网格。布局存储在 `config.json` 的 `component_layout` 中，旧版只有 `components` 的配置会按原顺序自动排布。程序只读取已选组件的数据，即使没有蓝牙设备也可以设计布局。

组件支持满屏（400×282）、左右半屏（200×282）和四分之一屏（200×141），底部 18 像素用于更新时间。Codex 和 GitHub 是左右半屏组件；卡通熊猫和卡通柯基是四分之一屏静态宠物组件，使用本地图像，不需要网络。宠物图片按黑白墨水屏转换。OA“我的任务”提供四分之一屏、左右半屏和满屏三种组件，四分之一屏显示任务数量概况；半屏和满屏优先显示未完成任务，空间不足时截断任务名称和列表。现有组件分别位于 `components/codex.py` 和 `components/github.py`。新增组件时，在 `components/` 中新建独立 Python 文件，定义组件的 `COMPONENT`（唯一 ID `id`、显示名称 `label`、尺寸 `size`、数据读取函数 `fetch` 和绘图函数 `draw`），并在 `components/__init__.py` 中导入并注册。尺寸为 `full` / `half` / `quarter`；`fetch(cfg)` 返回数据，`draw(data, cfg)` 返回对应尺寸的 Pillow 图片。可选的 `preview_data()` 提供组件库缩略图的示意数据，未提供时使用 `None` 绘制。注册后选择界面会自动列出组件。

「立即更新」在已连接时立即获取并传图；未连接时只获取数据生成预览。每次获取的时间和结果显示在右侧，并保存到 `output/history.jsonl`，重启显示最近 200 条。发送成功指刷新命令已写入，不代表物理刷新已完成。点击窗口关闭按钮会隐藏到 Windows 通知区域，后台继续自动更新；双击托盘图标或右键选择「打开仪表盘」可恢复窗口，右键选择「退出程序」可结束程序，正在进行的任务完成后退出。托盘图标可能位于任务栏的「显示隐藏的图标」中。蓝牙传输部分尚待实机验证。

重复运行启动脚本会打开已运行的仪表盘窗口，不会启动第二个后台程序。

### 命令行

```powershell
cd D:\client\e-paper
python -m pip install -r requirements.txt
codex login status
gh auth status
python -X utf8 dashboard.py
```

图片固定生成在 `D:\client\e-paper\output\dashboard.png`。配置文件 `config.json` 中的 `output_path` 可以修改路径。运行 `python -X utf8 dashboard.py --watch` 可按配置间隔重新读取并生成图片；按 Ctrl+C 停止。命令行循环只生成图片，不会自动传到屏幕。

`github_username` 留空时使用 `gh` 当前登录账号。程序读取近一年 GitHub 贡献总数和仓库贡献，屏幕格子显示最近 15 周；贡献是黑白简化图。仓库列表按 GitHub 返回结果展示，私有数据取决于授权和 GitHub 可见性规则。

Codex 数据通过 `codex app-server` 只读请求 `account/rateLimits/read` 和 `account/usage/read`，Token 近 7 日按服务返回的日期桶之和计算，统计口径以服务返回为准；API-key 等登录方式或旧版 CLI 可能不支持。数据读取失败时显示 `--` 或数据不可用，程序仍保存图片并返回非零退出码。Codex 和 GitHub 账号凭据由各自的 CLI 管理。

## OA 我的任务

安装依赖后，在「设计布局」中选择“我的任务 1/4”“我的任务 1/2”或“我的任务 全屏”。组件只读取“我负责的”任务；四分之一屏显示总数、未完成、已完成、未开始和进行中数量，未完成不包含已取消或已终止任务；半屏和满屏优先显示未完成任务、状态、计划完成日期、任务积分（SP）和计划任务工期（天）。列表按屏幕可容纳的任务数读取详情，未显示的任务不请求详情；四分之一屏不请求任务详情。布局预览使用示例数据；保存后刷新会联网读取真实任务。读取失败时本次不会向设备发送不完整数据。

运行需要本机安装 Google Chrome。OA 账号配置在项目目录的 `oa_credentials.json`，格式为 `{"username": "账号", "password": "密码"}`。该文件已加入 `.gitignore`，请妥善保管。登录和查询由 Playwright 无界面运行；登录会话缓存在 `output/oa_session.json`，有效期内跳过登录，过期后自动重新登录。如网站要求验证码或更改登录流程，可能需要调整程序。任务分页已实现，但目前只有一页数据，跨页读取尚未实测。

## 屏幕与蓝牙（待实机调试）

`color_mode` 默认 `bwr`（黑白红，SSD1619 型号 `02`）；若是黑白屏，改为 `bw`（型号 `04`）。屏幕颜色暂未确定，请到货后确认。首先使用 EPD-nRF5 原项目网页设置正确的驱动、屏幕引脚等，确保固件为 v1.6 或更新版。此项目不会自动刷固件或设置引脚。

```powershell
python -X utf8 bluetooth_send.py --scan
```

扫描后将设备地址填入 `config.json` 的 `bluetooth_address`，或直接：

```powershell
python -X utf8 bluetooth_send.py --send --address "设备地址"
```

发送脚本使用 EPD-nRF5 的 BLE 服务、初始化、分色数据和刷新命令；会检查设备报告的驱动配置是否与色彩模式匹配。不同固件版本、通知时序、蓝牙适配器和屏幕批次仍需实机验证。如失败，先使用上游网页手动传 `output/dashboard.png`，再根据实际错误调试。发送成功提示只代表刷新命令已写入，不代表屏幕物理刷新已完成。

上游：[EPD-nRF5](https://github.com/tsl0922/EPD-nRF5)，固件使用其 GPL-3.0 许可证；本程序的蓝牙流程参考上游网页实现。

图标来自 [Tabler Icons](https://github.com/tabler/tabler-icons)（MIT）和 [Simple Icons](https://github.com/simple-icons/simple-icons)（CC0），已转换为本地 PNG，运行时无需联网加载图标。
