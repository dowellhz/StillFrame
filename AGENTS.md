# Agent notes

## 打包与交付

- **群晖 SPK 打包完成后，立即复制到 `~/Downloads/`**，并核对 SHA-256 与 `server/dist/*.spk.sha256` 一致：

  ```sh
  cd server && npm test && python3 scripts/build-spk.py
  cp dist/Stillframe-<版本>.spk ~/Downloads/
  shasum -a 256 ~/Downloads/Stillframe-<版本>.spk
  ```

- 群晖版本号改 6 处并保持一致：`src/main.mjs`、`src/app.mjs`（/api/health）、`scripts/build-spk.py`、`synology/INFO`、`package.json`、`package-lock.json`（两处）。
- 固件版本号改 2 处：`firmware/main/stillframe.h` 的 `SF_VERSION` 与 `firmware/CMakeLists.txt` 的 `PROJECT_VER`。打包到 `firmware/dist/candidate-<版本>/`（app.bin、flash.bin、elf、SHA256SUMS），并确认 app.bin 中没有测试入口字符串。
- 已经装到设备或群晖上的版本号不复用；有改动就升号。

## 硬件约束（ESP32-133C02-IL rev 2.0）

- 不要配置 GPIO12、GPIO13：GPIO13 开内部下拉约 10 秒后会掉电复位。本板未焊 SW2～SW4。
- 屏幕排线不可带电插拔。详见根目录 README 的“避坑指南”。

## 设备升级

- 优先用设备网页 HTTP OTA（`curl -u admin:<热点密码> -H "X-SHA256: …" --data-binary @app.bin http://<相框IP>/api/update`），返回 409 时稍后重试。
- 有线刷写会覆盖原厂固件；原厂备份在 `firmware/backups/`（不进仓库）。

## 仓库

- `.private/` 含真实群晖凭证，绝不提交；推送前扫描凭证。
