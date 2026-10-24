#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "stillframe.h"
#include <string.h>
static EventGroupHandle_t events;
static portMUX_TYPE reconnect_gate = portMUX_INITIALIZER_UNLOCKED;
static bool connecting, reconnect_requested;

static void configure_captive_portal(void) {
  esp_netif_t *ap = esp_netif_get_handle_from_ifkey("WIFI_AP_DEF");
  if (!ap) {
    ESP_LOGW("wifi", "cannot advertise setup portal: AP netif missing");
    return;
  }
  static const char portal[] = "http://192.168.4.1/";
  esp_err_t stopped = esp_netif_dhcps_stop(ap);
  if (stopped != ESP_OK &&
      stopped != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED)
    ESP_LOGW("wifi", "DHCP stop before portal option failed: %s",
             esp_err_to_name(stopped));
  esp_err_t e = esp_netif_dhcps_option(
      ap, ESP_NETIF_OP_SET, ESP_NETIF_CAPTIVEPORTAL_URI, (void *)portal,
      strlen(portal));
  if (e)
    ESP_LOGW("wifi", "captive portal DHCP option failed: %s",
             esp_err_to_name(e));
  e = esp_netif_dhcps_start(ap);
  if (e && e != ESP_ERR_ESP_NETIF_DHCP_ALREADY_STARTED)
    ESP_LOGW("wifi", "DHCP restart failed: %s", esp_err_to_name(e));
  if (!e || e == ESP_ERR_ESP_NETIF_DHCP_ALREADY_STARTED)
    ESP_LOGI("wifi", "setup portal advertised by DHCP: %s", portal);
}
bool sf_network_take_reconnect(void) {
  taskENTER_CRITICAL(&reconnect_gate);
  bool requested = reconnect_requested;
  reconnect_requested = false;
  taskEXIT_CRITICAL(&reconnect_gate);
  return requested;
}
void sf_network_power_save(bool idle) {
  static int previous = -1;
  // Provisioning must favor a stable AP.  Modem sleep while APSTA is serving
  // the setup portal caused short client disconnects and bursts of lost ICMP
  // packets on real hardware.  Once the AP is off, use modem sleep normally.
  wifi_ps_type_t ps = sf_ap ? WIFI_PS_NONE
                            : (idle ? WIFI_PS_MAX_MODEM : WIFI_PS_MIN_MODEM);
  if (previous == (int)ps)
    return;
  esp_err_t e = esp_wifi_set_ps(ps);
  if (!e)
    previous = ps;
  else
    ESP_LOGW("power", "Wi-Fi power save unchanged: %s", esp_err_to_name(e));
}
static void wifi_event(void *arg, esp_event_base_t base, int32_t id,
                       void *data) {
  if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
    sf_connected = true;
    xEventGroupSetBits(events, 1);
  }
  if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
    sf_connected = false;
    xEventGroupClearBits(events, 1);
    taskENTER_CRITICAL(&reconnect_gate);
    if (!connecting)
      reconnect_requested = true;
    taskEXIT_CRITICAL(&reconnect_gate);
  }
  if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STACONNECTED) {
    wifi_event_ap_staconnected_t *event = data;
    ESP_LOGI("wifi", "setup client %02x:%02x:%02x:%02x:%02x:%02x joined",
             event->mac[0], event->mac[1], event->mac[2], event->mac[3],
             event->mac[4], event->mac[5]);
  }
  if (base == WIFI_EVENT && id == WIFI_EVENT_AP_STADISCONNECTED) {
    wifi_event_ap_stadisconnected_t *event = data;
    ESP_LOGW("wifi",
             "setup client %02x:%02x:%02x:%02x:%02x:%02x left; reason=%u",
             event->mac[0], event->mac[1], event->mac[2], event->mac[3],
             event->mac[4], event->mac[5], (unsigned)event->reason);
  }
}
esp_err_t sf_enable_ap(void) {
  sf_config c;
  sf_snapshot(&c);
  wifi_mode_t mode;
  esp_err_t e = esp_wifi_get_mode(&mode);
  if (e)
    return e;
  // A brand-new frame has no station to connect.  Keep provisioning in pure
  // AP mode so background STA activity cannot interrupt the setup link.  A
  // configured frame (or a configuration trial) uses APSTA temporarily.
  wifi_mode_t wanted = c.ssid[0] ? WIFI_MODE_APSTA : WIFI_MODE_AP;
  if (mode != wanted) {
    e = esp_wifi_set_mode(wanted);
    if (e)
      return e;
  }
  wifi_config_t ap = {.ap = {
#ifdef CONFIG_SF_OPEN_AP_DIAGNOSTIC
                             .ssid = "Stillframe-Test",
                             .ssid_len = 15,
#else
                             .ssid = "Stillframe",
                             .ssid_len = 10,
#endif
                             .channel = 1,
                             .max_connection = 4,
#ifdef CONFIG_SF_OPEN_AP_DIAGNOSTIC
                             .authmode = WIFI_AUTH_OPEN}};
  ap.ap.password[0] = 0;
#else
                             .authmode = WIFI_AUTH_WPA2_PSK}};
  strlcpy((char *)ap.ap.password, c.ap_password, sizeof(ap.ap.password));
#endif
  e = esp_wifi_set_config(WIFI_IF_AP, &ap);
  if (!e)
    sf_ap = true;
  return e;
}
esp_err_t sf_disable_ap(void) {
  if (!sf_ap)
    return ESP_OK;
  esp_err_t e = esp_wifi_set_mode(WIFI_MODE_STA);
  if (!e)
    sf_ap = false;
  return e;
}
esp_err_t sf_network_init(void) {
  events = xEventGroupCreate();
  if (!events)
    return ESP_ERR_NO_MEM;
  ESP_ERROR_CHECK(esp_netif_init());
  ESP_ERROR_CHECK(esp_event_loop_create_default());
  if (!esp_netif_create_default_wifi_sta() ||
      !esp_netif_create_default_wifi_ap())
    return ESP_ERR_NO_MEM;
  wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
  if (sf_storage_fault)
    init.nvs_enable = 0;
  esp_err_t e = esp_wifi_init(&init);
  if (e)
    return e;
  ESP_ERROR_CHECK(esp_wifi_set_storage(
      WIFI_STORAGE_RAM)); // Credentials live in our atomic NVS record only.
  ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                             wifi_event, NULL));
  ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                             wifi_event, NULL));
  ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_APSTA));
  ESP_ERROR_CHECK(sf_enable_ap());
  e = esp_wifi_start();
  if (e)
    return e;
  configure_captive_portal();
  return ESP_OK;
}
esp_err_t sf_connect(const sf_config *cfg, unsigned timeout_ms) {
  if (!cfg->ssid[0])
    return ESP_ERR_INVALID_ARG;
  wifi_mode_t mode;
  esp_err_t e = esp_wifi_get_mode(&mode);
  if (e)
    return e;
  wifi_mode_t wanted = sf_ap ? WIFI_MODE_APSTA : WIFI_MODE_STA;
  if (mode != wanted && (e = esp_wifi_set_mode(wanted)))
    return e;
  taskENTER_CRITICAL(&reconnect_gate);
  connecting = true;
  reconnect_requested = false;
  taskEXIT_CRITICAL(&reconnect_gate);
  esp_wifi_disconnect();
  sf_connected = false;
  xEventGroupClearBits(events, 1);
  sf_network_power_save(false);
  e = sf_station_configure(cfg);
  if (e)
    goto done;
  e = esp_wifi_connect();
  if (e)
    goto done;
  int64_t deadline = esp_timer_get_time() + (int64_t)timeout_ms * 1000;
  do {
    esp_task_wdt_reset();
    if (xEventGroupWaitBits(events, 1, pdFALSE, pdTRUE, pdMS_TO_TICKS(100)) &
        1) {
      e = ESP_OK;
      goto done;
    }
  } while (esp_timer_get_time() < deadline);
  e = ESP_ERR_TIMEOUT;
done:
  taskENTER_CRITICAL(&reconnect_gate);
  connecting = false;
  taskEXIT_CRITICAL(&reconnect_gate);
  return e;
}

esp_err_t sf_station_configure(const sf_config *cfg) {
  wifi_config_t station = {0};
  station.sta.listen_interval = 3;
  memcpy(station.sta.ssid, cfg->ssid,
         strnlen(cfg->ssid, sizeof(station.sta.ssid)));
  memcpy(station.sta.password, cfg->wifi_password,
         strnlen(cfg->wifi_password, sizeof(station.sta.password)));
  return esp_wifi_set_config(WIFI_IF_STA, &station);
}
