#include "esp_mac.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "stillframe.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>
sf_config sf_cfg;
SemaphoreHandle_t sf_lock, sf_operation;
volatile bool sf_connected, sf_ap, sf_sd, sf_refresh_requested, sf_restarting,
    sf_storage_fault, sf_ap_requested, sf_config_pending;
volatile bool sf_memory_fault;
static bool persisted;
static char displayed_sha[65];
char sf_status[160] = "正在启动";
void sf_snapshot(sf_config *cfg) {
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  *cfg = sf_cfg;
  xSemaphoreGive(sf_lock);
}
void sf_message(const char *text) {
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  snprintf(sf_status, sizeof(sf_status), "%s", text);
  xSemaphoreGive(sf_lock);
}
void sf_photo_sha(char out[65]) {
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  memcpy(out, displayed_sha, sizeof(displayed_sha));
  xSemaphoreGive(sf_lock);
}
esp_err_t sf_save_photo_sha(const char *sha) {
  if (!sha || strlen(sha) != 64 || sf_storage_fault)
    return ESP_ERR_INVALID_ARG;
  for (int i = 0; i < 64; i++)
    if (!isxdigit((unsigned char)sha[i]))
      return ESP_ERR_INVALID_ARG;
  nvs_handle_t n;
  esp_err_t e = nvs_open("stillframe", NVS_READWRITE, &n);
  if (e)
    return e;
  e = nvs_set_str(n, "photo_sha", sha);
  if (!e)
    e = nvs_commit(n);
  nvs_close(n);
  if (!e) {
    xSemaphoreTake(sf_lock, portMAX_DELAY);
    strlcpy(displayed_sha, sha, sizeof(displayed_sha));
    xSemaphoreGive(sf_lock);
  }
  return e;
}
esp_err_t sf_save(const sf_config *cfg) {
  if (sf_storage_fault)
    return ESP_ERR_INVALID_STATE;
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  bool unchanged = persisted && memcmp(cfg, &sf_cfg, sizeof(*cfg)) == 0;
  xSemaphoreGive(sf_lock);
  if (unchanged)
    return ESP_OK;
  nvs_handle_t n;
  esp_err_t e = nvs_open("stillframe", NVS_READWRITE, &n);
  if (e)
    return e;
  e = nvs_set_blob(n, "config", cfg, sizeof(*cfg));
  if (!e)
    e = nvs_commit(n);
  nvs_close(n);
  if (!e) {
    xSemaphoreTake(sf_lock, portMAX_DELAY);
    sf_cfg = *cfg;
    persisted = true;
    xSemaphoreGive(sf_lock);
  }
  return e;
}
esp_err_t sf_state_init(void) {
  sf_lock = xSemaphoreCreateMutex();
  sf_operation = xSemaphoreCreateMutex();
  if (!sf_lock || !sf_operation)
    return ESP_ERR_NO_MEM;
  // Never erase NVS on error: WiFi credentials and device identity must survive
  // upgrades.
  memset(&sf_cfg, 0, sizeof(sf_cfg));
  sf_cfg.version = 1;
  sf_cfg.interval = 3600;
  strcpy(sf_cfg.ap_password, "12345678");
  uint8_t mac[6];
  ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
  snprintf(sf_cfg.device_id, sizeof(sf_cfg.device_id),
           "sf-%02x%02x%02x%02x%02x%02x", mac[0], mac[1], mac[2], mac[3],
           mac[4], mac[5]);
  esp_err_t e = nvs_flash_init();
  if (e) {
    sf_storage_fault = true;
    return e;
  }
  nvs_handle_t n;
  e = nvs_open("stillframe", NVS_READONLY, &n);
  if (e == ESP_ERR_NVS_NOT_FOUND)
    return sf_save(&sf_cfg);
  if (e) {
    sf_storage_fault = true;
    return e;
  }
  sf_config saved;
  size_t size = sizeof(saved);
  e = nvs_get_blob(n, "config", &saved, &size);
  char saved_sha[65] = {0};
  size_t sha_size = sizeof(saved_sha);
  esp_err_t sha_error = nvs_get_str(n, "photo_sha", saved_sha, &sha_size);
  nvs_close(n);
  if (e == ESP_ERR_NVS_NOT_FOUND)
    return sf_save(&sf_cfg);
  if (e || size != sizeof(saved) || saved.version != 1) {
    sf_storage_fault = true;
    return ESP_ERR_INVALID_VERSION;
  }
  // Reject corrupted / incompatible records rather than interpreting
  // unterminated secrets.
  if (!memchr(saved.ssid, 0, sizeof(saved.ssid)) ||
      !memchr(saved.wifi_password, 0, sizeof(saved.wifi_password)) ||
      !memchr(saved.server, 0, sizeof(saved.server)) ||
      !memchr(saved.token, 0, sizeof(saved.token)) ||
      !memchr(saved.ap_password, 0, sizeof(saved.ap_password)) ||
      !memchr(saved.device_id, 0, sizeof(saved.device_id)) ||
      !memchr(saved.photo_id, 0, sizeof(saved.photo_id)) ||
      !memchr(saved.category, 0, sizeof(saved.category)) ||
      strlen(saved.ap_password) < 8 || saved.interval < 180 ||
      saved.interval > 86400) {
    sf_storage_fault = true;
    return ESP_ERR_INVALID_STATE;
  }
  sf_cfg = saved;
  if (sha_error == ESP_OK && strlen(saved_sha) == 64) {
    bool valid = true;
    for (int i = 0; i < 64; i++)
      valid = valid && isxdigit((unsigned char)saved_sha[i]);
    if (valid)
      strlcpy(displayed_sha, saved_sha, sizeof(displayed_sha));
  }
  persisted = true;
  return ESP_OK;
}
