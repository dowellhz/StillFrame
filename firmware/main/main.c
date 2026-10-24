#include "driver/gpio.h"
#include "esp_attr.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/queue.h"
#include "rom.h"
#include "stillframe.h"
#include <string.h>
static QueueHandle_t changes;
static volatile bool worker_boot_ready, worker_cycle_ready;
static bool boot_safe_mode;
static volatile bool safe_exit_requested;
typedef struct {
  uint32_t magic, early_resets, active, check;
} boot_rtc_state;
static RTC_NOINIT_ATTR boot_rtc_state boot_health;
#define BOOT_RTC_MAGIC 0x53464248u
static uint32_t boot_check(void) {
  return boot_health.magic ^ boot_health.early_resets ^ boot_health.active ^
         0x39c25a71u;
}
static void boot_write(unsigned resets, bool active) {
  boot_health.magic = BOOT_RTC_MAGIC;
  boot_health.early_resets = resets;
  boot_health.active = active;
  boot_health.check = boot_check();
}
static bool boot_guard_begin(void) {
  if (boot_health.magic != BOOT_RTC_MAGIC || boot_health.check != boot_check())
    boot_write(0, false);
  unsigned resets = boot_health.early_resets;
  if (boot_health.active && resets < 100)
    resets++;
  boot_write(resets, true);
  return resets >= 3;
}
static void boot_guard_clear(void) { boot_write(0, false); }
void sf_prepare_ota_reboot(void) {
  // A deliberate reboot into a newly written image starts a fresh health
  // assessment. Otherwise an OTA launched from safe mode inherits the old
  // failure count and the new image is rejected before it can recover.
  boot_guard_clear();
}
bool sf_safe_mode_active(void) { return boot_safe_mode; }
#ifdef CONFIG_SF_RUNTIME_TEST
static RTC_NOINIT_ATTR uint32_t safe_ota_stage;
#define SAFE_OTA_STAGE_MAGIC 0x53464f54u
static RTC_NOINIT_ATTR uint32_t safe_retry_stage;
#define SAFE_RETRY_STAGE_MAGIC 0x53465254u
static void safe_retry_busy_test(void *arg) {
  if (xSemaphoreTake(sf_operation, pdMS_TO_TICKS(1000)) == pdTRUE) {
    ESP_LOGI("startup-test", "SAFE RETRY WRITE OPERATION HELD");
    vTaskDelay(pdMS_TO_TICKS(2500));
    ESP_LOGI("startup-test", "SAFE RETRY WRITE OPERATION RELEASED");
    xSemaphoreGive(sf_operation);
  }
  vTaskDelete(NULL);
}
#endif
static portMUX_TYPE update_gate = portMUX_INITIALIZER_UNLOCKED;
bool sf_begin_update(void) {
  taskENTER_CRITICAL(&update_gate);
  bool allowed = !sf_restarting && !sf_config_pending;
  if (allowed)
    sf_restarting = true;
  taskEXIT_CRITICAL(&update_gate);
  return allowed;
}
esp_err_t sf_queue_config(const sf_config *c) {
  taskENTER_CRITICAL(&update_gate);
  bool busy = sf_restarting || sf_storage_fault || sf_config_pending;
  if (!busy)
    sf_config_pending = true;
  taskEXIT_CRITICAL(&update_gate);
  if (busy)
    return ESP_ERR_INVALID_STATE;
  if (xQueueSend(changes, c, 0) == pdTRUE)
    return ESP_OK;
  sf_config_pending = false;
  return ESP_ERR_TIMEOUT;
}
#ifdef CONFIG_SF_TEST_MODE
void sf_test_clear_pending_configuration(void) {
  xQueueReset(changes);
  sf_config_pending = false;
}
#endif
static void worker(void *arg) {
  ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
  sf_config cfg;
  sf_snapshot(&cfg);
  while (xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) != pdTRUE)
    esp_task_wdt_reset();
#ifdef CONFIG_SF_RUNTIME_TEST
  if (!strcmp(cfg.device_id, "sf-boot-stall") && sf_boot_pending()) {
    ESP_LOGW("startup-test", "INTENTIONAL WORKER STARTUP STALL");
    for (;;) {
      esp_task_wdt_reset();
      vTaskDelay(pdMS_TO_TICKS(100));
    }
  }
#endif
  sf_local_mount();
  worker_boot_ready = true;
  ESP_LOGI("stillframe", "worker initialized; configuration and OTA available");
#ifdef CONFIG_SF_RUNTIME_TEST
  if (!strcmp(cfg.device_id, "sf-power-reset"))
    sf_welcome_screen();
  if (!strcmp(cfg.device_id, "sf-panel-rollback") && sf_boot_pending()) {
    // Model an upgrade that started with a known-good panel. The emulator has
    // no e-paper peripheral, so its following real-driver attempt will fail.
    sf_test_assume_display_was_healthy();
    ESP_LOGW("startup-test", "INTENTIONAL PENDING-OTA PANEL FAILURE");
    sf_welcome_screen();
  }
  if (!strcmp(cfg.device_id, "sf-panel-prebroken") && sf_boot_pending()) {
    ESP_LOGW("startup-test", "INTENTIONAL PREEXISTING PANEL FAILURE");
    sf_welcome_screen();
  }
  bool safe_ota_test = !strcmp(cfg.device_id, "sf-safe-ota");
  bool safe_retry_test = !strcmp(cfg.device_id, "sf-safe-retry");
  if (safe_ota_test && safe_ota_stage != SAFE_OTA_STAGE_MAGIC &&
      !boot_safe_mode) {
    ESP_LOGE("startup-test", "INTENTIONAL SAFE-MODE PRE-OTA CRASH");
    abort();
  }
  if (safe_retry_test && safe_retry_stage != SAFE_RETRY_STAGE_MAGIC &&
      !boot_safe_mode) {
    ESP_LOGE("startup-test", "INTENTIONAL SAFE-RETRY PRE-STABLE CRASH");
    abort();
  }
  if (!strcmp(cfg.device_id, "sf-early-crash") && !boot_safe_mode) {
    ESP_LOGE("startup-test", "INTENTIONAL EARLY WORKER CRASH");
    abort();
  }
#endif
  if (!cfg.configured) {
    worker_cycle_ready = true;
    boot_guard_clear();
  }
  xSemaphoreGive(sf_operation);
  if (boot_safe_mode) {
    sf_enable_ap();
    worker_cycle_ready = true;
    sf_message("检测到连续启动异常，已暂停自动刷新；长按 SW4 可立即重试，也会在 30 分钟后自动重试");
    ESP_LOGE("stillframe", "three consecutive early resets; safe mode active");
#ifdef CONFIG_SF_RUNTIME_TEST
    if (!strcmp(cfg.device_id, "sf-early-crash"))
      ESP_LOGI("runtime-test", "EARLY RESET SAFE MODE TEST PASSED");
    if (safe_ota_test) {
      const esp_partition_t *next = esp_ota_get_next_update_partition(NULL);
      ESP_ERROR_CHECK(next ? esp_ota_set_boot_partition(next) : ESP_FAIL);
      safe_ota_stage = SAFE_OTA_STAGE_MAGIC;
      ESP_LOGI("startup-test",
               "SAFE MODE OTA WRITTEN; CLEARING OLD BOOT FAILURES");
      sf_prepare_ota_reboot();
      esp_restart();
    }
    if (safe_retry_test)
      ESP_ERROR_CHECK(xTaskCreate(safe_retry_busy_test, "safe_busy", 4096,
                                  NULL, 6, NULL) == pdPASS
                          ? ESP_OK
                          : ESP_FAIL);
#endif
  }
  int64_t heartbeat = esp_timer_get_time(), next = 0;
  int64_t safe_retry_at = heartbeat + 1800000000LL;
#ifdef CONFIG_SF_RUNTIME_TEST
  if (!strcmp(cfg.device_id, "sf-safe-retry"))
    safe_retry_at = heartbeat + 1000000LL;
#endif
  bool hide_help = !cfg.configured;
  bool manual_ap = false;
  bool first_cycle = cfg.configured && !boot_safe_mode;
  bool setup_pending = !cfg.configured && !boot_safe_mode;
  unsigned retry = 30;
  sf_config candidate;
  for (;;) {
    esp_task_wdt_reset();
    int64_t now = esp_timer_get_time();
    if (boot_safe_mode && safe_exit_requested) {
      if (!sf_restarting && !sf_config_pending &&
          xSemaphoreTake(sf_operation, 0) == pdTRUE) {
        if (!sf_restarting && !sf_config_pending) {
          sf_message("正在退出安全模式并重新启动");
#ifdef CONFIG_SF_RUNTIME_TEST
          if (!strcmp(cfg.device_id, "sf-safe-retry"))
            safe_retry_stage = SAFE_RETRY_STAGE_MAGIC;
#endif
          boot_guard_clear();
          sf_display_off();
          vTaskDelay(pdMS_TO_TICKS(200));
          esp_restart();
        }
        xSemaphoreGive(sf_operation);
      }
    }
    if (boot_safe_mode && now >= safe_retry_at) {
      // Automatic recovery must never interrupt an OTA, configuration save,
      // or MicroSD write. Acquire the same operation mutex as those paths and
      // recheck the restart/configuration flags after taking it.
      if (!sf_restarting && !sf_config_pending &&
          xSemaphoreTake(sf_operation, 0) == pdTRUE) {
        if (!sf_restarting && !sf_config_pending) {
          sf_message("安全模式已稳定 30 分钟，准备试运行");
#ifdef CONFIG_SF_RUNTIME_TEST
          if (!strcmp(cfg.device_id, "sf-safe-retry"))
            safe_retry_stage = SAFE_RETRY_STAGE_MAGIC;
#endif
          boot_guard_clear();
          sf_display_off();
          vTaskDelay(pdMS_TO_TICKS(200));
          esp_restart();
        }
        xSemaphoreGive(sf_operation);
      }
#ifdef CONFIG_SF_RUNTIME_TEST
      safe_retry_at = safe_retry_test ? now + 500000LL : now + 60000000LL;
#else
      safe_retry_at = now + 60000000LL;
#endif
    }
    if (sf_display_restart_due() && !manual_ap && !sf_config_pending &&
        !sf_restarting && xSemaphoreTake(sf_operation, 0) == pdTRUE) {
      // Recheck after acquiring the operation mutex. In particular, a local
      // album upload holds this mutex without setting either state flag.
      if (!manual_ap && !sf_config_pending && !sf_restarting) {
        sf_message("屏幕通信异常，正在安全重启后重试");
        sf_display_off();
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
      }
      xSemaphoreGive(sf_operation);
    }
    if (now - heartbeat >= 300000000) {
      heartbeat = now;
      ESP_LOGI("stillframe", "worker heartbeat; uptime=%lld seconds",
               (long long)(now / 1000000));
      ESP_LOGI("stillframe", "worker minimum free stack=%u bytes",
               (unsigned)uxTaskGetStackHighWaterMark(NULL));
    }
    if (sf_restarting) {
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    if (sf_ap_requested &&
        xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) == pdTRUE) {
      sf_ap_requested = false;
      esp_err_t e = sf_enable_ap();
      if (!e)
        manual_ap = true;
      sf_message(e ? "热点暂时无法开启，请稍后重试"
                   : "设置热点已开启：连接 Stillframe，访问 192.168.4.1");
      xSemaphoreGive(sf_operation);
    }
    if (setup_pending && sf_display_available() && !sf_display_wait_us() &&
        xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) == pdTRUE) {
      esp_err_t setup = sf_setup_screen();
      setup_pending = setup != ESP_OK;
      xSemaphoreGive(sf_operation);
    }
    if (xQueueReceive(changes, &candidate, 0) == pdTRUE) {
      if (xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) != pdTRUE) {
        xQueueSendToFront(changes, &candidate, 0);
        vTaskDelay(pdMS_TO_TICKS(200));
        continue;
      }
      sf_snapshot(&cfg);
      sf_message("正在检查配置，请稍候");
      esp_err_t e = ESP_OK;
      if (candidate.local && !sf_sd)
        e = sf_local_mount();
      if (!e && candidate.ssid[0])
        e = sf_connect(&candidate, 20000);
      if (!e && !candidate.local && !sf_connected)
        e = ESP_ERR_INVALID_STATE;
      if (!e) {
        candidate.configured = true;
        // A queued form can be older than the last completed display. Never
        // roll its acknowledgement back.
        if (candidate.local != cfg.local ||
            strcmp(candidate.server, cfg.server))
          candidate.photo_id[0] = 0;
        else
          strlcpy(candidate.photo_id, cfg.photo_id, sizeof(candidate.photo_id));
        if (!candidate.local)
          candidate.interval = cfg.interval;
        e = sf_save(&candidate);
      }
      if (!e) {
        sf_snapshot(&cfg);
        sf_message("配置已保存，正在读取照片和播放设置");
        manual_ap = false;
        if (!cfg.ssid[0])
          esp_wifi_disconnect();
        if (!cfg.local)
          sf_disable_ap();
        else
          sf_enable_ap();
        next = 0;
        setup_pending = false;
      } else {
        // A failed trial changed live station settings, but must not strand the
        // old saved setup.
        if (cfg.configured && cfg.ssid[0])
          sf_connect(&cfg, 20000);
        else
          esp_wifi_disconnect();
        sf_enable_ap();
        sf_message("配置未保存，已保留原设置并恢复设置热点；请检查 Wi-Fi 或 "
                   "MicroSD 卡");
      }
      sf_config_pending = false;
      xSemaphoreGive(sf_operation);
    }
    sf_snapshot(&cfg);
    if (!boot_safe_mode && !cfg.local && cfg.configured &&
        sf_network_take_reconnect()) {
      next = 0;
      sf_message("Wi-Fi 已断开，正在重新连接");
    }
    if (!boot_safe_mode && cfg.configured &&
        (sf_refresh_requested || esp_timer_get_time() >= next)) {
      if (xSemaphoreTake(sf_operation, pdMS_TO_TICKS(100)) == pdTRUE) {
        sf_network_power_save(false);
        sf_refresh_requested = false;
        esp_err_t e = ESP_OK;
        bool waiting = false;
        if (cfg.local) {
          if (sf_memory_fault) {
            sf_message("PSRAM 不足，无法载入本地照片；管理和升级仍可使用");
            e = ESP_ERR_NO_MEM;
          } else if (!sf_display_available()) {
            sf_message(sf_display_recovery_count() >= 3
                           ? "连续三次刷屏中断，已停止自动刷屏；请检查供电后断电重启"
                           : "屏幕通信已暂停，请检查连接后重启");
          } else if (sf_display_wait_us())
            waiting = true;
          else {
            if (!sf_sd)
              e = sf_local_mount();
            if (!e)
              e = sf_local_cycle();
            if (e == ESP_FAIL || e == ESP_ERR_NOT_FOUND)
              sf_local_unmount();
          }
        } else {
          if (!sf_connected)
            e = sf_connect(&cfg, 20000);
          esp_task_wdt_reset();
          if (!e)
            e = sf_server_cycle_due(sf_display_wait_us() == 0, &waiting);
        }
        sf_snapshot(&cfg);
        if (hide_help && !cfg.photo_id[0] && sf_display_available() &&
            !sf_display_wait_us()) {
          sf_welcome_screen();
          hide_help = false;
        } else if (cfg.photo_id[0])
          hide_help = false;
        if (e) {
          ESP_LOGW("stillframe", "cycle: %s", esp_err_to_name(e));
          bool panel_failed =
              sf_display_error() != ESP_OK && (cfg.local || sf_connected) &&
              (e == ESP_ERR_TIMEOUT || e == ESP_ERR_INVALID_STATE);
          sf_message(
              panel_failed
                  ? "照片已获取并校验，但屏幕通信失败。网络设置和升级仍可使用。"
              : cfg.local ? "本地播放失败，保留当前画面"
                          : "服务器暂不可用，稍后重试；保留当前画面");
          retry = retry < 150 ? retry * 2 : 300;
          next = esp_timer_get_time() + (int64_t)retry * 1000000;
        } else {
          if (!cfg.local && sf_connected && !manual_ap)
            sf_disable_ap();
          retry = 30;
          int64_t delay = (int64_t)cfg.interval * 1000000;
          if (waiting) {
            int64_t guard = sf_display_wait_us();
            if (guard < delay)
              delay = guard > 0 ? guard : 200000;
          }
          next = esp_timer_get_time() + delay;
        }
        sf_network_power_save(true);
        xSemaphoreGive(sf_operation);
        if (first_cycle) {
          first_cycle = false;
          worker_cycle_ready = true;
          boot_guard_clear();
          ESP_LOGI("stillframe", "first playback cycle returned; boot guard cleared");
        }
      }
    }
    vTaskDelay(pdMS_TO_TICKS(500));
  }
}
static void buttons(void *arg) {
  // Measured on ESP32-133C02-IL rev 2.0: GPIO12/13/14 idle high through
  // external pull-ups, so SW4 is active low. Never touch GPIO13: an internal
  // pull-down there trips the brownout detector about ten seconds later.
  gpio_config_t c = {.pin_bit_mask = 1ULL << 14, .mode = GPIO_MODE_INPUT};
  gpio_config(&c);
  ESP_LOGI("stillframe", "SW4 idle level=%d", gpio_get_level(14));
  unsigned held = 0;
  // Ignore a line that is already low at boot until it has been released.
  bool fired = !gpio_get_level(14);
  for (;;) {
    if (!gpio_get_level(14)) {
      held++;
      if (held >= 50 && !fired) {
        if (boot_safe_mode)
          safe_exit_requested = true;
        else
          sf_ap_requested = true;
        fired = true;
      }
    } else {
      held = 0;
      fired = false;
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
void app_main(void) {
#ifdef CONFIG_SF_TEST_PANIC
  ESP_LOGE("safety-test", "INTENTIONAL STARTUP FAILURE before validation");
  abort();
#endif
#ifdef CONFIG_SF_TEST_MODE
  boot_safe_mode = false;
#else
  boot_safe_mode = boot_guard_begin();
#endif
  ESP_LOGI("stillframe", "Stillframe " SF_VERSION " starting");
  esp_err_t storage = sf_state_init();
  if (storage) {
    if (!sf_lock || !sf_operation)
      abort();
    sf_storage_fault = true;
    ESP_LOGE("stillframe",
             "configuration unavailable (%s); preserve NVS and start recovery "
             "portal",
             esp_err_to_name(storage));
    esp_ota_img_states_t boot_state;
    if (esp_ota_get_state_partition(esp_ota_get_running_partition(),
                                    &boot_state) == ESP_OK &&
        boot_state == ESP_OTA_IMG_PENDING_VERIFY)
      esp_ota_mark_app_invalid_rollback_and_reboot();
  }
  ESP_LOGI("stillframe", "identity=%s configured=%d local=%d interval=%lu",
           sf_cfg.device_id, sf_cfg.configured, sf_cfg.local,
           (unsigned long)sf_cfg.interval);
  changes = xQueueCreate(1, sizeof(sf_config));
  if (!changes)
    abort();
  ESP_ERROR_CHECK(sf_display_init());
  ESP_ERROR_CHECK(sf_network_init());
  ESP_ERROR_CHECK(sf_web_start());
  sf_memory_fault = heap_caps_get_total_size(MALLOC_CAP_SPIRAM) < SF_BYTES;
  if (sf_memory_fault) {
    ESP_LOGE("stillframe",
             "PSRAM unavailable; photo playback paused, web and OTA remain available");
    sf_message("PSRAM 不足，已暂停照片播放；管理网页和固件升级仍可使用");
    if (sf_boot_pending())
      esp_ota_mark_app_invalid_rollback_and_reboot();
  }
#ifndef CONFIG_SF_TEST_MODE
  if (xTaskCreate(worker, "stillframe_worker", 12288, NULL, 5, NULL) != pdPASS)
    abort();
  if (xTaskCreate(buttons, "stillframe_buttons", 3072, NULL, 3, NULL) != pdPASS)
    abort();
#endif
#ifdef CONFIG_SF_TEST_MODE
  vTaskDelay(pdMS_TO_TICKS(1000));
#else
  // Give startup tasks time to run; external WiFi/NAS availability is not a
  // boot-health condition.
  vTaskDelay(pdMS_TO_TICKS(10000));
#endif
  // Local service health qualifies firmware; NAS availability and panel BUSY do
  // not.
  esp_ota_img_states_t state;
  const esp_partition_t *running = esp_ota_get_running_partition();
  if (esp_ota_get_state_partition(running, &state) == ESP_OK &&
      state == ESP_OTA_IMG_PENDING_VERIFY && !sf_storage_fault) {
#ifndef CONFIG_SF_TEST_MODE
    // A running HTTP listener alone is insufficient: never accept an image
    // whose worker is stuck initializing SD or the initial display.
    int64_t until = esp_timer_get_time() + 30000000LL;
    while (!worker_boot_ready && esp_timer_get_time() < until)
      vTaskDelay(pdMS_TO_TICKS(100));
    if (!worker_boot_ready || boot_safe_mode) {
      ESP_LOGE("stillframe",
               "startup worker not ready; rolling back unverified app");
      esp_ota_mark_app_invalid_rollback_and_reboot();
      abort();
    }
    sf_config startup_cfg;
    sf_snapshot(&startup_cfg);
    if (startup_cfg.configured) {
      until = esp_timer_get_time() + 300000000LL;
      while (!worker_cycle_ready && esp_timer_get_time() < until)
        vTaskDelay(pdMS_TO_TICKS(100));
      if (!worker_cycle_ready) {
        ESP_LOGE("stillframe",
                 "first playback cycle did not return; rolling back app");
        esp_ota_mark_app_invalid_rollback_and_reboot();
        abort();
      }
      if (sf_display_was_healthy_before_boot() &&
          sf_display_attempt_failed()) {
        ESP_LOGE("stillframe",
                 "previously healthy panel failed during first OTA cycle; "
                 "rolling back app");
        esp_ota_mark_app_invalid_rollback_and_reboot();
        abort();
      }
      if (sf_display_attempt_failed())
        ESP_LOGW("stillframe", "panel was already unverified or unhealthy; "
                               "keep OTA image so a repair can be installed");
    }
#endif
    ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
    ESP_LOGI("stillframe", "OTA self-test passed; app marked valid");
    // Report the confirmed image immediately instead of waiting an hour for
    // the next scheduled photo synchronization.
    sf_refresh_requested = true;
  }
  ESP_LOGI(
      "stillframe",
      "startup services ready; storage=%s panel=%s; AP Stillframe 192.168.4.1",
      sf_storage_fault ? "recovery" : "ready",
      esp_err_to_name(sf_display_error()));
#ifdef CONFIG_SF_RUNTIME_TEST
  extern void sf_run_runtime_tests(void);
  sf_run_runtime_tests();
#endif
#ifdef CONFIG_SF_TEST_MODE
  extern void sf_run_tests(void);
  sf_run_tests();
  return;
#else
  // Keep the IDF main task parked. The brownout once blamed on returning from
  // app_main was caused by a pull-down on GPIO13 (see buttons()); this loop is
  // harmless and consumes no meaningful CPU.
  for (;;)
    vTaskDelay(pdMS_TO_TICKS(1000));
#endif
}
