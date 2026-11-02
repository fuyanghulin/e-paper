# 墨水屏仪表盘

适配 EPD-nRF5 固件、4.2 英寸 400×300 SSD1619 的电脑端 Python 程序。读取本机 Codex CLI 和 GitHub CLI 数据，生成图片。蓝牙功能已按上游协议编写，尚未实机验证。

## 安装及生成图片

要求 Windows、Python 3.10+、已登录的 Codex CLI 和 GitHub CLI。

### 图形界面

双击 `启动仪表盘.bat`（或运行 `python -X utf8 app.py`）。首次使用点击「扫描设备」，在下拉框选择设备，确认屏幕颜色后点「保存并连接」。也可以直接填写地址。连接信息保存在本地 `config.json`，以后启动会自动尝试连接。蓝牙未连接时每 30 秒重试；连接成功后立即获取数据并发送，以后每次完成后间隔 5 分钟更新。断线后重连成功会立即更新。

「立即更新」在已连接时立即获取并传图；未连接时只获取数据生成预览。每次获取的时间和结果显示在右侧，并保存到 `output/history.jsonl`，重启显示最近 200 条。发送成功指刷新命令已写入，不代表物理刷新已完成。界面关闭后自动更新停止。蓝牙传输部分尚待实机验证。

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

Codex 数据通过 `codex app-server` 只读请求 `account/rateLimits/read` 和 `account/usage/read`，Token 近 7 日按服务返回的日期桶之和计算，统计口径以服务返回为准；API-key 等登录方式或旧版 CLI 可能不支持。数据读取失败时显示 `--` 或数据不可用，程序仍保存图片并返回非零退出码。账号凭据由 CLI 自行管理，程序不保存凭据。

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
