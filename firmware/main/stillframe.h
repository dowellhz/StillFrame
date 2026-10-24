#pragma once
#include "cJSON.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define SF_BYTES 960000
#define SF_WIDTH 1200
#define SF_HEIGHT 1600
#ifdef CONFIG_SF_PANEL_MAINTENANCE
#ifdef CONFIG_SF_OPEN_AP_DIAGNOSTIC
#define SF_VERSION "0.1.1-rc10-open-ap-test"
#else
#define SF_VERSION "0.1.1-rc10-maintenance"
#endif
#else
#define SF_VERSION "0.1.1-rc12"
#endif
typedef struct {
  uint32_t version;
  char ssid[33], wifi_password[65], server[257], token[193], ap_password[64];
  char device_id[32], photo_id[80];
  uint32_t interval;
  bool configured, local;
  char category[64];
  bool random;
} sf_config;
typedef struct {
  unsigned interval;
  bool has_photo;
  char id[80], url[512], sha256[65];
} sf_sync;
extern sf_config sf_cfg;
extern SemaphoreHandle_t sf_lock, sf_operation;
extern volatile bool sf_connected, sf_ap, sf_sd, sf_refresh_requested,
    sf_restarting, sf_storage_fault, sf_ap_requested, sf_config_pending;
extern volatile bool sf_memory_fault;
extern char sf_status[160];
esp_err_t sf_state_init(void);
esp_err_t sf_save(const sf_config *cfg);
void sf_photo_sha(char out[65]);
esp_err_t sf_save_photo_sha(const char *sha);
void sf_snapshot(sf_config *cfg);
void sf_message(const char *text);
esp_err_t sf_display_init(void);
esp_err_t sf_display(const uint8_t *pixels);
void sf_display_off(void);
esp_err_t sf_setup_screen(void);
esp_err_t sf_network_init(void);
esp_err_t sf_connect(const sf_config *cfg, unsigned timeout_ms);
esp_err_t sf_enable_ap(void);
esp_err_t sf_disable_ap(void);
esp_err_t sf_parse_sync(const char *body, size_t len, sf_sync *out);
esp_err_t sf_validate_frame(const uint8_t *data, size_t len, const char *sha);
esp_err_t sf_server_cycle(void);
esp_err_t sf_web_start(void);
esp_err_t sf_local_mount(void);
void sf_local_unmount(void);
esp_err_t sf_local_cycle(void);
esp_err_t sf_local_api(void *request);
esp_err_t sf_queue_config(const sf_config *candidate);

void sf_welcome_screen(void);

esp_err_t sf_display_error(void);

bool sf_display_available(void);
int64_t sf_display_wait_us(void);
bool sf_display_restart_due(void);
unsigned sf_display_recovery_count(void);
bool sf_display_attempt_failed(void);
bool sf_display_was_healthy_before_boot(void);
bool sf_display_maintenance(void);
#ifdef CONFIG_SF_RUNTIME_TEST
void sf_test_assume_display_was_healthy(void);
#endif
esp_err_t sf_server_cycle_due(bool allow_display, bool *waiting);

void sf_network_power_save(bool idle);
bool sf_network_take_reconnect(void);

esp_err_t sf_station_configure(const sf_config *cfg);

bool sf_begin_update(void);
void sf_prepare_ota_reboot(void);
bool sf_safe_mode_active(void);
