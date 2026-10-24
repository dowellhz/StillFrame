# Stillframe ESP32 固件仿真环境

此目录用于加载 ESP32-S3 完整 Flash 镜像并执行真实固件，使用乐鑫发布的 ESP Emulator 0.50.0 Beta。支持当前 Mac 的 Apple Silicon 原生版本，引擎已放入 bin，未安装到系统目录。

这与 simulator 目录的界面原型不同：后者不执行 ESP32 指令，不能作为 ROM 测试结果。用户已明确要求优先进行真实固件仿真。

## Stillframe 首版固件（2026-10-24）

现已有自研 ESP-IDF 固件和真实指令测试，详见 [固件说明](../firmware/README.md) 与 [测试记录](../doc/Stillframe固件开发与仿真测试-2026-10-24.md)。正式固件运行方式：

```sh
python3 emulator/run.py firmware/dist/candidate-0.1.1-rc1/Stillframe-0.1.1-rc1-flash.bin --name stillframe --ap-password 12345678 --elf firmware/dist/candidate-0.1.1-rc1/Stillframe-0.1.1-rc1.elf --seconds 30
```

核心安全回归运行 `firmware/tools/test-emulator.sh`。它使用 IDF 在模拟设备内部运行 HTTP 测试服务器，覆盖配置持久化、整帧下载、错误响应、真实网页 OTA 与失败启动回退。屏幕替身仅存在于测试构建中，正式构建没有。宿主端口转发与真实 NAS 访问仍受当前环境限制，屏幕与存储卡仍需实机测试。

## 已验证的范围

2026 年 10 月 24 日，使用项目已有的厂家 WiFi 固件进行真实启动，未修改固件：

- 加载 4 MiB 的完整镜像及 ESP32-S3 内置 ROM。
- 配置 8 MiB 模拟 PSRAM。
- 经 ROM 和固件启动，输出 NeoFrame 初始化日志。
- 执行屏幕初始化函数，日志出现 PON、DRF、POF 和 Display Done。
- 固件日志报告 AP 热点 NeoFrame 和 HTTP 服务器启动完成。

原始日志：[vendor-wifi-first.log](runs/vendor-wifi-first.log)。这些日志仅说明相关固件代码执行到了这里，不证明真实屏幕驱动、电气时序、AP 连接或 HTTP 请求已经验证。

本环境禁止监听本机端口，HTTP 转发启动时报 Operation not permitted。因此浏览器访问固件网页尚未验证。该限制与固件正常启动是两个独立问题。

## 运行厂家固件

在项目根目录执行：

```sh
python3 emulator/run.py --name vendor --seconds 30
```

脚本默认使用 fixtures/vendor-wifi.bin，它是从 doc/Burn firmware over WiFi.zip 解出的副本。原厂 AP 密码依据说明书为 123456789，与计划中的 Stillframe 初始密码 12345678 不同。

脚本把固件复制到 runs/<name>/flash.bin，在工作副本上运行，正常退出时保存 Flash 状态，console.log 保存串口输出。再次使用相同存档名称会继续使用其 Flash 状态；输入原文件不被覆盖。

```sh
# 重建此模拟设备的工作 Flash，清除它此前的配置与运行状态
python3 emulator/run.py --name vendor --fresh --seconds 30
```

异常终止或强制杀进程时不承诺保存最新状态，不能以此代替真实突然断电的存储测试。此封装尚未禁止两个进程同时使用同一个存档，请每个实例使用不同 --name。

## 加载以后开发的 Stillframe 固件

输入需要完整的 Flash 镜像，含二级引导程序、分区表、应用及必要的数据分区；不是单独的应用 bin。构建固件时使用 ESP-IDF 的 merge-bin 输出完整镜像。

```sh
python3 emulator/run.py /完整路径/merged-binary.bin \
  --name stillframe --ap-password 12345678 --seconds 60
```

需要诊断符号时加入同一次构建的应用 ELF：

```sh
python3 emulator/run.py /完整路径/merged-binary.bin \
  --name stillframe --ap-password 12345678 \
  --elf /完整路径/stillframe.elf --seconds 60
```

不同镜像应使用不同存档名称，或显式 --fresh。当前封装仅接收 ESP32-S3、镜像从 0 开始、分区表位于 0x8000 的常规布局。

## 虚拟网络

引擎给固件提供虚拟路由器，默认 SSID myssid、密码 mypassword，可通过 --ssid 和 --wifi-password 修改。它们表示固件作为 STA 时连接的网络；--ap-password 则表示固件自己建立的 AP 密码。

在允许监听本机端口的终端中，可尝试端口转发：

```sh
python3 emulator/run.py --name vendor --http-port 8180 --seconds 300
```

厂家固件日志给出的路径为 /wifi，对应本机访问 http://127.0.0.1:8180/wifi 。此组合的 HTTP 访问尚未实测成功，不应把它当成已验证功能。模拟 AP 不会使电脑真的广播一个 WiFi 热点，也无法用来测试手机的射频连接或信号质量。

## 尚未完成的外设和验收

- GDEP133C02 双驱动芯片的通信与画面模型尚未提供。不能显示固件真实刷出的墨水屏画面，也不能验证 BUSY 时序是否正确。
- MicroSD 卡接口与文件系统持久化尚未针对本板适配或验证。
- 尚未运行我们自己的 Stillframe 固件；目前只有厂家固件启动验证。
- 双 OTA 分区更新、自检回滚、看门狗和 NVS 断电恢复仍需通过专门固件验证，不能以界面动画替代。
- 真实颜色、残影、刷新时间、供电和功耗仍需实机测试。

后续优先完成真实 HTTP 联网验证，再评估屏幕 SPI/QSPI 外设接入。可以保留界面预览作为仿真器的显示前端，但必须由真实固件输出驱动画面，不能独立生成假状态。

## 引擎来源

- [乐鑫 ESP Emulator](https://github.com/espressif/esp-emulator)，Beta，固定版本 0.50.0。
- [对应版本发布页](https://github.com/espressif/esp-emulator/releases/tag/v0.50.0)。
- 下载 macOS arm64 原生包，并核对发布的 SHA256SUMS，见 [校验记录](docs/engine-checksum.txt)。
- [上游使用说明](docs/esp-emulator-upstream.md)、[浏览器版本说明](docs/esp-emulator-browser.md)、[许可文件](docs/esp-emulator-LICENSE)。

另一个选择是 [乐鑫 QEMU](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md)，支持 ESP32-S3 CPU、Flash、PSRAM 等，但其功能表明确不模拟 WiFi 和通用 SPI；因此本项目先验证 ESP Emulator。
