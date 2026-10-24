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

## 避坑指南

2026-10-24 首次上实体板时踩过的坑。格式：现象 → 原因 → 做法。

### 硬件（ESP32-133C02-IL rev 2.0）

- **每约 11 秒掉电复位**（串口 `E BOD: Brownout detector was triggered`），热点时有时无，屏幕刷成一片浅黄。→ 给 GPIO13 开内部下拉，约 10 秒后供电跌破 2.44 V。本板 GPIO13 接在供电相关电路上。→ **GPIO12、GPIO13 一律不要配置**。浅黄画面只是刷屏被复位打断，不是屏幕电流或数据问题。
- **SW2～SW4 的极性和厂家手册相反**。手册写“高电平触发”，实测 GPIO12/13/14 空闲都是高电平（外部上拉），所以按下是低电平。按高电平判断时，开机 5 秒就会被当成“长按 SW4”，热点被重启，手机掉线。
- **ESP32-S3 掉电阈值 level 7 是 2.44 V，是最低一档**，不是最严格的一档。在 level 7 下仍然掉电，说明电压是真的掉下去了，不要去“调低阈值”。
- 屏幕 BUSY_N 在转接板上有 2 kΩ 上拉，接在屏幕 3.3 V（受 GPIO45 控制）上，屏幕通电时不会浮空。
- 不要带电插拔屏幕排线，断电后再接。

### 调试方法

- **复位时间固定，就先怀疑固件做了什么**，不是随机的负载。按这个顺序排除：同一电源跑原厂 WiFi 固件（`doc/Burn firmware over WiFi.zip`，热点 NeoFrame），稳定就说明硬件和电源没问题 → 不启动 WiFi → 跳过整块初始化 → 再逐块加回 → 逐个引脚单独测试。
- 掉电后的 `Saved PC` 指向掉电中断处理函数本身，看不出原因。
- **用 `ELF file SHA256` 判断板子上跑的是哪次编译**。日志里的 `Compile time` 在只改 main 代码时不会更新。
- 版本号有两处：`firmware/CMakeLists.txt` 的 `PROJECT_VER` 写进应用描述，`main/stillframe.h` 的 `SF_VERSION` 用于日志和接口。升版本时两处都要改。
- 串口是原生 USB（`/dev/cu.usbmodem*`）。抓日志脚本切换 RTS 会复位芯片，**想看现场状态时不要复位**。原厂 Arduino 固件后半段日志走另一个 UART，USB 上看不到；可以用 `system_profiler SPAirPortDataType` 扫热点来确认它在工作。
- 刷屏中断计数和 3 分钟刷新保护存在 RTC 内存里，软件复位和 esptool 复位都不会清掉，**拔电重插才会清零**。
- 厂家示例 zip 的文件名是 GBK 编码，macOS `unzip` 会报 `Illegal byte sequence`，改用 Python 按 GBK 解码文件名。厂家示例里的 `vTaskDelay(pdMS_TO_TICKS(1))` 在 100 Hz 时钟下等于不延时。
- ESP-IDF 里 `ERR_TCP_TRANSPORT_CONNECTION_TIMEOUT` 的值是 0，`CLOSED_BY_FIN` 才是 -1。自己包装传输层时，不要把 0 当成连接关闭。

### 配网与使用

- **服务器模式下“相框连接凭证”必填**，要从群晖 Stillframe「设置」页复制，不是群晖的登录密码。WiFi 必须是 2.4 GHz。
- **配网成功后热点会自动关闭**，这是设计行为。之后在家里网络访问相框：`arp -an | grep 44:b1:76` 能查到 IP，网页登录名 admin，密码是热点密码。
- **这块板子没有焊 SW2/SW3/SW4**，只有 SW6（Reset）和 SW7（Power），“长按 SW4 开热点”用不了。固件 rc15 起改为：连续连不上家里 Wi‑Fi 超过一段时间（默认 10 分钟，群晖 0.1.8 的默认配置或设备配置里可改）就自动打开设置热点，恢复连接后自动关闭；有手机连着热点时暂停重连家里 Wi‑Fi，避免热点跳信道把手机踢掉。
- 板上蓝灯是 USB‑C 旁的电源指示灯，通电常亮，固件控制不了。
- 相框刷新后，群晖的“设备报告显示”曾经慢一张：原因是只在下一次同步时才上报。固件 rc12 加群晖 0.1.7 改为刷完立即确认，两边都要升级。
- 已知问题：OTA 升级或手动刷新后约 3 分钟会多换一张照片，日常每小时的节奏不受影响。
- 最短刷新间隔是 180 秒，13.3 寸六色屏全刷大约需要 27 秒。
- rc14 起两次刷新之间自动浅睡眠（CPU 40～160 MHz，WiFi 保持连接），网页第一次访问会慢 1～2 秒；刷屏、同步、OTA、SD 写入期间禁止睡眠。ESP32‑S3 的原生 USB 在浅睡眠中不工作：插着电脑时固件保持清醒（`CONFIG_USJ_NO_AUTO_LS_ON_CONNECTION`），开机前十几秒也强制清醒，否则电脑来不及枚举 USB，串口会“消失”。

### 升级

- 网页 HTTP OTA 等同于设置页的“上传固件”：

  ```sh
  curl -u admin:<热点密码> -H "X-SHA256: $(shasum -a 256 app.bin | cut -d' ' -f1)" \
    --data-binary @app.bin http://<相框IP>/api/update
  ```

  新固件要等第一个刷新周期完成才会标记有效，在那之前重启会自动回滚。
- 诊断用的配置项（`CONFIG_SF_PANEL_MAINTENANCE`、`CONFIG_SF_OPEN_AP_DIAGNOSTIC`，使用 `sdkconfig.maintenance`）会关闭屏幕电源或开放热点，**只能用于诊断，不能发布**。

### 群晖

- DSM 不允许套件自动在桌面放图标。安装后从「主菜单」把 Stillframe 拖到桌面。图标要提供 16～256 各个尺寸，否则主菜单可能不显示。
- 六色墨水实际颜色比理想色板暗淡得多，照片默认会做“鲜艳”增强。可以逐张改成“标准”或“原样”。

### 仓库

- `.gitignore` 里不带前导 `/` 的 `tools/` 会把 `firmware/tools/` 也排除掉，只针对根目录的规则要写成 `/tools/`。
- HTTPS 推送几 MB 时可能被远端断开，执行 `git config http.postBuffer 157286400` 后重推即可。

## 未纳入仓库

工具链（`.tools/`）、群晖联调凭证与记录（`.private/`）、构建产物、整片 Flash 备份、模拟器存档、硬件日志，以及厂家资料、示例固件和下载的画作图片。
