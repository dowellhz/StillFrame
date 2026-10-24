# Stillframe

13.3 英寸六色墨水屏相框：ESP32-S3 固件 + 群晖相册服务器。

| 目录 | 内容 |
|---|---|
| [firmware](firmware/) | Good Display ESP32-133C02-IL（ESP32-S3 N16R8）+ GDEP133C02 固件，ESP-IDF 5.5.2。配网热点、群晖同步、本地 MicroSD 相册、网页与远程 OTA。 |
| [server](server/) | 群晖 DSM 7 套件（Node.js）：照片库、多级分类、六色渲染、设备管理与 ROM 分发。接口见 [server/API.md](server/API.md)。 |
| [simulator](simulator/) | 设置网页的浏览器模拟器。 |
| [emulator](emulator/) | 在 Espressif ESP Emulator 中运行固件的脚本。 |
| [doc](doc/) | 需求与开发、联调记录。 |

编译好的固件（app.bin / flash.bin）和群晖 SPK 发布在 GitHub Releases，不放进仓库。

## 构建

```sh
firmware/tools/idf.sh build merge-bin     # 固件，需要 ESP-IDF v5.5.2
cd server && npm ci && npm test && python3 scripts/build-spk.py
```

## 未纳入仓库

工具链（`.tools/`）、群晖联调凭证与记录（`.private/`）、构建产物、整片 Flash 备份、模拟器存档、硬件日志，以及厂家资料、示例固件和下载的画作图片。
