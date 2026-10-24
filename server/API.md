# Stillframe 设备接口 v1

设备配置使用服务器根地址，例如 `http://群晖地址:8484`。以下接口均需 `Authorization: Bearer <设备接入凭证>`；凭证从管理员页面取得，不使用管理员用户名或密码。

## 获取配置和下一张照片

`POST /api/v1/device/sync`

```json
{
  "deviceId": "sf-001122aabbcc",
  "requestId": "本次请求的唯一编号",
  "currentPhotoId": "当前已完整显示的照片 ID，首次可省略",
  "firmwareVersion": "0.1.0",
  "batteryPercent": 85
}
```

- deviceId 固定保存，断电重启后不变，长度 4～100，允许字母、数字、冒号、下划线、连字符。
- requestId 每轮新同步生成一次，同轮请求重试使用原编号。服务器缓存最近一次同编号响应，避免网络重试时跳片。
- currentPhotoId 只报告已经成功显示的照片，不要在下载前或校验失败时提前更新。
- firmwareVersion、batteryPercent 可选。服务器将当前照片报告与“上次下发照片”分开记录。

首次有效请求自动建档，并返回 default 配置。响应示例：

```json
{
  "schemaVersion": 1,
  "registered": true,
  "deviceId": "sf-001122aabbcc",
  "serverTime": "2026-10-24T00:00:00.000Z",
  "config": {
    "intervalSeconds": 3600,
    "categoryIds": ["art"],
    "includeChildren": true,
    "order": "sequence",
    "revision": "配置内容摘要",
    "source": "default"
  },
  "photo": {
    "id": "照片 UUID",
    "title": "向日葵",
    "width": 1200,
    "height": 1600,
    "format": "spectra6-4bpp-row-major",
    "bytes": 960000,
    "sha256": "64 位十六进制 SHA-256",
    "url": "/api/v1/device/photos/照片UUID/display.bin?v=版本UUID"
  },
  "nextRequestAfterSeconds": 3600
}
```

photo 没有候选照片时为 null。此时保留原画面，仍保存新配置并按返回间隔安排下次请求。source 为 default 或 device。配置更新在新一轮请求生效；重发同一个 requestId 是重试，不作为新一轮配置同步。

候选照片只包括启用的照片。categoryIds 空数组表示全部分类；includeChildren 控制是否包含下级分类。顺序播放按创建时间和 ID 排序；随机播放在有多张时排除当前已显示照片。

设备未确认上次下发照片已显示时，服务器优先重发仍有效的待显示照片。若管理员修改了分类，导致待显示照片不再符合条件，则根据新配置重新选择。

## 下载显示数据

请求响应中 photo.url，仍需携带同一个 Authorization 头。url 是相对服务器根地址的路径；保留查询参数 v，确保下载的是响应中 SHA-256 对应的版本。

返回原始二进制，无文件头，共 960000 字节。画面为 1200 × 1600，逐行、从左至右排列，每字节高四位是前一个像素，低四位是后一个像素：

| 颜色 | 四位编码 |
|---|---|
| 黑 | 0 |
| 白 | 1 |
| 黄 | 2 |
| 红 | 3 |
| 蓝 | 5 |
| 绿 | 6 |

不使用编码 4。每行 600 字节。发送到两个屏幕驱动芯片时，分别提取每行前 300 字节和后 300 字节，每个芯片共接收 480000 字节；接口不额外打包为两个连续半屏。

显示前检查 HTTP 状态、长度和 SHA-256。完整下载并校验成功后再初始化屏幕、传输并触发刷新。下载失败保留旧画面，不上报新 currentPhotoId。

旧派生版本暂时保留，所以照片重新处理时，正在下载的版本仍可完成；照片停用或删除后，下载返回 404，设备应重新同步。

## 错误

错误响应为 JSON：`{"error":"原因"}`。

| 状态 | 含义 |
|---|---|
| 400 | 字段、格式或请求无效 |
| 401 | 接入凭证无效 |
| 403 | 设备已停用 |
| 404 | 照片或版本不存在 |
| 503 | 服务器尚未完成管理员初始化 |

短暂网络失败使用退避重试，不能清除本地 WiFi 配置。401／403 应保留配置和画面，并报告错误，不重复创建新设备身份。具体重试时序待固件阶段实现。

## 0.1.4：按设备记录下载

同步响应中的 `photo.url` 现在自动带有 `deviceId` 查询参数；客户端应原样请求这个 URL。旧固件无需改动，旧缓存响应也会补齐归属参数而保持原来的照片和版本。没有 `deviceId` 的旧下载链接仍可使用，但不会猜测归属设备或伪造下载记录。

只有设备已建档、凭证有效、设备启用、图片存在，且 GET 响应完整发送之后才写下载记录。HEAD、认证失败、404、禁用设备和响应中断不记下载。服务器响应完成只说明文件已发送，不能证明设备已校验完成或刷新屏幕成功。

管理员状态接口的设备记录新增：

- `lastDownloadedPhotoId`、`lastDownloadedVersion`、`lastDownloadedAt`：最近一次完整文件发送。
- `downloadHistory`：最近 20 次记录，包含 id、photoId、title、version、at、bytes。照片删除后历史标题与记录保留。
- `currentPhotoReportedAt`：收到设备当前照片报告的时间，不是推测的屏幕刷新时间。
- `currentPhotoVersion`：可选的设备显示版本报告。客户端可在同步 JSON 中附带该字段；未报告时不把最近下载版本推断成已显示版本。

`currentPhotoId` 和下载记录分别保存。完整下载不会修改已报告显示的照片，也不会代替客户端确认。客户端明确报告空字符串时可清除当前照片报告。

管理员图片预览、缩略图和显示数据接口支持 `?v=<版本 UUID>`，用于查看设备实际下载的历史版本。照片编辑生成新版本时，设备卡片与下载记录仍可预览旧版本。设备只报告照片 ID、未报告显示版本时，卡片标记为“设备报告显示”，放大预览说明采用相册当前版本。

## ROM 管理（0.1.6）

管理员 `POST /api/admin/firmwares`，JSON `{filename, data}`；data 为 `data:application/octet-stream;base64,...`。仅接受不超过 5 MiB 的 Stillframe ESP32-S3 应用 bin，解析 ESP-IDF 分段、校验码、内置 SHA-256、项目名、版本和固定位置的硬件描述。拒绝整片 Flash 镜像、缺少硬件信息的旧 ROM、测试 ROM、未知型号和损坏文件。响应 state 增加 firmwares。

管理员 `POST /api/admin/devices/:id/firmware`，JSON `{firmwareId}`，重新检查磁盘文件完整性及设备已报告的 boardModel、panelModel、chipModel、otaProtocol 和 otaSlotBytes。任务仅针对指定设备，已有任务时拒绝覆盖；`DELETE` 可取消尚未完成的任务。取消不能召回已开始写入的升级。

设备 sync 额外上报上述硬件字段、firmwareSha256（运行分区完整应用文件 SHA-256）。返回 firmware 为 null 或 `{id,taskId,version,boardModel,panelModel,chipModel,otaProtocol,bytes,sha256,url,...}`。设备使用原接入凭证 GET 相对 url，禁止跨站重定向。服务器核对设备及任务仍有效。首次升级需已有兼容固件；旧固件未报告硬件型号时禁止群晖远程下发，可先通过设备网页升级或有线刷写兼容版本。

设备 `POST /api/v1/device/firmware-result`：`{deviceId,taskId,status,message}`，status 为 installed（已写入，等待重启确认）或 failed。仅在设备重启后 sync 报告与目标一致的完整应用 SHA-256 时，服务器标记 succeeded；版本字符串或下载完成不足以确认成功。任务状态 queued/offered/succeeded/failed/cancelled 保存在设备档案中，活动记录保留各阶段事件。

硬件型号来自编译目标与 ROM 内嵌描述，不能通过 ESP32 芯片自动探测出物理主板商品型号；接线、电源和实际屏幕仍需真机验收。SHA-256 用于完整性核对，不等于发行者数字签名。当前允许管理员手动选择兼容旧版本；升级包只更新应用分区，不修改引导程序或分区表。

## 显示确认

`POST /api/v1/device/displayed`，设备凭证同 sync：`{deviceId, photoId, photoVersion?}`。设备完成下载、校验并刷新屏幕后立即调用，只更新“设备报告显示”（`currentPhotoId`、`currentPhotoVersion`、报告时间），不选择下一张照片，也不影响待显示照片的重发逻辑；下一次 sync 仍照常携带 `currentPhotoId`。photoVersion 取自下载地址中的 `v`。未知设备 404，停用设备 403。固件 0.1.1-rc12 起使用；旧服务器返回 404 时固件只记录警告。

## 断网自动开热点

sync 返回的 `config` 新增 `offlineHotspotSeconds`（60～86400，默认 600）。默认配置和设备专属配置都可设置；此前保存、没有该字段的配置按 600 下发。固件 0.1.1-rc16 起在联网时接收并写入相框 NVS（键 `offline_ap`），断网后按最后一次收到的值执行：连续连不上家里 Wi-Fi 超过该时间即打开 Stillframe 设置热点，恢复连接后自动关闭。旧固件忽略该字段。

## 照片色彩

照片字段：`color`（natural/standard/vivid）、`chroma`（0.6～1.8）、`brightness`（−20～20）、`contrast`（0.7～1.5）、`renderer`（当前 `lab-1`）。更换 `color` 而未同时给出微调值时套用该预设的值。`POST /api/admin/photos/:id/simulate` 以请求体覆盖照片设置，返回 600×800 模拟 PNG，不保存。`PUT /api/admin/photo-defaults {color}` 设置新上传默认色彩；`POST /api/admin/photos/rerender` 按默认色彩后台重新生成全部照片（202，进行中再次请求 409），进度见 state 的 `rerender`。
