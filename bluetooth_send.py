"""Experimental EPD-nRF5 SSD1619 BLE sender; requires a configured device."""
import argparse
import asyncio
import json
from pathlib import Path

from PIL import Image
from bleak import BleakClient, BleakScanner

ROOT = Path(__file__).resolve().parent
SERVICE = '62750001-d828-918d-fb46-b6c11c675aec'
CHAR = '62750002-d828-918d-fb46-b6c11c675aec'
VERSION = '62750003-d828-918d-fb46-b6c11c675aec'


def image_planes(image, mode):
    image = image.convert('RGB')
    if image.size != (400, 300):
        raise ValueError('图片必须是 400×300')
    black, red = bytearray(15000), bytearray(15000)
    for i, (r, g, b) in enumerate(image.getdata()):
        bit = 0x80 >> (i % 8)
        if 0.299 * r + 0.587 * g + 0.114 * b >= 140: black[i // 8] |= bit
        if not (r > 160 and r > g and r > b): red[i // 8] |= bit
    return [bytes(black), bytes(red)] if mode == 'bwr' else [bytes(black)]


async def scan():
    print('扫描蓝牙设备 8 秒……')
    for device in await BleakScanner.discover(timeout=8):
        if device.name and device.name.upper().startswith('NRF'):
            print(f'{device.address}  {device.name}')


class EpaperConnection:
    def __init__(self, address, mode):
        self.address, self.mode = address, mode
        self.client = None
        self.config = None
        self.rle = False
        self.received = asyncio.Event()

    @property
    def connected(self):
        return bool(self.client and self.client.is_connected)

    def notification(self, _sender, data):
        raw = bytes(data)
        if self.config is None:
            self.config = raw
            self.received.set()
        else:
            if 'rle=1' in raw.decode('utf-8', errors='replace'):
                self.rle = True

    async def connect(self):
        expected = 0x02 if self.mode == 'bwr' else 0x04
        device = await BleakScanner.find_device_by_address(self.address, timeout=10)
        if not device:
            raise RuntimeError('未发现设备，请检查设备电源、蓝牙和地址')
        self.client = BleakClient(device, timeout=20)
        try:
            await self.client.connect()
            client = self.client
            version = await client.read_gatt_char(VERSION)
            if not version or version[0] < 0x16:
                raise RuntimeError('固件版本低于 v1.6，不支持此传图方式')
            await client.start_notify(CHAR, self.notification)
            await client.write_gatt_char(CHAR, b'\x01', response=True)
            try:
                await asyncio.wait_for(self.received.wait(), 5)
            except asyncio.TimeoutError:
                raise RuntimeError('没有收到设备配置，已停止发送') from None
            await asyncio.sleep(1)
            conf = self.config
            if len(conf) < 8 or conf[7] != expected:
                current = f'0x{conf[7]:02x}' if len(conf) >= 8 else '未知'
                raise RuntimeError(
                    f'设备驱动配置为 {current}，预期 SSD1619 {self.mode} (0x{expected:02x})；请先在原项目网页中配置驱动和引脚')
        except BaseException:
            await self.close()
            raise

    async def send_image(self, image):
        if not self.connected:
            raise RuntimeError('蓝牙未连接')
        client = self.client
        planes = image_planes(image, self.mode)
        for plane, data in enumerate(planes):
            for offset in range(0, len(data), 18):
                first = offset == 0
                flag = ((plane | (2 if first else 0)) if self.rle else (
                            (0x0f if plane == 0 else 0) | (0 if first else 0xf0)))
                await client.write_gatt_char(CHAR, bytes((0x30, flag)) + data[offset:offset + 18], response=True)
        await client.write_gatt_char(CHAR, b'\x05', response=True)

    async def close(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self.client = None


async def send(address, image, mode):
    connection = EpaperConnection(address, mode)
    try:
        await connection.connect()
        await connection.send_image(image)
        print('刷新命令已发送，请等待墨水屏刷新完成。')
    finally:
        await connection.close()


def main():
    parser = argparse.ArgumentParser(description='EPD-nRF5 蓝牙扫描与发送（未经过实机验证）')
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--address', help='蓝牙地址；也可在 config.json 设置')
    args = parser.parse_args()
    if args.scan:
        asyncio.run(scan())
        return
    if not args.send: parser.error('请指定 --scan 或 --send')
    cfg = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    address = args.address or cfg.get('bluetooth_address')
    if not address: parser.error('请提供 --address 或在 config.json 配置 bluetooth_address')
    path = Path(cfg['output_path'])
    if not path.is_absolute(): path = ROOT / path
    with Image.open(path) as image:
        asyncio.run(send(address, image, cfg['color_mode']))


if __name__ == '__main__':
    main()
