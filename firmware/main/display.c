// GDEP133C02 two-controller SPI protocol; register values from Good Display
// reference.
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "stillframe.h"
#include <string.h>
static spi_device_handle_t bus;
static const int cs[2] = {18, 17};
// DMA may finish after a timeout. Keep its descriptor and buffer alive until
// reboot, and quarantine the bus so a late completion never references returned
// stack data.
static spi_transaction_ext_t pending;
static DMA_ATTR uint8_t dma_tx[300];
static bool bus_faulted;
static esp_err_t last_error;
static int64_t last_attempt = -180000000LL;
static int64_t restart_at = -1;
static bool fault_recorded;
static bool attempted, attempt_failed, healthy_before_boot_attempt;
#define DISPLAY_RTC_MAGIC 0x53464453u
typedef struct {
  uint32_t magic, failures, in_progress, last_success, check;
} display_rtc_state;
static RTC_NOINIT_ATTR display_rtc_state recovery;
static uint32_t recovery_check(void) {
  return recovery.magic ^ recovery.failures ^ recovery.in_progress ^
         recovery.last_success ^
         0xa57f31c9u;
}
static void recovery_write(unsigned failures, bool in_progress,
                           bool last_success) {
  recovery.magic = DISPLAY_RTC_MAGIC;
  recovery.failures = failures;
  recovery.in_progress = in_progress;
  recovery.last_success = last_success;
  recovery.check = recovery_check();
}
static void recovery_init(void) {
  if (recovery.magic != DISPLAY_RTC_MAGIC || recovery.check != recovery_check())
    recovery_write(0, false, false);
  else if (recovery.in_progress) {
    unsigned failures = recovery.failures < 100 ? recovery.failures + 1 : 3;
    recovery_write(failures, false, false);
  }
  healthy_before_boot_attempt =
      recovery.failures == 0 && recovery.last_success;
  if (recovery.failures)
    last_attempt = 0; // A reset during refresh must not bypass the 3-minute guard.
  if (recovery.failures >= 3) {
    last_error = ESP_ERR_INVALID_STATE;
    ESP_LOGE("display",
             "three refresh resets detected; automatic display disabled");
  }
}
static esp_err_t display_finish(esp_err_t e) {
  if (!e) {
    recovery_write(0, false, true);
    fault_recorded = false;
  } else {
    recovery_write(recovery.failures, false, false);
    if (bus_faulted && !fault_recorded) {
      fault_recorded = true;
      unsigned failures = recovery.failures < 100 ? recovery.failures + 1 : 3;
      recovery_write(failures, false, false);
      if (failures < 3)
        restart_at = esp_timer_get_time() + 180000000LL;
    }
  }
  return e;
}
bool sf_display_available(void) {
#ifdef CONFIG_SF_PANEL_MAINTENANCE
  return false;
#else
  return bus && !bus_faulted && recovery.failures < 3;
#endif
}
int64_t sf_display_wait_us(void) {
  int64_t wait = last_attempt + 180000000LL - esp_timer_get_time();
  return wait > 0 ? wait : 0;
}
esp_err_t sf_display_error(void) { return last_error; }
bool sf_display_maintenance(void) {
#ifdef CONFIG_SF_PANEL_MAINTENANCE
  return true;
#else
  return false;
#endif
}
bool sf_display_restart_due(void) {
  return bus_faulted && restart_at >= 0 && esp_timer_get_time() >= restart_at;
}
unsigned sf_display_recovery_count(void) {
  return recovery.magic == DISPLAY_RTC_MAGIC ? recovery.failures : 0;
}
bool sf_display_attempt_failed(void) { return attempted && attempt_failed; }
bool sf_display_was_healthy_before_boot(void) {
  return healthy_before_boot_attempt;
}
#ifdef CONFIG_SF_RUNTIME_TEST
void sf_test_assume_display_was_healthy(void) {
  healthy_before_boot_attempt = true;
}
#endif
static esp_err_t send_spi(uint8_t command, unsigned command_bits,
                          const uint8_t *data, size_t len) {
  if (bus_faulted)
    return ESP_ERR_INVALID_STATE;
  if (len > sizeof(dma_tx) || (len && !data))
    return ESP_ERR_INVALID_ARG;
  memset(&pending, 0, sizeof(pending));
  if (len)
    memcpy(dma_tx, data, len);
  pending.base.flags = SPI_TRANS_VARIABLE_CMD;
  pending.base.cmd = command;
  pending.base.length = len * 8;
  pending.base.tx_buffer = len ? dma_tx : NULL;
  pending.command_bits = command_bits;
  esp_task_wdt_reset();
  esp_err_t e = spi_device_queue_trans(bus, &pending.base, pdMS_TO_TICKS(3000));
  if (!e) {
    spi_transaction_t *completed = NULL;
    e = spi_device_get_trans_result(bus, &completed, pdMS_TO_TICKS(3000));
    if (!e && completed != &pending.base)
      e = ESP_ERR_INVALID_STATE;
  }
  esp_task_wdt_reset();
  if (e) {
    last_error = e;
    bus_faulted = true;
    sf_display_off();
    ESP_LOGE("display",
             "SPI command 0x%02x failed (%s); bus quarantined until reboot",
             command, esp_err_to_name(e));
  }
  return e;
}
static esp_err_t transfer(int target, uint8_t command, const uint8_t *data,
                          size_t len) {
  if (bus_faulted)
    return ESP_ERR_INVALID_STATE;
  gpio_set_level(cs[target], 0);
  esp_err_t e = send_spi(command, 8, data, len);
  gpio_set_level(cs[target], 1);
  return e;
}
static esp_err_t both(uint8_t command, const uint8_t *data, size_t len) {
  // The vendor reference does not initialize the two controllers one after
  // another.  It selects both CS lines and clocks each common command once so
  // the two halves remain in exactly the same controller state.  Sequential
  // writes happen to work in the emulator, but a real GDEP133C02 can finish a
  // refresh with a pale yellow residual image when the controllers are not
  // initialized in lockstep.
  if (bus_faulted)
    return ESP_ERR_INVALID_STATE;
  gpio_set_level(cs[0], 0);
  gpio_set_level(cs[1], 0);
  esp_err_t e = send_spi(command, 8, data, len);
  gpio_set_level(cs[0], 1);
  gpio_set_level(cs[1], 1);
  return e;
}
static esp_err_t ready(void) {
  int64_t until = esp_timer_get_time() + 120000000;
  do {
    if (gpio_get_level(7))
      return ESP_OK;
    esp_task_wdt_reset();
    vTaskDelay(pdMS_TO_TICKS(20));
  } while (esp_timer_get_time() < until);
  last_error = ESP_ERR_TIMEOUT;
  ESP_LOGE("display", "BUSY timeout; power off");
  sf_display_off();
  return ESP_ERR_TIMEOUT;
}
static esp_err_t busy_cycle(void) {
  // BUSY_N is active low.  Immediately after a command the pin can still be
  // high for a short time; treating that old high level as completion races
  // the controller and can power the panel down in the middle of a refresh.
  int64_t assert_until = esp_timer_get_time() + 5000000LL;
  while (gpio_get_level(7)) {
    esp_task_wdt_reset();
    if (esp_timer_get_time() >= assert_until) {
      last_error = ESP_ERR_TIMEOUT;
      ESP_LOGE("display", "BUSY did not assert after refresh command");
      sf_display_off();
      return ESP_ERR_TIMEOUT;
    }
    vTaskDelay(pdMS_TO_TICKS(2));
  }
  return ready();
}
void sf_display_off(void) {
  gpio_set_level(45, 0);
  gpio_set_level(6, 0);
}
esp_err_t sf_display_init(void) {
  recovery_init();
  gpio_config_t out = {.pin_bit_mask = (1ULL << 18) | (1ULL << 17) |
                                       (1ULL << 6) | (1ULL << 45),
                       .mode = GPIO_MODE_OUTPUT};
  esp_err_t e = gpio_config(&out);
  if (e)
    return e;
  gpio_set_level(18, 1);
  gpio_set_level(17, 1);
  sf_display_off();
#ifdef CONFIG_SF_PANEL_MAINTENANCE
  last_error = ESP_ERR_NOT_SUPPORTED;
  ESP_LOGW("display",
           "panel maintenance mode; power, reset and SPI remain disabled");
  return ESP_OK;
#endif
  gpio_config_t in = {.pin_bit_mask = 1ULL << 7, .mode = GPIO_MODE_INPUT};
  if ((e = gpio_config(&in)))
    return e;
  spi_bus_config_t b = {.mosi_io_num = 41,
                        .miso_io_num = 40,
                        .sclk_io_num = 9,
                        .quadwp_io_num = -1,
                        .quadhd_io_num = -1,
                        .max_transfer_sz = 32768};
  if ((e = spi_bus_initialize(SPI3_HOST, &b, SPI_DMA_CH_AUTO)))
    return e;
  spi_device_interface_config_t d = {.command_bits = 8,
                                     .clock_speed_hz = 10000000,
                                     .duty_cycle_pos = 128,
                                     .mode = 0,
                                     .spics_io_num = -1,
                                     .queue_size = 1,
                                     .cs_ena_posttrans = 3};
  return spi_bus_add_device(SPI3_HOST, &d, &bus);
}
#define TRY(call)                                                              \
  do {                                                                         \
    esp_err_t err = (call);                                                    \
    if (err) {                                                                 \
      last_error = err;                                                        \
      attempt_failed = true;                                                   \
      sf_display_off();                                                        \
      return display_finish(err);                                               \
    }                                                                          \
  } while (0)
esp_err_t sf_display(const uint8_t *pixels) {
#ifdef CONFIG_SF_PANEL_MAINTENANCE
  (void)pixels;
  sf_display_off();
  last_error = ESP_ERR_NOT_SUPPORTED;
  return last_error;
#else
  bool power_reset_test = false;
#ifdef CONFIG_SF_TEST_MODE
  extern esp_err_t sf_test_panel(const uint8_t *pixels);
  attempted = true;
  last_error = sf_test_panel(pixels);
  attempt_failed = last_error != ESP_OK;
  return last_error;
#endif
#ifdef CONFIG_SF_RUNTIME_TEST
  sf_config runtime_cfg;
  sf_snapshot(&runtime_cfg);
  power_reset_test = !strcmp(runtime_cfg.device_id, "sf-power-reset");
  if (!strcmp(runtime_cfg.device_id, "sf-slow-setup")) {
    attempted = true;
    attempt_failed = false;
    last_attempt = esp_timer_get_time();
    recovery_write(recovery.failures, true, recovery.last_success);
    ESP_LOGW("startup-test", "INTENTIONAL 40-SECOND SETUP DISPLAY");
    for (int i = 0; i < 400; i++) {
      esp_task_wdt_reset();
      vTaskDelay(pdMS_TO_TICKS(100));
    }
    last_error = ESP_OK;
    return display_finish(ESP_OK);
  }
#endif
  if (!bus || !pixels || bus_faulted)
    return ESP_ERR_INVALID_STATE;
  if (recovery.failures >= 3) {
    last_error = ESP_ERR_INVALID_STATE;
    return ESP_ERR_INVALID_STATE;
  }
  if (sf_display_wait_us() && !power_reset_test)
    return ESP_ERR_INVALID_STATE;
  attempted = true;
  attempt_failed = false;
  last_attempt = esp_timer_get_time();
  last_error = ESP_OK;
  recovery_write(recovery.failures, true, recovery.last_success);
#ifdef CONFIG_SF_RUNTIME_TEST
  if (power_reset_test) {
    ESP_LOGE("startup-test", "INTENTIONAL RESET DURING HIGH-VOLTAGE REFRESH");
    abort();
  }
#endif
  ESP_LOGI("display", "starting panel reset");
  gpio_set_level(45, 1);
  vTaskDelay(pdMS_TO_TICKS(20));
  gpio_set_level(6, 0);
  vTaskDelay(pdMS_TO_TICKS(20));
  gpio_set_level(6, 1);
  vTaskDelay(pdMS_TO_TICKS(20));
  TRY(ready());
  ESP_LOGI("display", "reset complete; initializing controllers");
  const uint8_t an[] = {0xc0, 0x1e, 0x1e, 0xce, 0xce, 0xce, 0x15, 0x15, 0x55};
  TRY(transfer(0, 0x74, an, sizeof(an)));
  const struct {
    uint8_t cmd, n, d[8];
  } init[] = {{0xf0, 6, {0x49, 0x55, 0x13, 0x5d, 0x05, 0x10}},
              {0x00, 2, {0xdf, 0x69}},
              {0x50, 1, {0xf7}},
              {0x60, 2, {3, 3}},
              {0x86, 1, {0x10}},
              {0xe3, 1, {0x22}},
              {0xe0, 1, {1}},
              {0x61, 4, {4, 0xb0, 3, 0x20}}};
  for (unsigned i = 0; i < sizeof(init) / sizeof(init[0]); i++)
    TRY(both(init[i].cmd, init[i].d, init[i].n));
  const struct {
    uint8_t cmd, n, d[6];
  } power[] = {{0x01, 6, {0x0f, 0, 0x28, 0x2c, 0x28, 0x38}},
               {0xb6, 1, {7}},
               {0x06, 2, {0xe8, 0x28}},
               {0xb7, 1, {1}},
               {0x05, 2, {0xe8, 0x28}},
               {0xb0, 1, {1}},
               {0xb1, 1, {2}}};
  for (unsigned i = 0; i < sizeof(power) / sizeof(power[0]); i++)
    TRY(transfer(0, power[i].cmd, power[i].d, power[i].n));
  // Hold chip select throughout DTM, then stream the corresponding 300 bytes of
  // EVERY row.
  for (int chip = 0; chip < 2; chip++) {
    gpio_set_level(cs[chip], 0);
    esp_err_t e = send_spi(0x10, 8, NULL, 0);
    for (int row = 0; !e && row < SF_HEIGHT; row++) {
      e = send_spi(0, 0, pixels + row * 600 + chip * 300, 300);
      esp_task_wdt_reset();
      if ((row & 15) == 15)
        taskYIELD();
    }
    gpio_set_level(cs[chip], 1);
    TRY(e);
  }
  // The vendor sequence broadcasts PON/DRF/POF with both controllers selected
  // and keeps both CS lines low until BUSY completes.
  gpio_set_level(cs[0], 0);
  gpio_set_level(cs[1], 0);
  esp_err_t e = send_spi(0x04, 8, NULL, 0);
  if (!e)
    e = busy_cycle();
  gpio_set_level(cs[0], 1);
  gpio_set_level(cs[1], 1);
  TRY(e);
  uint8_t one = 1, zero = 0;
  gpio_set_level(cs[0], 0);
  gpio_set_level(cs[1], 0);
  vTaskDelay(pdMS_TO_TICKS(30));
  e = send_spi(0x12, 8, &one, 1);
  if (!e)
    e = busy_cycle();
  gpio_set_level(cs[0], 1);
  gpio_set_level(cs[1], 1);
  TRY(e);
  gpio_set_level(cs[0], 0);
  gpio_set_level(cs[1], 0);
  e = send_spi(0x02, 8, &zero, 1);
  if (!e)
    e = busy_cycle();
  gpio_set_level(cs[0], 1);
  gpio_set_level(cs[1], 1);
  TRY(e);
  // Match the vendor reference during hardware qualification: POF disables
  // the panel's high-voltage rails, while LOAD_SW keeps logic power present.
  // Do not immediately pull LOAD_SW and RESET low; that can interrupt the
  // controller's final settling after BUSY returns high.
  ESP_LOGI("display", "frame sent; POF complete, panel logic power retained");
  attempt_failed = false;
  return display_finish(ESP_OK);
#endif
}
extern const uint8_t setup_start[] asm("_binary_setup_bin_start");
esp_err_t sf_setup_screen(void) {
#ifdef CONFIG_SF_PANEL_MAINTENANCE
  sf_message("屏幕维护模式：屏幕电源已禁用，可继续配置网络和升级固件");
  return ESP_ERR_NOT_SUPPORTED;
#else
  sf_config cfg;
  sf_snapshot(&cfg);
  // Only the factory artwork includes credentials. After the password changes,
  // never render the old password again.
  if (!cfg.configured && strcmp(cfg.ap_password, "12345678") == 0) {
    sf_message("连接 Stillframe 热点后，访问 192.168.4.1");
    esp_err_t e = sf_display(setup_start);
    if (e)
      sf_message(
          "屏幕初始化失败，仍可设置网络或更新固件；请检查屏幕连接后重启");
    return e;
  }
  return ESP_OK;
#endif
}

extern const uint8_t welcome_start[] asm("_binary_welcome_bin_start");
void sf_welcome_screen(void) { sf_display(welcome_start); }
