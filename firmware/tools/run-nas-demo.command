#!/bin/bash
# Run manually from an ordinary local Terminal when agent sandbox networking is denied.
# This starts an emulator only; it never writes to a physical serial/USB device.
set -euo pipefail
SF_ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$SF_ROOT"
SF_PRIVATE="$SF_ROOT/.private/nas-integration"
if [ ! -f "$SF_PRIVATE/flash.bin" ] || [ ! -f "$SF_PRIVATE/firmware.elf" ]; then
  echo '缺少本机的群晖联调镜像，请先完成本工作区的私有配置信息准备。'
  exit 1
fi
SF_ELF_ARGS=(--elf "$SF_PRIVATE/firmware.elf")
if [ -f "$SF_PRIVATE/next-firmware.elf" ]; then SF_ELF_ARGS+=(--elf "$SF_PRIVATE/next-firmware.elf"); fi
printf '%s\n' 'Stillframe 群晖联调（仅模拟器，不刷写开发板）' \
 '设置网页：http://127.0.0.1:8181/' \
 '管理账号：admin，密码为设置热点密码（当前初始值 12345678）。' \
 '服务器：http://10.10.10.21:8484' \
 '使用独立测试设备档案。首次同步遵守 180 秒刷新保护，需要等待约 3 分钟。' \
 '连接凭证已保存在权限受限的模拟 Flash 中，不在命令或日志中显示。' \
 '模拟器不包含墨水屏模型，照片校验成功后可能报告屏幕通信超时。' \
 '本次模拟测试运行 30 分钟后自动保存并退出；这是模拟器时限，ROM 本身没有该退出限制。' \
 'Ctrl+C 停止。'
"$SF_ROOT/emulator/bin/esp-emu" --chip esp32s3 \
 --firmware "$SF_PRIVATE/flash.bin" "${SF_ELF_ARGS[@]}" \
 --psram-size 8M --net "user,hostfwd=tcp:127.0.0.1:8181-:80" --wifi-ssid myssid --wifi-password mypassword \
 --wifi-fw-ap-password 12345678 --timeout 1800s --save-state --log-color never 2>&1 | tee "$SF_PRIVATE/live-console.log"
