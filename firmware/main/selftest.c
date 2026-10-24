// This file is linked only when CONFIG_SF_TEST_MODE=y, never in release
// firmware.
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_wifi.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include "nvs.h"
#include "rom.h"
#include "stillframe.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
extern const uint8_t panic_start[] asm("_binary_panic_bin_start");
extern const uint8_t panic_end[] asm("_binary_panic_bin_end");
#define CHECK(test, label)                                                     \
  do {                                                                         \
    if (!(test)) {                                                             \
      ESP_LOGE("test", "FAIL: %s", label);                                     \
      abort();                                                                 \
    }                                                                          \
    ESP_LOGI("test", "PASS: %s", label);                                       \
  } while (0)
extern const uint8_t nas_json_start[] asm("_binary_nas_sync_json_start");
extern const uint8_t nas_json_end[] asm("_binary_nas_sync_json_end");
extern const uint8_t nas_frame_start[] asm("_binary_nas_frame_bin_start");
extern const uint8_t nas_frame_end[] asm("_binary_nas_frame_bin_end");
static void protocol_tests(void) {
  extern bool sf_test_local_index_valid(cJSON * j);
  cJSON *local = cJSON_Parse("{\"categories\":[],\"photos\":[]}");
  CHECK(sf_test_local_index_valid(local), "empty local index is valid");
  cJSON *cats = cJSON_GetObjectItem(local, "categories"),
        *photos = cJSON_GetObjectItem(local, "photos");
  cJSON *cat = cJSON_Parse("{\"id\":\"a\",\"name\":\"A\",\"parentId\":\"a\"}");
  cJSON_AddItemToArray(cats, cat);
  CHECK(!sf_test_local_index_valid(local),
        "local category cycles cannot be loaded or saved");
  cJSON_ReplaceItemInObject(cat, "parentId", cJSON_CreateString(""));
  cJSON *photo = cJSON_CreateObject();
  cJSON_AddStringToObject(photo, "id", "../outside");
  cJSON_AddStringToObject(
      photo, "sha256",
      "0000000000000000000000000000000000000000000000000000000000000000");
  cJSON_AddItemToArray(photos, photo);
  CHECK(!sf_test_local_index_valid(local),
        "local index rejects invalid file identifiers");
  cJSON_ReplaceItemInObject(photo, "id", cJSON_CreateString("valid"));
  CHECK(sf_test_local_index_valid(local),
        "well-formed local metadata is accepted");
  char *huge = malloc(262145);
  CHECK(huge, "allocate oversize index fixture");
  memset(huge, 'x', 262144);
  huge[262144] = 0;
  cJSON_AddStringToObject(local, "extra", huge);
  free(huge);
  CHECK(!sf_test_local_index_valid(local),
        "local metadata cannot outgrow the maximum readable index size");
  cJSON_Delete(local);
  const char *empty = "{\"schemaVersion\":1,\"config\":{\"intervalSeconds\":"
                      "180},\"photo\":null}";
  sf_sync parsed;
  CHECK(sf_parse_sync((const char *)nas_json_start,
                      nas_json_end - nas_json_start, &parsed) == ESP_OK &&
            parsed.has_photo && parsed.interval == 180,
        "parse captured live NAS device configuration and photo JSON");
  CHECK(sf_validate_frame(nas_frame_start, nas_frame_end - nas_frame_start,
                          parsed.sha256) == ESP_OK,
        "validate complete live NAS Monet frame on actual Xtensa CPU");

  CHECK(sf_parse_sync(empty, strlen(empty), &parsed) == ESP_OK &&
            !parsed.has_photo && parsed.interval == 180,
        "empty album updates configuration");
  CHECK(sf_parse_sync("{}", 2, &parsed) != ESP_OK,
        "reject missing configuration");
  const char *bad = "{\"schemaVersion\":1,\"config\":{\"intervalSeconds\":179},"
                    "\"photo\":null}";
  CHECK(sf_parse_sync(bad, strlen(bad), &parsed) != ESP_OK,
        "enforce minimum refresh interval");
  char valid[1024];
  snprintf(valid, sizeof(valid),
           "{\"schemaVersion\":1,\"config\":{\"intervalSeconds\":3600},"
           "\"photo\":{\"id\":\"p1\",\"width\":1200,\"height\":1600,\"bytes\":"
           "960000,\"format\":\"spectra6-4bpp-row-major\",\"sha256\":\"%064d\","
           "\"url\":\"/api/v1/device/photos/p1/display.bin?v=1\"}}",
           0);
  CHECK(sf_parse_sync(valid, strlen(valid), &parsed) == ESP_OK &&
            parsed.has_photo,
        "parse server display contract");
  cJSON *j = cJSON_Parse(valid);
  cJSON *p = cJSON_GetObjectItem(j, "photo");
  cJSON_ReplaceItemInObject(
      p, "url", cJSON_CreateString("https://attacker.invalid/frame.bin"));
  char *s = cJSON_PrintUnformatted(j);
  CHECK(sf_parse_sync(s, strlen(s), &parsed) != ESP_OK,
        "reject cross-origin photo URLs");
  free(s);
  cJSON_ReplaceItemInObject(
      p, "url", cJSON_CreateString("/api/v1/device/photos/p1/display.bin"));
  cJSON_ReplaceItemInObject(p, "bytes", cJSON_CreateNumber(960001));
  s = cJSON_PrintUnformatted(j);
  CHECK(sf_parse_sync(s, strlen(s), &parsed) != ESP_OK,
        "reject incorrect frame size");
  free(s);
  cJSON_Delete(j);
  uint8_t *pixels =
      heap_caps_malloc(SF_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  CHECK(pixels != NULL, "allocate complete frame in PSRAM");
  memset(pixels, 0x11, SF_BYTES);
  uint8_t hash[32];
  mbedtls_sha256(pixels, SF_BYTES, hash, 0);
  char sha[65];
  for (int i = 0; i < 32; i++)
    sprintf(sha + i * 2, "%02x", hash[i]);
  CHECK(sf_validate_frame(pixels, SF_BYTES, sha) == ESP_OK,
        "accept complete verified frame");
  CHECK(sf_validate_frame(pixels, SF_BYTES - 1, sha) != ESP_OK,
        "reject interrupted image download");
  pixels[0] = 0x44;
  CHECK(sf_validate_frame(pixels, SF_BYTES, sha) != ESP_OK,
        "reject unsupported color nibble");
  pixels[0] = 0x22;
  CHECK(sf_validate_frame(pixels, SF_BYTES, sha) == ESP_ERR_INVALID_CRC,
        "reject SHA256 mismatch");
  free(pixels);
}
void sf_run_tests(void) {
  ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
  nvs_handle_t n;
  ESP_ERROR_CHECK(nvs_open("safety_test", NVS_READWRITE, &n));
  uint32_t stage = 0;
  nvs_get_u32(n, "stage", &stage);
  if (stage == 0) {
    protocol_tests();
    extern void sf_network_fault_tests(void);
    sf_network_fault_tests();
    sf_config cfg;
    sf_snapshot(&cfg);
    strcpy(cfg.ssid, "myssid");
    strcpy(cfg.wifi_password, "mypassword");
    strcpy(cfg.server, "http://10.10.10.21:8484");
    strcpy(cfg.token, "test-invalid-credential");
    strcpy(cfg.ap_password, "test-12345678");
    cfg.interval = 7200;
    cfg.configured = true;
    ESP_ERROR_CHECK(sf_save(&cfg));
    ESP_ERROR_CHECK(nvs_set_str(n, "identity", cfg.device_id));
    ESP_ERROR_CHECK(nvs_set_u32(n, "stage", 1));
    ESP_ERROR_CHECK(nvs_commit(n));
    nvs_close(n);
    ESP_LOGI("test", "NVS test record saved; rebooting");
    esp_restart();
  }
  sf_config cfg;
  sf_snapshot(&cfg);
  CHECK(!strcmp(cfg.ssid, "myssid") &&
            !strcmp(cfg.wifi_password, "mypassword") &&
            !strcmp(cfg.ap_password, "test-12345678") && cfg.interval == 7200 &&
            cfg.configured,
        "NVS configuration survives reset");
  char identity[32];
  size_t identity_len = sizeof(identity);
  ESP_ERROR_CHECK(nvs_get_str(n, "identity", identity, &identity_len));
  CHECK(!strcmp(cfg.device_id, identity),
        "stable device identity survives reset");
  wifi_config_t actual_ap;
  ESP_ERROR_CHECK(esp_wifi_get_config(WIFI_IF_AP, &actual_ap));
  CHECK(!strcmp((char *)actual_ap.ap.ssid, "Stillframe") &&
            !strcmp((char *)actual_ap.ap.password, cfg.ap_password),
        "saved AP credentials applied after reboot");
  if (stage == 1) {
    extern void sf_station_encoding_test(void);
    sf_station_encoding_test();
    esp_err_t e = sf_connect(&cfg, 15000);
    CHECK(e == ESP_OK && sf_connected, "STA connects to emulated WiFi");
    ESP_ERROR_CHECK(esp_wifi_disconnect());
    vTaskDelay(pdMS_TO_TICKS(200));
    CHECK(sf_network_take_reconnect(),
          "unexpected Wi-Fi disconnect requests an immediate worker reconnect");
    CHECK(sf_connect(&cfg, 15000) == ESP_OK,
          "device reconnects after an unexpected Wi-Fi disconnect");
    extern void sf_http_tests(nvs_handle_t n);
    sf_http_tests(n);
    for (;;) {
      esp_task_wdt_reset();
      vTaskDelay(pdMS_TO_TICKS(100));
    }
  }
  if (stage == 2) {
    const esp_partition_t *current = esp_ota_get_running_partition();
    CHECK(current && current->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_0,
          "bootloader rolled back to original OTA slot");
    const esp_partition_t *bad = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_APP_OTA_1, NULL);
    esp_ota_img_states_t state;
    CHECK(esp_ota_get_state_partition(bad, &state) == ESP_OK &&
              state == ESP_OTA_IMG_ABORTED,
          "failed startup marked ABORTED");
    extern void sf_remote_tests(nvs_handle_t n, bool rolled_back);
    sf_remote_tests(n, false);
  }
  if (stage == 4) {
    extern void sf_remote_tests(nvs_handle_t n, bool rolled_back);
    sf_remote_tests(n, true);
  }
  nvs_close(n);
  ESP_LOGI("test", "ALL FIRMWARE SAFETY TESTS PASSED");
  ESP_ERROR_CHECK(esp_task_wdt_delete(NULL));
}
static int panel_result = ESP_OK, panel_calls, mode, sync_count, bin_calls;
static char unresolved_request[80];
static char first_request[80], frame_sha[65];
esp_err_t sf_test_panel(const uint8_t *pixels) {
  panel_calls++;
  ESP_LOGI("test", "TEST PANEL STUB: result=%d (physical display not emulated)",
           panel_result);
  return panel_result;
}
static esp_err_t mock_sync(httpd_req_t *r) {
  char auth[100];
  if (httpd_req_get_hdr_value_str(r, "Authorization", auth, sizeof(auth)) ||
      strcmp(auth, "Bearer test-valid-credential")) {
    httpd_resp_set_status(r, "401 Unauthorized");
    return httpd_resp_sendstr(r, "invalid token");
  }
  if (r->content_len > 1024)
    return ESP_FAIL;
  char body[1025];
  int used = 0;
  while (used < r->content_len) {
    int n = httpd_req_recv(r, body + used, r->content_len - used);
    if (n <= 0)
      return ESP_FAIL;
    used += n;
  }
  body[used] = 0;
  cJSON *j = cJSON_Parse(body);
  CHECK(j != NULL, "server receives valid JSON request");
  cJSON *id = cJSON_GetObjectItem(j, "deviceId"),
        *req = cJSON_GetObjectItem(j, "requestId"),
        *shown = cJSON_GetObjectItem(j, "currentPhotoId");
  CHECK(cJSON_IsString(id) && !strcmp(id->valuestring, sf_cfg.device_id),
        "sync carries stable device identity");
  CHECK(cJSON_IsString(req), "sync carries idempotency key");
  if (mode == 3) {
    strlcpy(unresolved_request, req->valuestring, sizeof(unresolved_request));
    cJSON_Delete(j);
    return ESP_FAIL;
  }
  if (unresolved_request[0]) {
    CHECK(!strcmp(unresolved_request, req->valuestring),
          "retry unresolved HTTP response with same request ID");
    unresolved_request[0] = 0;
  }
  if (sync_count == 0)
    strlcpy(first_request, req->valuestring, sizeof(first_request));
  if (sync_count == 1)
    CHECK(strcmp(first_request, req->valuestring) && !shown,
          "failed display starts fresh config sync without acknowledgement");
  if (sync_count == 2)
    CHECK(cJSON_IsString(shown) && !strcmp(shown->valuestring, "test-photo"),
          "acknowledge only the successfully displayed photo");
  cJSON_Delete(j);
  sync_count++;
  char response[1100];
  unsigned interval = sync_count == 1 ? 180 : sync_count == 2 ? 7200 : 900;
  if (mode == 1 || mode == 4)
    snprintf(response, sizeof(response),
             "{\"schemaVersion\":1,\"config\":{\"intervalSeconds\":%u},"
             "\"firmware\":%s,\"photo\":null}", interval,
             mode == 4
                 ? "{\"taskId\":\"00000000-0000-0000-0000-000000000099\","
                   "\"url\":\"/api/v1/device/firmware/bad\",\"sha256\":"
                   "\"0000000000000000000000000000000000000000000000000000000000000000\","
                   "\"boardModel\":\"WRONG\",\"panelModel\":\"GDEP133C02\","
                   "\"chipModel\":\"esp32s3\",\"otaProtocol\":1,\"bytes\":4096}"
                 : "null");
  else
    snprintf(response, sizeof(response),
             "{\"schemaVersion\":1,\"registered\":%s,\"config\":{"
             "\"intervalSeconds\":%u},\"photo\":{\"id\":\"%s\","
             "\"width\":1200,\"height\":1600,\"bytes\":960000,\"format\":"
             "\"spectra6-4bpp-row-major\",\"sha256\":\"%s\",\"url\":\"/api/v1/"
             "device/photos/test-photo/display.bin\"}}",
             sync_count == 1 ? "true" : "false", interval,
             mode == 2 ? "truncated-photo"
                       : mode == 5 ? "cooldown-photo" : "test-photo",
             frame_sha);
  httpd_resp_set_type(r, "application/json");
  return httpd_resp_sendstr(r, response);
}
static esp_err_t mock_bin(httpd_req_t *r) {
  bin_calls++;
  uint8_t white[4096];
  memset(white, 0x11, sizeof(white));
  size_t count = mode == 2 ? SF_BYTES - 10 : SF_BYTES;
  httpd_resp_set_type(r, "application/octet-stream");
  while (count) {
    size_t n = count > sizeof(white) ? sizeof(white) : count;
    esp_err_t e = httpd_resp_send_chunk(r, (char *)white, n);
    if (e)
      return e;
    count -= n;
  }
  return httpd_resp_send_chunk(r, NULL, 0);
}
static int request(const char *path, const void *data, size_t size,
                   const char *sha, bool authorized, char *out, size_t cap) {
  char url[300];
  snprintf(url, sizeof(url), "http://127.0.0.1%s", path);
  esp_http_client_config_t config = {
      .url = url, .timeout_ms = 5000, .disable_auto_redirect = true};
  esp_http_client_handle_t h = esp_http_client_init(&config);
  CHECK(h != NULL, "create loopback HTTP client");
  if (authorized) {
    char plain[100], base[160] = "Basic ";
    size_t n;
    snprintf(plain, sizeof(plain), "admin:%s", sf_cfg.ap_password);
    mbedtls_base64_encode((uint8_t *)base + 6, sizeof(base) - 6, &n,
                          (uint8_t *)plain, strlen(plain));
    base[6 + n] = 0;
    esp_http_client_set_header(h, "Authorization", base);
  }
  if (data) {
    esp_http_client_set_method(h, HTTP_METHOD_POST);
    esp_http_client_set_header(h, "Content-Type", "application/octet-stream");
  }
  if (sha)
    esp_http_client_set_header(h, "X-SHA256", sha);
  ESP_ERROR_CHECK(esp_http_client_open(h, size));
  size_t used = 0;
  while (used < size) {
    int n = esp_http_client_write(h, (const char *)data + used, size - used);
    CHECK(n > 0, "write HTTP upload");
    used += n;
    esp_task_wdt_reset();
  }
  CHECK(esp_http_client_fetch_headers(h) >= 0, "read HTTP response headers");
  int code = esp_http_client_get_status_code(h);
  size_t got = 0;
  while (got < cap - 1) {
    int n = esp_http_client_read(h, out + got, cap - 1 - got);
    if (n <= 0)
      break;
    got += n;
    esp_task_wdt_reset();
  }
  out[got] = 0;
  esp_http_client_cleanup(h);
  return code;
}
void sf_http_tests(nvs_handle_t n) {
  char reply[4096];

  xSemaphoreTake(sf_lock, portMAX_DELAY);
  bool was_configured = sf_cfg.configured;
  sf_cfg.configured = false;
  xSemaphoreGive(sf_lock);
  CHECK(request("/", NULL, 0, NULL, false, reply, sizeof(reply)) == 401,
        "setup page requires hotspot credentials before initial setup");
  CHECK(request("/api/status", NULL, 0, NULL, false, reply,
                sizeof(reply)) == 401,
        "status requires authentication before initial setup");
  CHECK(request("/api/config", "{}", 2, NULL, false, reply,
                sizeof(reply)) == 401,
        "configuration requires authentication before initial setup");
  CHECK(request("/api/local", NULL, 0, NULL, false, reply,
                sizeof(reply)) == 401,
        "local storage API requires authentication before initial setup");
  CHECK(request("/api/update", "x", 1, NULL, false, reply, sizeof(reply)) ==
            401,
        "firmware upload requires authentication before initial setup");
  xSemaphoreTake(sf_lock, portMAX_DELAY);
  sf_cfg.configured = was_configured;
  xSemaphoreGive(sf_lock);

  CHECK(request("/api/status", NULL, 0, NULL, false, reply, sizeof(reply)) ==
            401,
        "configured web management requires authentication");
  CHECK(request("/api/status", NULL, 0, NULL, true, reply, sizeof(reply)) ==
            200,
        "authenticated management status works");
  CHECK(!strstr(reply, "mypassword") && !strstr(reply, "test-12345678") &&
            !strstr(reply, "test-invalid-credential"),
        "status never exposes stored passwords or token");
  CHECK(request("/api/config", "{}", 2, NULL, true, reply, sizeof(reply)) ==
            202,
        "existing valid configuration can be submitted");
  CHECK(sf_config_pending,
        "accepted configuration remains pending until processed");
  CHECK(request("/api/update", "x", 1, NULL, true, reply, sizeof(reply)) == 409,
        "OTA cannot overtake a pending configuration");
  extern void sf_test_clear_pending_configuration(void);
  sf_test_clear_pending_configuration();
  // Test fixture cleanup; the normal worker is not enabled in this test build.
  CHECK(request("/api/config", "{\"apPassword\":\"short\"}", 22, NULL, true,
                reply, sizeof(reply)) == 400,
        "reject short AP password");
  CHECK(sf_local_mount() != ESP_OK && !sf_sd,
        "missing SD does not enable local storage");
  // Use an in-guest NAS fixture: real IDF TCP, HTTP, JSON, frame download and
  // hashing.
  httpd_config_t hc = HTTPD_DEFAULT_CONFIG();
  hc.server_port = 8485;
  hc.ctrl_port = 32769;
  hc.stack_size = 8192;
  httpd_handle_t server;
  ESP_ERROR_CHECK(httpd_start(&server, &hc));
  httpd_uri_t sync = {.uri = "/api/v1/device/sync",
                      .method = HTTP_POST,
                      .handler = mock_sync},
              bin = {.uri = "/api/v1/device/photos/test-photo/display.bin",
                     .method = HTTP_GET,
                     .handler = mock_bin};
  ESP_ERROR_CHECK(httpd_register_uri_handler(server, &sync));
  ESP_ERROR_CHECK(httpd_register_uri_handler(server, &bin));
  uint8_t *white = malloc(SF_BYTES);
  CHECK(white != NULL, "allocate NAS test frame");
  memset(white, 0x11, SF_BYTES);
  uint8_t digest[32];
  mbedtls_sha256(white, SF_BYTES, digest, 0);
  free(white);
  for (int i = 0; i < 32; i++)
    sprintf(frame_sha + 2 * i, "%02x", digest[i]);
  sf_config cfg;
  sf_snapshot(&cfg);
  strcpy(cfg.server, "http://127.0.0.1:8485");
  strcpy(cfg.token, "test-valid-credential");
  cfg.photo_id[0] = 0;
  ESP_ERROR_CHECK(sf_save(&cfg));
  mode = 3;
  CHECK(sf_server_cycle() != ESP_OK,
        "unresolved sync transport failure is retryable");
  mode = 0;
  panel_result = ESP_ERR_TIMEOUT;
  CHECK(sf_server_cycle() == ESP_ERR_TIMEOUT && !sf_cfg.photo_id[0] &&
            sf_cfg.interval == 180,
        "first sync registers configuration but failed panel is never "
        "acknowledged");
  panel_result = ESP_OK;
  CHECK(sf_server_cycle() == ESP_OK && !strcmp(sf_cfg.photo_id, "test-photo") &&
            sf_cfg.interval == 7200,
        "second sync downloads 960000 bytes, verifies SHA256 and applies new "
        "configuration");
  int same_downloads = bin_calls, same_displays = panel_calls;
  CHECK(sf_server_cycle() == ESP_OK && bin_calls == same_downloads &&
            panel_calls == same_displays,
        "unchanged photo id and display SHA skip repeat download and refresh");
  mode = 1;
  CHECK(sf_server_cycle() == ESP_OK && sf_cfg.interval == 900,
        "every sync applies new configuration even without a new photo");
  int calls = panel_calls;
  mode = 2;
  CHECK(sf_server_cycle() != ESP_OK && panel_calls == calls,
        "truncated HTTP photo never reaches panel");
  mode = 5;
  bool waiting = false;
  int downloaded = bin_calls;
  CHECK(sf_server_cycle_due(false, &waiting) == ESP_OK && waiting &&
            bin_calls == downloaded,
        "refresh cooldown still fetches config but avoids early download and "
        "display");
  mode = 4;
  CHECK(sf_server_cycle() == ESP_OK && sf_cfg.interval == 900,
        "rejected firmware offer does not block server configuration or photo cycle");
  sf_snapshot(&cfg);
  strcpy(cfg.token, "test-invalid-credential");
  ESP_ERROR_CHECK(sf_save(&cfg));
  CHECK(sf_server_cycle() != ESP_OK && panel_calls == calls &&
            !strcmp(sf_cfg.photo_id, "test-photo"),
        "HTTP 401 preserves existing picture and acknowledgement");
  httpd_stop(server);
  // Re-run the actual web OTA path, first with an incorrect checksum, then a
  // valid crashing app.
  size_t len = panic_end - panic_start;
  char sha[65];
  mbedtls_sha256(panic_start, len, digest, 0);
  for (int i = 0; i < 32; i++)
    sprintf(sha + i * 2, "%02x", digest[i]);
  const esp_partition_t *active = esp_ota_get_boot_partition();
  CHECK(request(
            "/api/update", panic_start, len,
            "0000000000000000000000000000000000000000000000000000000000000000",
            true, reply, sizeof(reply)) == 400 &&
            esp_ota_get_boot_partition() == active,
        "OTA checksum failure never changes boot partition");
  // Store stage and the exact config expectation BEFORE the OTA handler
  // schedules reset.
  sf_snapshot(&cfg);
  cfg.interval = 7200;
  cfg.photo_id[0] = 0;
  ESP_ERROR_CHECK(sf_save(&cfg));
  ESP_ERROR_CHECK(nvs_set_u32(n, "stage", 2));
  ESP_ERROR_CHECK(nvs_commit(n));
  CHECK(request("/api/update", panic_start, len, sha, true, reply,
                sizeof(reply)) == 200,
        "valid web OTA writes inactive slot and schedules reboot");
  ESP_LOGI("test", "Bad startup image staged via HTTP OTA; waiting for real "
                   "reboot and rollback");
}

static int remote_gets, remote_failures;
static esp_err_t remote_bin(httpd_req_t *r) {
  remote_gets++;
  httpd_resp_set_type(r, "application/octet-stream");
  return httpd_resp_send(r, (const char *)panic_start, panic_end - panic_start);
}
static esp_err_t remote_result(httpd_req_t *r) {
  char body[1024];
  int used = 0;
  if (r->content_len > 1023)
    return ESP_FAIL;
  while (used < r->content_len) {
    int n = httpd_req_recv(r, body + used, r->content_len - used);
    if (n <= 0)
      return ESP_FAIL;
    used += n;
  }
  body[used] = 0;
  if (strstr(body, "failed"))
    remote_failures++;
  return httpd_resp_sendstr(r, "{}");
}
void sf_remote_tests(nvs_handle_t n, bool rolled_back) {
  sf_config cfg;
  sf_snapshot(&cfg);
  ESP_ERROR_CHECK(sf_connect(&cfg, 15000));
  strcpy(cfg.server, "http://127.0.0.1:8486");
  httpd_config_t hc = HTTPD_DEFAULT_CONFIG();
  hc.server_port = 8486;
  hc.ctrl_port = 32770;
  hc.stack_size = 8192;
  httpd_handle_t server;
  ESP_ERROR_CHECK(httpd_start(&server, &hc));
  httpd_uri_t bin = {.uri = "/api/v1/device/firmware/test",
                     .method = HTTP_GET,
                     .handler = remote_bin},
              report = {.uri = "/api/v1/device/firmware-result",
                        .method = HTTP_POST,
                        .handler = remote_result};
  ESP_ERROR_CHECK(httpd_register_uri_handler(server, &bin));
  ESP_ERROR_CHECK(httpd_register_uri_handler(server, &report));
  uint8_t digest[32];
  char sha[65], json[1024];
  mbedtls_sha256(panic_start, panic_end - panic_start, digest, 0);
  for (int i = 0; i < 32; i++)
    sprintf(sha + i * 2, "%02x", digest[i]);
  snprintf(json, sizeof(json),
           "{\"taskId\":\"00000000-0000-0000-0000-000000000002\",\"url\":\"/"
           "api/v1/device/firmware/"
           "test\",\"sha256\":\"%s\",\"boardModel\":\"ESP32-133C02-IL\","
           "\"panelModel\":\"GDEP133C02\",\"chipModel\":\"esp32s3\","
           "\"otaProtocol\":1,\"bytes\":%u}",
           sha, (unsigned)(panic_end - panic_start));
  cJSON *offer = cJSON_Parse(json);
  CHECK(offer != NULL, "construct remote OTA fixture");
  const esp_partition_t *active = esp_ota_get_boot_partition();
  if (rolled_back) {
    CHECK(active->subtype == ESP_PARTITION_SUBTYPE_APP_OTA_0,
          "remote OTA bad startup rolled back");
    CHECK(sf_remote_update(offer, &cfg) == ESP_ERR_INVALID_STATE &&
              remote_gets == 0 && remote_failures == 1 &&
              esp_ota_get_boot_partition() == active,
          "failed remote task never re-downloads or reflashes after rollback");
    ESP_ERROR_CHECK(nvs_set_u32(n, "stage", 5));
    ESP_ERROR_CHECK(nvs_commit(n));
    cJSON_Delete(offer);
    httpd_stop(server);
    return;
  }
  sf_config_pending = true;
  CHECK(sf_remote_update(offer, &cfg) == ESP_ERR_INVALID_STATE &&
            remote_gets == 0,
        "busy configuration does not consume a remote upgrade task");
  sf_config_pending = false;
  char running[65];
  CHECK(sf_running_sha(running) == ESP_OK && strlen(running) == 64,
        "compute installed application SHA for NAS confirmation");
  ESP_LOGI("test", "RUNNING_ROM_SHA256 %s", running);
  cJSON_ReplaceItemInObject(offer, "boardModel", cJSON_CreateString("WRONG"));
  CHECK(sf_remote_update(offer, &cfg) == ESP_ERR_INVALID_ARG &&
            remote_gets == 0 && remote_failures == 1 &&
            esp_ota_get_boot_partition() == active,
        "device independently rejects remote ROM for a wrong board");
  cJSON_ReplaceItemInObject(offer, "boardModel",
                            cJSON_CreateString("ESP32-133C02-IL"));
  cJSON_ReplaceItemInObject(
      offer, "sha256",
      cJSON_CreateString(
          "0000000000000000000000000000000000000000000000000000000000000000"));
  cJSON_ReplaceItemInObject(
      offer, "taskId",
      cJSON_CreateString("00000000-0000-0000-0000-000000000001"));
  CHECK(sf_remote_update(offer, &cfg) == ESP_ERR_INVALID_CRC &&
            remote_gets == 1 && remote_failures == 2 &&
            esp_ota_get_boot_partition() == active,
        "remote ROM checksum mismatch preserves boot slot and reports failure");
  cJSON_ReplaceItemInObject(offer, "sha256", cJSON_CreateString(sha));
  cJSON_ReplaceItemInObject(
      offer, "taskId",
      cJSON_CreateString("00000000-0000-0000-0000-000000000002"));
  ESP_ERROR_CHECK(nvs_set_u32(n, "stage", 4));
  ESP_ERROR_CHECK(nvs_commit(n));
  ESP_LOGI("test",
           "remote OTA valid image will write inactive slot then reboot");
  sf_remote_update(offer, &cfg);
  CHECK(false, "valid remote OTA must reboot");
}

void sf_station_encoding_test(void) {
  sf_config saved, edge;
  sf_snapshot(&saved);
  edge = saved;
  memset(edge.ssid, 'W', 32);
  edge.ssid[32] = 0;
  memset(edge.wifi_password, 'a', 64);
  edge.wifi_password[64] = 0;
  ESP_ERROR_CHECK(sf_station_configure(&edge));
  wifi_config_t encoded;
  ESP_ERROR_CHECK(esp_wifi_get_config(WIFI_IF_STA, &encoded));
  CHECK(!memcmp(encoded.sta.ssid, edge.ssid, 32) &&
            !memcmp(encoded.sta.password, edge.wifi_password, 64),
        "32-byte SSID and 64-digit PSK are not truncated");
  ESP_ERROR_CHECK(sf_station_configure(&saved));
}
