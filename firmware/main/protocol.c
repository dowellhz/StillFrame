#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_task_wdt.h"
#include "http_guard.h"
#include "mbedtls/sha256.h"
#include "rom.h"
#include "stillframe.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
static bool string_field(cJSON *obj, const char *key, char *out, size_t n) {
  cJSON *v = cJSON_GetObjectItemCaseSensitive(obj, key);
  if (!cJSON_IsString(v) || strlen(v->valuestring) >= n)
    return false;
  strlcpy(out, v->valuestring, n);
  return true;
}
esp_err_t sf_parse_sync(const char *body, size_t len, sf_sync *out) {
  memset(out, 0, sizeof(*out));
  cJSON *j = cJSON_ParseWithLength(body, len);
  if (!j)
    return ESP_ERR_INVALID_RESPONSE;
  esp_err_t e = ESP_ERR_INVALID_RESPONSE;
  cJSON *schema = cJSON_GetObjectItemCaseSensitive(j, "schemaVersion"),
        *config = cJSON_GetObjectItemCaseSensitive(j, "config");
  cJSON *interval = cJSON_GetObjectItemCaseSensitive(config, "intervalSeconds"),
        *p = cJSON_GetObjectItemCaseSensitive(j, "photo");
  if (!cJSON_IsNumber(schema) || schema->valuedouble != 1 ||
      !cJSON_IsNumber(interval) || interval->valuedouble < 180 ||
      interval->valuedouble > 86400 ||
      interval->valuedouble != interval->valueint)
    goto done;
  out->interval = interval->valueint;
  // Optional; older servers omit it and the frame keeps its saved value.
  cJSON *offline = cJSON_GetObjectItemCaseSensitive(config, "offlineHotspotSeconds");
  if (cJSON_IsNumber(offline) && offline->valuedouble >= 60 &&
      offline->valuedouble <= 86400 &&
      offline->valuedouble == offline->valueint)
    out->offline_ap = offline->valueint;
  if (cJSON_IsNull(p)) {
    e = ESP_OK;
    goto done;
  }
  if (!cJSON_IsObject(p))
    goto done;
  cJSON *w = cJSON_GetObjectItemCaseSensitive(p, "width"),
        *h = cJSON_GetObjectItemCaseSensitive(p, "height"),
        *b = cJSON_GetObjectItemCaseSensitive(p, "bytes");
  char fmt[64];
  if (!cJSON_IsNumber(w) || w->valuedouble != SF_WIDTH || !cJSON_IsNumber(h) ||
      h->valuedouble != SF_HEIGHT || !cJSON_IsNumber(b) ||
      b->valuedouble != SF_BYTES ||
      !string_field(p, "format", fmt, sizeof(fmt)) ||
      strcmp(fmt, "spectra6-4bpp-row-major") ||
      !string_field(p, "id", out->id, sizeof(out->id)) || !out->id[0] ||
      !string_field(p, "url", out->url, sizeof(out->url)) ||
      !string_field(p, "sha256", out->sha256, sizeof(out->sha256)) ||
      strlen(out->sha256) != 64)
    goto done;
  // Accept same-origin paths only; never send the device token to a supplied
  // external URL.
  if (strncmp(out->url, "/api/v1/device/photos/", 22) ||
      strchr(out->url, '\r') || strchr(out->url, '\n') ||
      strstr(out->url, ".."))
    goto done;
  for (int i = 0; i < 64; i++)
    if (!isxdigit((unsigned char)out->sha256[i]))
      goto done;
  out->has_photo = true;
  e = ESP_OK;
done:
  cJSON_Delete(j);
  return e;
}
esp_err_t sf_validate_frame(const uint8_t *data, size_t len, const char *sha) {
  if (len != SF_BYTES || !sha || strlen(sha) != 64)
    return ESP_ERR_INVALID_SIZE;
  for (size_t i = 0; i < len; i++) {
    unsigned a = data[i] >> 4, b = data[i] & 15;
    if (a > 6 || a == 4 || b > 6 || b == 4)
      return ESP_ERR_INVALID_ARG;
  }
  uint8_t digest[32];
  if (mbedtls_sha256(data, len, digest, 0))
    return ESP_FAIL;
  char hex[65];
  for (int i = 0; i < 32; i++)
    sprintf(hex + i * 2, "%02x", digest[i]);
  return strcasecmp(hex, sha) == 0 ? ESP_OK : ESP_ERR_INVALID_CRC;
}
// Bound every read, permit chunked bodies, and require EOF; never truncate
// silently.
static esp_err_t read_body(esp_http_client_handle_t h, uint8_t *buf, size_t cap,
                           size_t *used) {
  *used = 0;
  int n;
  while (*used < cap) {
    n = esp_http_client_read(h, (char *)buf + *used, cap - *used);
    if (n < 0)
      return ESP_FAIL;
    if (!n)
      break;
    *used += n;
    esp_task_wdt_reset();
  }
  if (*used == cap) {
    char extra;
    n = esp_http_client_read(h, &extra, 1);
    if (n != 0)
      return ESP_ERR_INVALID_SIZE;
  }
  return esp_http_client_is_complete_data_received(h)
             ? ESP_OK
             : ESP_ERR_INVALID_RESPONSE;
}
// Best effort: tell the server what the panel now shows so its dashboard does not
// lag a whole sync interval. The next sync still reports currentPhotoId.
static void report_displayed(const sf_config *cfg, const char *photo,
                             const char *url) {
  cJSON *j = cJSON_CreateObject();
  if (!j)
    return;
  cJSON_AddStringToObject(j, "deviceId", cfg->device_id);
  cJSON_AddStringToObject(j, "photoId", photo);
  const char *v = strstr(url, "?v=");
  if (!v)
    v = strstr(url, "&v=");
  if (v && strspn(v + 3, "0123456789abcdef-") == 36) {
    char version[37];
    memcpy(version, v + 3, 36);
    version[36] = 0;
    cJSON_AddStringToObject(j, "photoVersion", version);
  }
  char *body = cJSON_PrintUnformatted(j);
  cJSON_Delete(j);
  if (!body)
    return;
  esp_http_client_handle_t h =
      sf_http_client(cfg, "/api/v1/device/displayed", 10000);
  if (h) {
    esp_http_client_set_method(h, HTTP_METHOD_POST);
    esp_http_client_set_header(h, "Content-Type", "application/json");
    esp_http_client_set_post_field(h, body, strlen(body));
    esp_task_wdt_reset();
    esp_err_t e = esp_http_client_perform(h);
    int status = e ? 0 : esp_http_client_get_status_code(h);
    esp_task_wdt_reset();
    if (status != 200)
      ESP_LOGW("sync", "display confirmation not accepted (%s, HTTP %d)",
               esp_err_to_name(e), status);
    sf_http_cleanup(h);
  }
  free(body);
}
esp_err_t sf_server_cycle(void) { return sf_server_cycle_due(true, NULL); }
esp_err_t sf_server_cycle_due(bool allow_display, bool *waiting) {
  if (waiting)
    *waiting = false;
  sf_config cfg;
  sf_snapshot(&cfg);
  static char request[64];
  static char for_photo[80];
  // Reuse an id only while the sync response is unresolved. A new sync must
  // read fresh settings even when the previous display or download failed.
  if (!request[0] || strcmp(for_photo, cfg.photo_id)) {
    snprintf(request, sizeof(request), "%08lx%08lx",
             (unsigned long)esp_random(), (unsigned long)esp_random());
    strlcpy(for_photo, cfg.photo_id, sizeof(for_photo));
  }
  cJSON *j = cJSON_CreateObject();
  if (!j)
    return ESP_ERR_NO_MEM;
  cJSON_AddStringToObject(j, "deviceId", cfg.device_id);
  cJSON_AddStringToObject(j, "requestId", request);
  cJSON_AddStringToObject(j, "firmwareVersion", SF_VERSION);
  cJSON_AddStringToObject(j, "boardModel", sf_hardware.board);
  cJSON_AddStringToObject(j, "panelModel", sf_hardware.panel);
  cJSON_AddStringToObject(j, "chipModel", "esp32s3");
  cJSON_AddNumberToObject(j, "otaProtocol", sf_hardware.protocol);
  const esp_partition_t *slot = esp_ota_get_next_update_partition(NULL);
  cJSON_AddNumberToObject(j, "otaSlotBytes", slot ? slot->size : 0);
  char firmware_sha[65];
  bool pending = sf_boot_pending();
  // Do not let the NAS confirm an upgrade before the startup grace period
  // has completed and rollback has been cancelled.
  if (!pending && !sf_running_sha(firmware_sha))
    cJSON_AddStringToObject(j, "firmwareSha256", firmware_sha);
  if (cfg.photo_id[0])
    cJSON_AddStringToObject(j, "currentPhotoId", cfg.photo_id);
  char *body = cJSON_PrintUnformatted(j);
  cJSON_Delete(j);
  if (!body)
    return ESP_ERR_NO_MEM;
  esp_http_client_handle_t h =
      sf_http_client(&cfg, "/api/v1/device/sync", 30000);
  if (!h) {
    free(body);
    return ESP_FAIL;
  }
  esp_http_client_set_method(h, HTTP_METHOD_POST);
  esp_http_client_set_header(h, "Content-Type", "application/json");
  esp_task_wdt_reset();
  esp_err_t e = esp_http_client_open(h, strlen(body));
  esp_task_wdt_reset();
  if (!e) {
    int wrote = esp_http_client_write(h, body, strlen(body));
    if (wrote != (int)strlen(body))
      e = ESP_FAIL;
  }
  free(body);
  char *reply = malloc(16385);
  size_t n = 0;
  sf_sync result;
  if (!reply)
    e = ESP_ERR_NO_MEM;
  esp_task_wdt_reset();
  if (!e && esp_http_client_fetch_headers(h) < 0)
    e = ESP_FAIL;
  if (!e && esp_http_client_get_status_code(h) != 200) {
    ESP_LOGW("sync", "HTTP %d", esp_http_client_get_status_code(h));
    e = ESP_ERR_INVALID_RESPONSE;
  }
  if (!e)
    e = read_body(h, (uint8_t *)reply, 16384, &n);
  if (!e) {
    reply[n] = 0;
    e = sf_parse_sync(reply, n, &result);
  }
  sf_http_cleanup(h);
  if (!e) {
    request[0] = 0;
    cJSON *response = cJSON_ParseWithLength(reply, n);
    if (response) {
      esp_err_t update = sf_remote_update(
          cJSON_GetObjectItemCaseSensitive(response, "firmware"), &cfg);
      if (update)
        ESP_LOGW("sync", "firmware task did not install: %s; continuing photo cycle",
                 esp_err_to_name(update));
      cJSON_Delete(response);
    } else
      e = ESP_ERR_INVALID_RESPONSE;
  }
  free(reply);
  if (e)
    return e;
  request[0] = 0;
  ESP_LOGI("sync", "server config received: interval=%u, photo=%s",
           result.interval, result.has_photo ? result.id : "none");
  cfg.interval = result.interval;
  e = sf_save(&cfg);
  if (e)
    return e;
  if (result.offline_ap && result.offline_ap != sf_offline_ap_seconds()) {
    esp_err_t saved = sf_save_offline_ap(result.offline_ap);
    ESP_LOGI("sync", "offline hotspot delay %u s%s", result.offline_ap,
             saved ? " (not saved)" : "");
  }
  if (!result.has_photo) {
    request[0] = 0;
    sf_message("服务器暂无照片，保留当前画面");
    return ESP_OK;
  }
  char displayed_sha[65];
  sf_photo_sha(displayed_sha);
  if (!strcmp(result.id, cfg.photo_id) &&
      !strcasecmp(result.sha256, displayed_sha)) {
    request[0] = 0;
    sf_message("照片未变化，保留当前画面");
    ESP_LOGI("sync", "photo id and display SHA unchanged; download skipped");
    return ESP_OK;
  }
  if (!sf_display_available()) {
    sf_message(sf_display_recovery_count() >= 3
                   ? "服务器已连接；连续三次刷屏中断，已停止自动刷屏。请检查供电后断电重启。"
                   : "服务器已连接；屏幕通信已暂停，停止重复下载。请检查屏幕连接后重启。");
    return ESP_OK;
  }
  if (!allow_display) {
    if (waiting)
      *waiting = true;
    sf_message("服务器配置已更新，等待屏幕安全刷新时间。");
    return ESP_OK;
  }
  if (sf_memory_fault) {
    sf_message("服务器已连接；PSRAM 不足，无法载入照片。管理和升级仍可使用。");
    return ESP_ERR_NO_MEM;
  }
  h = sf_http_client(&cfg, result.url, 120000);
  if (!h)
    return ESP_FAIL;
  uint8_t *pixels =
      heap_caps_malloc(SF_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!pixels) {
    sf_http_cleanup(h);
    return ESP_ERR_NO_MEM;
  }
  esp_task_wdt_reset();
  e = esp_http_client_open(h, 0);
  esp_task_wdt_reset();
  if (!e && esp_http_client_fetch_headers(h) < 0)
    e = ESP_FAIL;
  if (!e && esp_http_client_get_status_code(h) != 200)
    e = ESP_ERR_INVALID_RESPONSE;
  if (!e)
    e = read_body(h, pixels, SF_BYTES, &n);
  sf_http_cleanup(h);
  if (!e)
    e = sf_validate_frame(pixels, n, result.sha256);
  if (!e) {
    ESP_LOGI("sync", "photo download verified: %u bytes, SHA256 matched",
             (unsigned)n);
    sf_message("正在刷新照片");
    e = sf_display(pixels);
  }
  if (!e) {
    strlcpy(cfg.photo_id, result.id, sizeof(cfg.photo_id));
    e = sf_save(&cfg);
    if (!e) {
      esp_err_t saved_sha = sf_save_photo_sha(result.sha256);
      if (saved_sha)
        ESP_LOGW("sync", "display SHA was not persisted: %s",
                 esp_err_to_name(saved_sha));
      request[0] = 0;
      sf_message("照片已更新");
      ESP_LOGI("sync", "frame verified and displayed");
    }
  }
  free(pixels);
  if (!e)
    report_displayed(&cfg, result.id, result.url);
  return e;
}
