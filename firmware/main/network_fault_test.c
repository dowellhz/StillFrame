// Real in-guest TCP fault server. No mocking of the IDF HTTP client or
// transport.
#include "esp_log.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "http_guard.h"
#include "lwip/sockets.h"
#include <stdlib.h>
#include <string.h>
#define VERIFY(x, msg)                                                         \
  do {                                                                         \
    if (!(x)) {                                                                \
      ESP_LOGE("network-test", "FAIL: %s", msg);                               \
      abort();                                                                 \
    }                                                                          \
    ESP_LOGI("network-test", "PASS: %s", msg);                                 \
  } while (0)
static void slow_server(void *arg) {
  TaskHandle_t parent = arg;
  int listener = socket(AF_INET, SOCK_STREAM, 0), one = 1;
  VERIFY(listener >= 0, "create in-guest TCP fault server");
  setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  struct sockaddr_in addr = {.sin_family = AF_INET,
                             .sin_port = htons(8487),
                             .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
  VERIFY(bind(listener, (struct sockaddr *)&addr, sizeof(addr)) == 0 &&
             listen(listener, 2) == 0,
         "listen in-guest fault server");
  xTaskNotifyGive(parent);
  const char *headers =
      "HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n";
  for (int mode = 0; mode < 2; mode++) {
    int fd = accept(listener, NULL, NULL);
    VERIFY(fd >= 0, "accept fault test connection");
    char request[512];
    struct timeval timeout = {.tv_sec = 3};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    recv(fd, request, sizeof(request), 0);
    if (mode == 1)
      send(fd, headers, strlen(headers), 0);
    for (int i = 0; i < 30; i++) {
      const char *byte = mode == 0 ? headers + i : "x";
      if (send(fd, byte, 1, 0) < 0)
        break;
      vTaskDelay(pdMS_TO_TICKS(100));
    }
    close(fd);
    xTaskNotifyGive(parent);
  }
  close(listener);
  vTaskDelete(NULL);
}
void sf_network_fault_tests(void) {
  VERIFY(xTaskCreate(slow_server, "slow_http", 4096,
                     xTaskGetCurrentTaskHandle(), 4, NULL) == pdPASS,
         "start fault test server");
  VERIFY(ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(3000)) > 0,
         "wait for fault server ready");
  sf_config cfg = {0};
  strcpy(cfg.server, "http://127.0.0.1:8487");
  strcpy(cfg.token, "fault-test");
  for (int mode = 0; mode < 2; mode++) {
    esp_http_client_handle_t h = sf_http_client(&cfg, "/", 700);
    VERIFY(h, "allocate deadline-limited HTTP client");
    int64_t start = esp_timer_get_time();
    VERIFY(esp_http_client_open(h, 0) == ESP_OK,
           "connect deadline test client");
    int64_t length = esp_http_client_fetch_headers(h);
    if (!mode)
      VERIFY(length < 0,
             "partial trickled headers stop at the total request deadline");
    else {
      VERIFY(length == 1000, "body fault response headers received");
      char buf[1000];
      int got = esp_http_client_read(h, buf, sizeof(buf));
      VERIFY(got < 1000 && !esp_http_client_is_complete_data_received(h),
             "partial trickled body is never accepted as a complete download");
    }
    VERIFY(
        esp_timer_get_time() - start < 1500000,
        "slow peer cannot extend request lifetime by sending small fragments");
    sf_http_cleanup(h);
    esp_task_wdt_reset();
    VERIFY(ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(5000)) > 0,
           "fault server releases closed connection");
  }
}
