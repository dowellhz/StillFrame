// Optional regression build: REAL worker and REAL panel driver, no panel stub.
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "stillframe.h"
#include <stdlib.h>
#include <string.h>
#define CHECK(x, label)                                                        \
  do {                                                                         \
    if (!(x)) {                                                                \
      ESP_LOGE("runtime-test", "FAIL: %s", label);                             \
      abort();                                                                 \
    }                                                                          \
  } while (0)
static int unexpected_downloads;
static esp_err_t probe_nas(httpd_req_t *r) {
  char body[1024];
  size_t used = 0;
  while (used < r->content_len && used < sizeof(body)) {
    int n = httpd_req_recv(r, body + used, sizeof(body) - used);
    if (n <= 0)
      return ESP_FAIL;
    used += n;
  }
  return httpd_resp_sendstr(
      r, "{\"schemaVersion\":1,\"config\":{\"intervalSeconds\":900},\"photo\":{"
         "\"id\":\"skip-quarantined\",\"width\":1200,\"height\":1600,\"bytes\":"
         "960000,\"format\":\"spectra6-4bpp-row-major\",\"sha256\":"
         "\"0000000000000000000000000000000000000000000000000000000000000000\","
         "\"url\":\"/api/v1/device/photos/skip-quarantined/display.bin\"}}");
}
static esp_err_t unexpected_bin(httpd_req_t *r) {
  unexpected_downloads++;
  return httpd_resp_sendstr(r, "must not download");
}
static void check_quarantined_download(void) {
  httpd_config_t c = HTTPD_DEFAULT_CONFIG();
  c.server_port = 8485;
  c.ctrl_port = 32769;
  c.stack_size = 4096;
  httpd_handle_t h;
  ESP_ERROR_CHECK(httpd_start(&h, &c));
  httpd_uri_t sync = {.uri = "/api/v1/device/sync",
                      .method = HTTP_POST,
                      .handler = probe_nas},
              bin = {.uri =
                         "/api/v1/device/photos/skip-quarantined/display.bin",
                     .method = HTTP_GET,
                     .handler = unexpected_bin};
  ESP_ERROR_CHECK(httpd_register_uri_handler(h, &sync));
  ESP_ERROR_CHECK(httpd_register_uri_handler(h, &bin));
  sf_config old;
  sf_snapshot(&old);
  sf_config cfg = old;
  strcpy(cfg.server, "http://127.0.0.1:8485");
  strcpy(cfg.token, "runtime-probe");
  ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
  ESP_ERROR_CHECK(sf_save(&cfg));
  CHECK(sf_server_cycle() == ESP_OK && sf_cfg.interval == 900 &&
            unexpected_downloads == 0,
        "quarantined display still updates server configuration without "
        "downloading pictures");
  ESP_ERROR_CHECK(sf_save(&old));
  ESP_ERROR_CHECK(esp_task_wdt_delete(NULL));
  httpd_stop(h);
  ESP_LOGI("runtime-test", "PASS: quarantine suppresses photo downloads "
                           "without freezing server configuration");
}
void sf_run_runtime_tests(void) {
  sf_config cfg;
  sf_snapshot(&cfg);
  if (!strcmp(cfg.device_id, "sf-slow-setup")) {
    esp_ota_img_states_t state;
    const esp_partition_t *running = esp_ota_get_running_partition();
    CHECK(running && running->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1 &&
              esp_ota_get_state_partition(running, &state) == ESP_OK &&
              state == ESP_OTA_IMG_VALID,
          "slow first setup display cannot cause an OTA rollback");
    ESP_LOGI("runtime-test", "SLOW SETUP OTA TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-safe-ota")) {
    esp_ota_img_states_t state;
    const esp_partition_t *running = esp_ota_get_running_partition();
    CHECK(running && running->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1 &&
              esp_ota_get_state_partition(running, &state) == ESP_OK &&
              state == ESP_OTA_IMG_VALID,
          "OTA launched from safe mode boots and becomes valid");
    ESP_LOGI("runtime-test", "SAFE MODE OTA RECOVERY TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-panel-rollback")) {
    const esp_partition_t *running = esp_ota_get_running_partition();
    const esp_partition_t *bad = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_1, NULL);
    esp_ota_img_states_t state;
    CHECK(running && running->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_0,
          "panel failure in pending image rolls back to prior slot");
    CHECK(bad && esp_ota_get_state_partition(bad, &state) == ESP_OK &&
              state == ESP_OTA_IMG_INVALID,
          "pending image with panel failure is marked invalid");
    ESP_LOGI("runtime-test", "PENDING OTA PANEL ROLLBACK TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-panel-prebroken")) {
    esp_ota_img_states_t state;
    const esp_partition_t *running = esp_ota_get_running_partition();
    CHECK(running && running->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_1 &&
              esp_ota_get_state_partition(running, &state) == ESP_OK &&
              state == ESP_OTA_IMG_VALID,
          "preexisting panel failure must not prevent installing a repair");
    ESP_LOGI("runtime-test", "PREEXISTING PANEL OTA ACCEPTANCE TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-power-reset")) {
    CHECK(sf_display_recovery_count() == 3 && !sf_display_available(),
          "three interrupted refreshes disable automatic display attempts");
    ESP_LOGI("runtime-test", "POWER RESET DISPLAY QUARANTINE TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-safe-retry")) {
    CHECK(!sf_safe_mode_active(),
          "stable safe mode timeout clears failures and retries normal boot");
    ESP_LOGI("runtime-test", "SAFE MODE AUTOMATIC RETRY TEST PASSED");
    return;
  }
  if (!strcmp(cfg.device_id, "sf-boot-stall")) {
    const esp_partition_t *running = esp_ota_get_running_partition();
    const esp_partition_t *bad = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_1, NULL);
    esp_ota_img_states_t state;
    CHECK(running && running->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_0,
          "stalled worker must roll back to prior image");
    CHECK(bad && esp_ota_get_state_partition(bad, &state) == ESP_OK &&
              state == ESP_OTA_IMG_INVALID,
          "stalled startup must be marked invalid");
    CHECK(xSemaphoreTake(sf_operation, pdMS_TO_TICKS(1000)) == pdTRUE,
          "recovered worker must release operation mutex");
    xSemaphoreGive(sf_operation);
    ESP_LOGI("runtime-test", "STARTUP WORKER ROLLBACK TEST PASSED");
    return;
  }
  if (cfg.configured) {
    ESP_LOGI("runtime-test",
             "provisioned NAS integration device; running real worker");
    return;
  }
  vTaskDelay(pdMS_TO_TICKS(4000));
  bool recovery = sf_storage_fault;
  if (!recovery)
    check_quarantined_download();
  int samples = 0;
  do {
    // The old indefinite SPI wait retains this mutex and fails this check.
    CHECK(xSemaphoreTake(sf_operation, pdMS_TO_TICKS(1000)) == pdTRUE,
          "screen fault must release operation mutex");
    xSemaphoreGive(sf_operation);
    esp_http_client_config_t c = {.url = "http://127.0.0.1/api/status",
                                  .timeout_ms = 2000};
    esp_http_client_handle_t h = esp_http_client_init(&c);
    CHECK(h, "create HTTP probe");
    esp_http_client_set_header(h, "Authorization",
                               "Basic YWRtaW46MTIzNDU2Nzg=");
    CHECK(esp_http_client_open(h, 0) == ESP_OK,
          "HTTP service connects after panel timeout");
    CHECK(esp_http_client_fetch_headers(h) >= 0 &&
              esp_http_client_get_status_code(h) == 200,
          "HTTP service responds after panel timeout");
    char response[2048];
    size_t used = 0;
    int n;
    while (used < sizeof(response) - 1 &&
           (n = esp_http_client_read(h, response + used,
                                     sizeof(response) - 1 - used)) > 0)
      used += n;
    response[used] = 0;
    cJSON *status = cJSON_Parse(response);
    CHECK(status && cJSON_IsTrue(cJSON_GetObjectItem(status, "displayFault")),
          "panel failure must be visible in status independently of help "
          "messages");
    if (recovery)
      CHECK(cJSON_IsTrue(cJSON_GetObjectItem(status, "storageFault")),
            "corrupt stored config remains flagged without erasure");
    cJSON_Delete(status);
    esp_http_client_cleanup(h);
    samples++;
    ESP_LOGI("runtime-test",
             "HTTP and operation mutex healthy; uptime=%lld seconds",
             (long long)(esp_timer_get_time() / 1000000));
    if (esp_timer_get_time() >= (recovery ? 20000000 : 90000000))
      break;
    vTaskDelay(pdMS_TO_TICKS(10000));
  } while (true);
  if (recovery) {
    esp_http_client_config_t c = {.url = "http://127.0.0.1/api/config",
                                  .timeout_ms = 2000};
    esp_http_client_handle_t h = esp_http_client_init(&c);
    CHECK(h, "create recovery config probe");
    esp_http_client_set_header(h, "Authorization",
                               "Basic YWRtaW46MTIzNDU2Nzg=");
    esp_http_client_set_method(h, HTTP_METHOD_POST);
    CHECK(esp_http_client_open(h, 2) == ESP_OK,
          "recovery configuration endpoint connects");
    CHECK(esp_http_client_write(h, "{}", 2) == 2,
          "write recovery configuration probe");
    CHECK(esp_http_client_fetch_headers(h) >= 0 &&
              esp_http_client_get_status_code(h) == 503,
          "recovery does not overwrite unreadable credentials");
    esp_http_client_cleanup(h);
    ESP_LOGI("runtime-test", "RECOVERY PORTAL TEST PASSED; NVS preserved");
    return;
  }
  CHECK(samples >= 9, "repeat HTTP probes beyond original watchdog failure");
  ESP_LOGI("runtime-test",
           "REAL DRIVER RUNTIME TEST PASSED after 90 seconds; no panel stub");
}
