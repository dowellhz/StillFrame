#include "rom.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "http_guard.h"
#include "mbedtls/sha256.h"
#include "nvs.h"
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
const sf_hardware_descriptor sf_hardware __attribute__((
    used, section(".rodata_custom_desc"))) = {.magic = "STILLFRAME-HW1",
                                              .board = "ESP32-133C02-IL",
                                              .panel = "GDEP133C02",
                                              .protocol = 1,
                                              .width = SF_WIDTH,
                                              .height = SF_HEIGHT,
#if defined(CONFIG_SF_TEST_MODE) || defined(CONFIG_SF_RUNTIME_TEST) ||         \
    defined(CONFIG_SF_TEST_PANIC)
                                              .flags = 1
#else
                                              .flags = 0
#endif
};
_Static_assert(sizeof(sf_hardware_descriptor) == 84,
               "ROM metadata layout changed");
bool sf_rom_header_valid(const uint8_t *buf, size_t len) {
  if (len < SF_ROM_HEADER_BYTES)
    return false;
  esp_image_header_t h;
  esp_app_desc_t a;
  sf_hardware_descriptor hw;
  memcpy(&h, buf, sizeof(h));
  memcpy(&a, buf + 32, sizeof(a));
  memcpy(&hw, buf + 288, sizeof(hw));
  if (h.magic != ESP_IMAGE_HEADER_MAGIC || h.chip_id != 9 ||
      h.hash_appended != 1 || a.magic_word != ESP_APP_DESC_MAGIC_WORD ||
      memcmp(a.project_name, "Stillframe", 11))
    return false;
  if (memcmp(hw.magic, sf_hardware.magic, 16) ||
      memcmp(hw.board, sf_hardware.board, 32) ||
      memcmp(hw.panel, sf_hardware.panel, 24) || hw.protocol != 1 ||
      hw.width != SF_WIDTH || hw.height != SF_HEIGHT)
    return false;
#ifndef CONFIG_SF_TEST_MODE
  if (hw.flags)
    return false;
#endif
  return true;
}
static void hex(const uint8_t digest[32], char out[65]) {
  for (int i = 0; i < 32; i++)
    sprintf(out + i * 2, "%02x", digest[i]);
}
esp_err_t sf_running_sha(char out[65]) {
  static char cached[65];
  if (cached[0]) {
    memcpy(out, cached, 65);
    return ESP_OK;
  }
  const esp_partition_t *p = esp_ota_get_running_partition();
  esp_image_header_t h;
  if (!p || esp_partition_read(p, 0, &h, sizeof(h)) || h.magic != 0xe9 ||
      !h.segment_count || h.segment_count > 16)
    return ESP_FAIL;
  size_t off = 24;
  for (unsigned i = 0; i < h.segment_count; i++) {
    esp_image_segment_header_t seg;
    if (off + 8 > p->size || esp_partition_read(p, off, &seg, 8))
      return ESP_FAIL;
    off += 8;
    if (seg.data_len > p->size - off)
      return ESP_FAIL;
    off += seg.data_len;
  }
  size_t bytes = ((off + 1 + 15) / 16) * 16 + (h.hash_appended ? 32 : 0);
  if (bytes > p->size)
    return ESP_FAIL;
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  uint8_t buf[2048], digest[32];
  esp_err_t e = ESP_OK;
  for (size_t pos = 0; pos < bytes; pos += sizeof(buf)) {
    size_t n = bytes - pos < sizeof(buf) ? bytes - pos : sizeof(buf);
    if (esp_partition_read(p, pos, buf, n) ||
        mbedtls_sha256_update(&ctx, buf, n)) {
      e = ESP_FAIL;
      break;
    }
    esp_task_wdt_reset();
  }
  if (!e) {
    mbedtls_sha256_finish(&ctx, digest);
    hex(digest, cached);
    memcpy(out, cached, 65);
  }
  mbedtls_sha256_free(&ctx);
  return e;
}
static const char *str(cJSON *j, const char *key) {
  cJSON *v = cJSON_GetObjectItemCaseSensitive(j, key);
  return cJSON_IsString(v) ? v->valuestring : NULL;
}
static void report(const sf_config *cfg, const char *task, bool installed) {
  cJSON *j = cJSON_CreateObject();
  if (!j)
    return;
  cJSON_AddStringToObject(j, "deviceId", cfg->device_id);
  cJSON_AddStringToObject(j, "taskId", task);
  cJSON_AddStringToObject(j, "status", installed ? "installed" : "failed");
  cJSON_AddStringToObject(j, "message",
                          installed ? "备用分区已验证，等待重启确认"
                                    : "设备校验、下载或写入失败，保留原版本");
  char *body = cJSON_PrintUnformatted(j);
  cJSON_Delete(j);
  if (!body)
    return;
  esp_http_client_handle_t h =
      sf_http_client(cfg, "/api/v1/device/firmware-result", 15000);
  if (h) {
    esp_http_client_set_method(h, HTTP_METHOD_POST);
    esp_http_client_set_header(h, "Content-Type", "application/json");
    esp_http_client_set_post_field(h, body, strlen(body));
    esp_task_wdt_reset();
    esp_http_client_perform(h);
    esp_task_wdt_reset();
    sf_http_cleanup(h);
  }
  free(body);
}
esp_err_t sf_remote_update(cJSON *offer, const sf_config *cfg) {
  if (!cJSON_IsObject(offer))
    return ESP_OK;
  const char *task = str(offer, "taskId"), *url = str(offer, "url"),
             *sha = str(offer, "sha256"), *board = str(offer, "boardModel"),
             *panel = str(offer, "panelModel"), *chip = str(offer, "chipModel");
  cJSON *b = cJSON_GetObjectItemCaseSensitive(offer, "bytes"),
        *protocol = cJSON_GetObjectItemCaseSensitive(offer, "otaProtocol");
  const esp_partition_t *p = esp_ota_get_next_update_partition(NULL);
  if (sf_boot_pending())
    return ESP_OK;
  bool task_ok = task && strlen(task) == 36;
  if (!task_ok || !url || strlen(url) > 511 ||
      strncmp(url, "/api/v1/device/firmware/", 24) || strstr(url, "..") ||
      strchr(url, '\r') || strchr(url, '\n') || !sha || strlen(sha) != 64 ||
      !board || strcmp(board, sf_hardware.board) || !panel ||
      strcmp(panel, sf_hardware.panel) || !chip || strcmp(chip, "esp32s3") ||
      !cJSON_IsNumber(protocol) || protocol->valuedouble != 1 ||
      !cJSON_IsNumber(b) || b->valuedouble != b->valueint ||
      b->valueint < SF_ROM_HEADER_BYTES || !p || b->valueint > p->size ||
      sf_storage_fault) {
    if (task_ok)
      report(cfg, task, false);
    return ESP_ERR_INVALID_ARG;
  }
  for (int i = 0; i < 64; i++)
    if (!isxdigit((unsigned char)sha[i])) {
      report(cfg, task, false);
      return ESP_ERR_INVALID_ARG;
    }
  char current[65];
  if (!sf_running_sha(current) && !strcasecmp(current, sha))
    return ESP_OK;
  // One attempt per task survives power loss and rollback. A failed image can
  // never create an endless remote update/reboot loop.
  nvs_handle_t nvs;
  esp_err_t e = nvs_open("sf_ota", NVS_READWRITE, &nvs);
  if (e)
    return e;
  char previous[40] = {0};
  size_t prevsize = sizeof(previous);
  nvs_get_str(nvs, "attempt", previous, &prevsize);
  if (!strcmp(previous, task)) {
    nvs_close(nvs);
    report(cfg, task, false);
    return ESP_ERR_INVALID_STATE;
  }
  if (!sf_begin_update()) {
    nvs_close(nvs);
    return ESP_ERR_INVALID_STATE;
  }
  e = nvs_set_str(nvs, "attempt", task);
  if (!e)
    e = nvs_commit(nvs);
  nvs_close(nvs);
  if (e) {
    sf_restarting = false;
    return e;
  }
  sf_message("正在下载并校验 ROM，请保持供电");
  esp_http_client_handle_t h = sf_http_client(cfg, url, 300000);
  esp_ota_handle_t ota = 0;
  bool started = false;
  size_t used = 0;
  uint8_t *buf = malloc(4096), digest[32];
  char actual[65];
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  if (!h || !buf) {
    e = ESP_ERR_NO_MEM;
    goto done;
  }
  esp_task_wdt_reset();
  e = esp_http_client_open(h, 0);
  esp_task_wdt_reset();
  if (e)
    goto done;
  if (esp_http_client_fetch_headers(h) != b->valueint ||
      esp_http_client_get_status_code(h) != 200) {
    e = ESP_ERR_INVALID_RESPONSE;
    goto done;
  }
  int64_t deadline = esp_timer_get_time() + 300000000LL;
  while (used < (size_t)b->valueint) {
    if (esp_timer_get_time() > deadline) {
      e = ESP_ERR_TIMEOUT;
      goto done;
    }
    size_t cap = b->valueint - used < 4096 ? b->valueint - used : 4096;
    int count = esp_http_client_read(h, (char *)buf, cap);
    if (count <= 0) {
      e = ESP_FAIL;
      goto done;
    }
    if (!started) {
      size_t first = count;
      while (first < SF_ROM_HEADER_BYTES) {
        if (esp_timer_get_time() > deadline) {
          e = ESP_ERR_TIMEOUT;
          goto done;
        }
        esp_task_wdt_reset();
        count = esp_http_client_read(h, (char *)buf + first,
                                     SF_ROM_HEADER_BYTES - first);
        if (count <= 0) {
          e = ESP_FAIL;
          goto done;
        }
        first += count;
      }
      count = first;
      if (!sf_rom_header_valid(buf, count)) {
        e = ESP_ERR_INVALID_ARG;
        goto done;
      }
      e = esp_ota_begin(p, OTA_WITH_SEQUENTIAL_WRITES, &ota);
      if (e)
        goto done;
      started = true;
    }
    if (mbedtls_sha256_update(&ctx, buf, count) ||
        (e = esp_ota_write(ota, buf, count))) {
      e = ESP_FAIL;
      goto done;
    }
    used += count;
    esp_task_wdt_reset();
  }
  if (!esp_http_client_is_complete_data_received(h)) {
    e = ESP_ERR_INVALID_RESPONSE;
    goto done;
  }
  mbedtls_sha256_finish(&ctx, digest);
  hex(digest, actual);
  if (strcasecmp(sha, actual)) {
    e = ESP_ERR_INVALID_CRC;
    goto done;
  }
  e = esp_ota_end(ota);
  started = false;
  if (!e)
    e = esp_ota_set_boot_partition(p);
done:
  if (started)
    esp_ota_abort(ota);
  if (h)
    sf_http_cleanup(h);
  free(buf);
  mbedtls_sha256_free(&ctx);
  report(cfg, task, e == ESP_OK);
  if (!e) {
    sf_restarting = true;
    sf_display_off();
    sf_prepare_ota_reboot();
    esp_restart();
  }
  sf_restarting = false;
  return e;
}

bool sf_boot_pending(void) {
  esp_ota_img_states_t state;
  return esp_ota_get_state_partition(esp_ota_get_running_partition(), &state) ==
             ESP_OK &&
         state == ESP_OTA_IMG_PENDING_VERIFY;
}
