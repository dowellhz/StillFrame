#!/usr/bin/env python3
"""Run an ESP32-S3 merged flash image in the pinned ESP Emulator engine.
Always runs a private working flash copy; never modifies the supplied firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def inspect_image(source):
    image = source.read_bytes()
    if len(image) < 0x9000 or image[0] != 0xE9:
        raise ValueError('需要从地址 0 开始的完整 Flash 镜像，而非单独的应用 bin')
    chip = struct.unpack_from('<H', image, 12)[0]
    if chip != 9:
        raise ValueError(f'镜像芯片 ID 为 {chip}，要求 ESP32-S3（9）')
    if image[0x8000:0x8002] != b'\xaa\x50':
        raise ValueError('在 0x8000 未找到分区表；请用 idf.py merge-bin 合并固件。非标准分区表偏移暂不支持')
    parts = []
    for off in range(0x8000, 0x9000, 32):
        magic, typ, sub, start, size, label, flags = struct.unpack_from('<HBBII16sI', image, off)
        if magic != 0x50AA:
            break
        parts.append({'name': label.split(b'\0')[0].decode('utf8', errors='replace'), 'type': typ, 'subtype': sub, 'offset': start, 'size': size})
    if not any(p['type'] == 0 for p in parts):
        raise ValueError('镜像分区表没有应用分区')
    return {'source': str(source), 'sha256': hashlib.sha256(image).hexdigest(), 'size': len(image), 'chip': 'esp32s3', 'partitions': parts}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('firmware', nargs='?', default=str(ROOT / 'fixtures/vendor-wifi.bin'))
    p.add_argument('--name', default='device', help='模拟设备存档名；不同名称相互独立')
    p.add_argument('--seconds', type=int, default=30, help='运行时长，默认 30 秒')
    p.add_argument('--allow-panic-reboot', action='store_true', help='测试专用：让故障固件真实重启，以验证引导程序回退')
    p.add_argument('--exit-on', help='测试专用：串口出现指定标记时结束')
    p.add_argument('--fresh', action='store_true', help='丢弃指定模拟设备的 Flash 存档，从输入镜像重建')
    p.add_argument('--http-port', type=int, help='可选：把本机 127.0.0.1 的端口转发至固件 HTTP 80 端口')
    p.add_argument('--ssid', default='myssid', help='提供给固件连接的虚拟路由器名称')
    p.add_argument('--wifi-password', default='mypassword', help='虚拟路由器密码')
    p.add_argument('--ap-password', default='123456789', help='固件自己建立的 AP 密码；厂家默认为 123456789，Stillframe 计划使用 12345678')
    p.add_argument('--elf', type=Path, help='可选：同一构建的应用 ELF，便于符号解析和诊断')
    args = p.parse_args()
    try:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', args.name):
            raise ValueError('存档名称只允许英文字母、数字、下划线和连字符')
        if not 1 <= args.seconds <= 86400:
            raise ValueError('运行时间需在 1～86400 秒之间')
        if args.http_port is not None and not 1024 <= args.http_port <= 65535:
            raise ValueError('本机端口需在 1024～65535 之间')
        source = Path(args.firmware).resolve()
        info = inspect_image(source)
        engine = ROOT / 'bin/esp-emu'
        if not engine.is_file():
            raise ValueError('缺少 emulator/bin/esp-emu，请参考 README 安装固定版本引擎')
        folder = ROOT / 'runs' / args.name
        folder.mkdir(parents=True, exist_ok=True)
        flash = folder / 'flash.bin'
        manifest = folder / 'source.json'
        if flash.exists() and not args.fresh:
            if not manifest.exists() or json.loads(manifest.read_text())['sha256'] != info['sha256']:
                raise ValueError('存档属于另一份固件，请换 --name，或加 --fresh 重建；输入原文件不会被改写')
        else:
            shutil.copyfile(source, flash)
            manifest.write_text(json.dumps(info, ensure_ascii=False, indent=2))
        net = 'user' if args.http_port is None else f'user,hostfwd=tcp:127.0.0.1:{args.http_port}-:80'
        cmd = [str(engine), '--chip', 'esp32s3', '--firmware', str(flash), '--psram-size', '8M', '--net', net,
               '--wifi-ssid', args.ssid, '--wifi-password', args.wifi_password, '--wifi-fw-ap-password', args.ap_password,
               '--timeout', f'{args.seconds}s', '--save-state', '--log-color', 'never']
        if args.exit_on:
            cmd += ['--exit-on', args.exit_on]
        if args.allow_panic_reboot:
            cmd += ['--no-panic-intercept']
        if args.elf:
            cmd += ['--elf', str(args.elf.resolve())]
        log = folder / 'console.log'
        print(f'ESP32-S3 固件仿真 · 引擎 0.50.0\n输入：{source}\n工作 Flash：{flash}\n串口日志：{log}', flush=True)
        print('当前仅验证执行与串口；未提供 GDEP133C02 屏幕外设模型。', flush=True)
        if args.http_port:
            print(f'固件启动 HTTP 后尝试访问 http://127.0.0.1:{args.http_port}/wifi；转发是否支持该固件仍需验证。', flush=True)
        with log.open('w') as out:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                for line in iter(process.stdout.readline, b''):
                    text = line.decode('utf8', errors='replace')
                    print(text, end='', flush=True)
                    out.write(text)
                    out.flush()
                return process.wait()
            except KeyboardInterrupt:
                process.terminate()
                process.wait(timeout=10)
                return 130
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f'无法启动：{e}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
