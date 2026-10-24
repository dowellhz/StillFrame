#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include "rom.h"
#include "stillframe.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
extern const char html_start[] asm("_binary_index_html_start");
extern const char html_end[] asm("_binary_index_html_end");
static esp_err_t error(httpd_req_t *r, const char *status, const char *msg) {
  httpd_resp_set_status(r, status);
  return httpd_resp_sendstr(r, msg);
}
static bool authorize(httpd_req_t *r) {
  if (r->method != HTTP_GET && httpd_req_get_hdr_value_len(r, "Origin")) {
    char origin[300], host[260], expected[300];
    if (httpd_req_get_hdr_value_str(r, "Origin", origin, sizeof(origin)) ||
        httpd_req_get_hdr_value_str(r, "Host", host, sizeof(host))) {
      error(r, "403 Forbidden", "请求来源无效");
      return false;
    }
    snprintf(expected, sizeof(expected), "http://%s", host);
    if (strcmp(origin, expected)) {
      error(r, "403 Forbidden", "请从相框自己的页面操作");
      return false;
    }
  }
  sf_config c;
  sf_snapshot(&c);
  char got[160], plain[80], want[160] = "Basic ";
  size_t len;
  snprintf(plain, sizeof(plain), "admin:%s", c.ap_password);
  mbedtls_base64_encode((uint8_t *)want + 6, sizeof(want) - 6, &len,
                        (uint8_t *)plain, strlen(plain));
  want[6 + len] = 0;
  if (httpd_req_get_hdr_value_str(r, "Authorization", got, sizeof(got)) ==
      ESP_OK) {
    unsigned diff = 0;
    size_t a = strlen(got), b = strlen(want);
    if (a == b) {
      for (size_t i = 0; i < a; i++)
        diff |= got[i] ^ want[i];
      if (!diff)
        return true;
    }
  }
  httpd_resp_set_hdr(r, "WWW-Authenticate", "Basic realm=\"Stillframe\"");
  error(r, "401 Unauthorized", "请使用 admin 和设置热点密码登录");
  return false;
}
static bool auth(httpd_req_t *r) { return authorize(r); }
static esp_err_t home(httpd_req_t *r) {
  if (!auth(r))
    return ESP_OK;
  httpd_resp_set_type(r, "text/html; charset=utf-8");
  httpd_resp_set_hdr(r, "Cache-Control", "no-store");
  return httpd_resp_send(r, html_start, html_end - html_start);
}
static char *body(httpd_req_t *r, size_t max) {
  if (r->content_len <= 0 || r->content_len > max)
    return NULL;
  char *p = malloc(r->content_len + 1);
  if (!p)
    return NULL;
  size_t used = 0;
  int64_t deadline = esp_timer_get_time() + 10000000;
  while (used < r->content_len) {
    int n = httpd_req_recv(r, p + used, r->content_len - used);
    if (n <= 0 || esp_timer_get_time() > deadline) {
      free(p);
      return NULL;
    }
    used += n;
  }
  p[used] = 0;
  return p;
}
static esp_err_t status(httpd_req_t *r) {
  if (!auth(r))
    return ESP_OK;
  sf_config c;
  sf_snapshot(&c);
  cJSON *j = cJSON_CreateObject();
  cJSON_AddStringToObject(j, "deviceId", c.device_id);
  cJSON_AddStringToObject(j, "firmwareVersion", SF_VERSION);
  cJSON_AddBoolToObject(j, "configured", c.configured);
  cJSON_AddBoolToObject(j, "connected", sf_connected);
  cJSON_AddBoolToObject(j, "ap", sf_ap);
  cJSON_AddBoolToObject(j, "sd", sf_sd);
  cJSON_AddBoolToObject(j, "storageFault", sf_storage_fault);
  cJSON_AddBoolToObject(j, "memoryFault", sf_memory_fault);
  cJSON_AddBoolToObject(j, "safeMode", sf_safe_mode_active());
  cJSON_AddBoolToObject(j, "configPending", sf_config_pending);
  cJSON_AddBoolToObject(j, "displayFault", sf_display_error() != ESP_OK);
  cJSON_AddBoolToObject(j, "displayMaintenance", sf_display_maintenance());
  cJSON_AddStringToObject(j, "displayError",
                          esp_err_to_name(sf_display_error()));
  cJSON_AddNumberToObject(j, "displayRecoveryCount",
                          sf_display_recovery_count());
  cJSON_AddStringToObject(j, "ssid", c.ssid);
  cJSON_AddStringToObject(j, "server", c.server);
  cJSON_AddBoolToObject(j, "hasToken", c.token[0] != 0);
  cJSON_AddBoolToObject(j, "local", c.local);
  cJSON_AddNumberToObject(j, "intervalSeconds", c.interval);
  cJSON_AddBoolToObject(j, "random", c.random);
  cJSON_AddStringToObject(j, "category", c.category);
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  cJSON_AddStringToObject(j, "message", sf_status);
  xSemaphoreGive(sf_lock);
  char *s = cJSON_PrintUnformatted(j);
  cJSON_Delete(j);
  if (!s)
    return ESP_ERR_NO_MEM;
  httpd_resp_set_type(r, "application/json");
  httpd_resp_set_hdr(r, "Cache-Control", "no-store");
  esp_err_t e = httpd_resp_sendstr(r, s);
  free(s);
  return e;
}
static bool field(cJSON *j, const char *key, char *dest, size_t size,
                  bool keep_empty) {
  cJSON *v = cJSON_GetObjectItemCaseSensitive(j, key);
  if (!v)
    return true;
  if (!cJSON_IsString(v) || strlen(v->valuestring) >= size)
    return false;
  if (!keep_empty || v->valuestring[0])
    strlcpy(dest, v->valuestring, size);
  return true;
}
static esp_err_t configure(httpd_req_t *r) {
  if (!auth(r))
    return ESP_OK;
  if (sf_storage_fault)
    return error(r, "503 Service Unavailable",
                 "配置存储异常，原数据未清空，请通过固件修复或有线救援恢复");
  if (sf_restarting)
    return error(r, "409 Conflict", "升级完成，即将重启，请重启后再保存配置");
  char *s = body(r, 4096);
  if (!s)
    return error(r, "400 Bad Request", "配置内容无效");
  cJSON *j = cJSON_Parse(s);
  free(s);
  if (!j)
    return error(r, "400 Bad Request", "JSON 无效");
  sf_config c;
  sf_snapshot(&c);
  char old_ssid[33];
  strlcpy(old_ssid, c.ssid, sizeof(old_ssid));
  // Report the first rejected field so the page can say exactly what to fix.
  const char *why = NULL;
#define REJECT(text)                                                           \
  do {                                                                         \
    if (!why)                                                                  \
      why = (text);                                                            \
  } while (0)
  if (!field(j, "ssid", c.ssid, sizeof(c.ssid), false))
    REJECT("Wi-Fi 名称过长（最多 32 字节）");
  if (!field(j, "wifiPassword", c.wifi_password, sizeof(c.wifi_password), true))
    REJECT("Wi-Fi 密码过长（最多 64 个字符）");
  if (!field(j, "server", c.server, sizeof(c.server), false))
    REJECT("相册服务器地址过长");
  if (!field(j, "token", c.token, sizeof(c.token), true))
    REJECT("相框连接凭证过长");
  if (!field(j, "apPassword", c.ap_password, sizeof(c.ap_password), true))
    REJECT("热点密码过长（最多 63 个字符）");
  if (!field(j, "category", c.category, sizeof(c.category), false))
    REJECT("播放分类无效");
  cJSON *wifi_pass = cJSON_GetObjectItemCaseSensitive(j, "wifiPassword");
  if (strcmp(old_ssid, c.ssid) && cJSON_IsString(wifi_pass) &&
      !wifi_pass->valuestring[0])
    c.wifi_password[0] = 0;
  for (size_t i = 0; i < strlen(c.token); i++)
    if ((unsigned char)c.token[i] < 33 || (unsigned char)c.token[i] > 126)
      REJECT("相框连接凭证含有空格或无效字符，请从服务器设置页重新复制");
  cJSON *local = cJSON_GetObjectItemCaseSensitive(j, "local"),
        *interval = cJSON_GetObjectItemCaseSensitive(j, "intervalSeconds"),
        *random = cJSON_GetObjectItemCaseSensitive(j, "random");
  if (local) {
    if (!cJSON_IsBool(local))
      REJECT("播放来源无效");
    else
      c.local = cJSON_IsTrue(local);
  }
  if (random) {
    if (!cJSON_IsBool(random))
      REJECT("播放顺序无效");
    else
      c.random = cJSON_IsTrue(random);
  }
  if (interval) {
    if (!cJSON_IsNumber(interval) || interval->valuedouble < 180 ||
        interval->valuedouble > 86400 ||
        interval->valueint != interval->valuedouble)
      REJECT("刷新间隔须为 180～86400 秒");
    else
      c.interval = interval->valueint;
  }
  cJSON_Delete(j);
  size_t alen = strlen(c.ap_password);
  if (alen < 8 || alen > 63)
    REJECT("热点密码须为 8～63 个字符");
  for (size_t i = 0; i < alen; i++)
    if (c.ap_password[i] < 32 || c.ap_password[i] > 126)
      REJECT("热点密码只能使用英文字母、数字和常用符号");
  size_t wifi_len = strlen(c.wifi_password);
  if (wifi_len && wifi_len < 8)
    REJECT("Wi-Fi 密码至少 8 位；开放网络请留空");
  if (wifi_len == 64)
    for (size_t i = 0; i < wifi_len; i++)
      if (!isxdigit((unsigned char)c.wifi_password[i]))
        REJECT("64 位 Wi-Fi 密码只能是十六进制字符");
  size_t end = strlen(c.server);
  while (end && c.server[end - 1] == '/')
    c.server[--end] = 0;
  if (!c.local) {
    if (!c.ssid[0])
      REJECT("请填写路由器的 Wi-Fi 名称");
    if (strncmp(c.server, "http://", 7) && strncmp(c.server, "https://", 8))
      REJECT("相册服务器地址须以 http:// 或 https:// 开头");
    if (!c.token[0])
      REJECT("请填写相框连接凭证（在相册服务器「设置」页面复制）");
  }
  for (size_t i = 0; i < strlen(c.server); i++)
    if ((unsigned char)c.server[i] <= 32 || c.server[i] == '@' ||
        c.server[i] == '#' || c.server[i] == '?')
      REJECT("相册服务器地址不能包含空格、@、# 或 ?");
#undef REJECT
  if (why)
    return error(r, "400 Bad Request", why);
  if (sf_queue_config(&c))
    return error(r, "409 Conflict", "正在保存配置，请稍候");
  return error(r, "202 Accepted",
               "正在检查并保存配置；热点关闭后，请回到家庭 WiFi 访问设备");
}
static esp_err_t refresh(httpd_req_t *r) {
  if (!auth(r))
    return ESP_OK;
  sf_refresh_requested = true;
  return httpd_resp_sendstr(r, "已请求刷新");
}
static void reboot(void *arg) {
  vTaskDelay(pdMS_TO_TICKS(1000));
  sf_display_off();
  sf_prepare_ota_reboot();
  esp_restart();
}
static esp_err_t update(httpd_req_t *r) {
  // Firmware replacement is privileged even during first-time provisioning.
  // The initial credentials are admin and the AP password printed on screen.
  if (!authorize(r))
    return ESP_OK;
  if (sf_restarting || sf_config_pending || sf_boot_pending())
    return error(r, "409 Conflict", "设备正在保存配置或准备重启，请稍后重试");

  if (xSemaphoreTake(sf_operation, 0) != pdTRUE)
    return error(r, "409 Conflict", "设备正在工作，请稍后升级");
  if (!sf_begin_update()) {
    xSemaphoreGive(sf_operation);
    return error(r, "409 Conflict", "设备正在保存配置或升级，请稍候");
  }
  const esp_partition_t *part = esp_ota_get_next_update_partition(NULL);
  esp_ota_handle_t handle = 0;
  esp_err_t e = ESP_FAIL;
  char expected[65];
  bool started = false, success = false;
  uint8_t *buf = NULL;
  mbedtls_sha256_context hash;
  mbedtls_sha256_init(&hash);
  mbedtls_sha256_starts(&hash, 0);
  if (!part || r->content_len < SF_ROM_HEADER_BYTES ||
      r->content_len > part->size ||
      httpd_req_get_hdr_value_str(r, "X-SHA256", expected, sizeof(expected)) !=
          ESP_OK ||
      strlen(expected) != 64)
    goto done;
  buf = malloc(4096);
  if (!buf)
    goto done;
  size_t used = 0;
  int64_t upload_deadline = esp_timer_get_time() + 300000000LL;
  while (used < r->content_len) {
    if (esp_timer_get_time() > upload_deadline)
      goto done;
    int n = httpd_req_recv(r, (char *)buf,
                           4096 < r->content_len - used
                               ? 4096
                               : r->content_len - used);
    if (n <= 0)
      goto done;
    if (!started) {
      // The first recv may be short: collect enough bytes for both image and
      // app descriptors.
      size_t first = n, need = SF_ROM_HEADER_BYTES;
      while (first < need) {
        if (esp_timer_get_time() > upload_deadline)
          goto done;
        n = httpd_req_recv(r, (char *)buf + first, need - first);
        if (n <= 0)
          goto done;
        first += n;
      }
      n = first;
      if (!sf_rom_header_valid(buf, n))
        goto done;
      e = esp_ota_begin(part, OTA_WITH_SEQUENTIAL_WRITES, &handle);
      if (e)
        goto done;
      started = true;
    }
    if (mbedtls_sha256_update(&hash, buf, n))
      goto done;
    if (esp_ota_write(handle, buf, n) != ESP_OK)
      goto done;
    used += n;
  }
  uint8_t digest[32];
  char actual[65];
  mbedtls_sha256_finish(&hash, digest);
  for (int i = 0; i < 32; i++)
    sprintf(actual + i * 2, "%02x", digest[i]);
  if (strcasecmp(actual, expected))
    goto done;
  e = esp_ota_end(handle);
  started = false;
  if (!e)
    e = esp_ota_set_boot_partition(part);
  success = e == ESP_OK;
done:
  if (!success)
    e = ESP_FAIL;
  if (started)
    esp_ota_abort(handle);
  free(buf);
  mbedtls_sha256_free(&hash);
  sf_restarting = success;
  xSemaphoreGive(sf_operation);
  if (e)
    return error(
        r, "400 Bad Request",
        "升级失败，继续使用当前版本。请上传 Stillframe 应用 bin 并核对校验值");
  httpd_resp_sendstr(r, "升级已写入备用分区，即将重启");
  if (xTaskCreate(reboot, "reboot", 2048, NULL, 4, NULL) != pdPASS) {
    sf_display_off();
    sf_prepare_ota_reboot();
    esp_restart();
  }
  return ESP_OK;
}
static esp_err_t local_api(httpd_req_t *r) {
  if (!auth(r))
    return ESP_OK;
  if (sf_storage_fault)
    return error(r, "503 Service Unavailable",
                 "恢复模式下暂停本地相册访问，原文件未修改");
  if (xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) != pdTRUE)
    return error(r, "409 Conflict", "设备正忙");
  esp_err_t e = sf_local_api(r);
  if (e == ESP_FAIL || e == ESP_ERR_NOT_FOUND)
    sf_local_unmount();
  xSemaphoreGive(sf_operation);
  return e;
}
esp_err_t sf_web_start(void) {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 12288;
  cfg.max_uri_handlers = 12;
  cfg.recv_wait_timeout = 15;
  cfg.send_wait_timeout = 15;
  httpd_handle_t h;
  esp_err_t e = httpd_start(&h, &cfg);
  if (e)
    return e;
  const httpd_uri_t routes[] = {
      {.uri = "/", .method = HTTP_GET, .handler = home},
      {.uri = "/api/status", .method = HTTP_GET, .handler = status},
      {.uri = "/api/config", .method = HTTP_POST, .handler = configure},
      {.uri = "/api/refresh", .method = HTTP_POST, .handler = refresh},
      {.uri = "/api/update", .method = HTTP_POST, .handler = update},
      {.uri = "/api/local", .method = HTTP_GET, .handler = local_api},
      {.uri = "/api/local", .method = HTTP_POST, .handler = local_api},
      {.uri = "/api/local/bin", .method = HTTP_POST, .handler = local_api},
      {.uri = "/api/local/bin", .method = HTTP_GET, .handler = local_api}};
  for (unsigned i = 0; i < sizeof(routes) / sizeof(routes[0]); i++) {
    e = httpd_register_uri_handler(h, &routes[i]);
    if (e)
      return e;
  }
  return ESP_OK;
}
