#include "http_guard.h"
#include "esp_crt_bundle.h"
#include "esp_sntp.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_transport.h"
#include "esp_transport_ssl.h"
#include "esp_transport_tcp.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
  esp_transport_handle_t outer, inner;
  int64_t deadline;
} guard;
static int remaining(guard *g, int limit) {
  int64_t us = g->deadline - esp_timer_get_time();
  if (us <= 0) {
    errno = ETIMEDOUT;
    return 0;
  }
  int ms = (us + 999) / 1000;
  return limit > 0 && ms > limit ? limit : ms;
}
static int connect_guard(esp_transport_handle_t t, const char *host, int port,
                         int timeout) {
  guard *g = esp_transport_get_context_data(t);
  int ms = remaining(g, timeout);
  if (!ms)
    return -1;
  esp_task_wdt_reset();
  int n = esp_transport_connect(g->inner, host, port, ms);
  esp_task_wdt_reset();
  return n;
}
static int read_guard(esp_transport_handle_t t, char *buf, int len,
                      int timeout) {
  guard *g = esp_transport_get_context_data(t);
  int64_t idle =
      esp_timer_get_time() + (int64_t)(timeout > 0 ? timeout : 10000) * 1000;
  for (;;) {
    int ms = remaining(g, 1000);
    if (!ms || esp_timer_get_time() >= idle) {
      errno = ETIMEDOUT;
      return 0;
    }
    esp_task_wdt_reset();
    int n = esp_transport_read(g->inner, buf, len, ms);
    esp_task_wdt_reset();
    if (n != 0)
      return n;
  }
}
static int write_guard(esp_transport_handle_t t, const char *buf, int len,
                       int timeout) {
  guard *g = esp_transport_get_context_data(t);
  int ms = remaining(g, timeout);
  if (!ms)
    return -1;
  esp_task_wdt_reset();
  int n = esp_transport_write(g->inner, buf, len, ms);
  esp_task_wdt_reset();
  return n;
}
static int close_guard(esp_transport_handle_t t) {
  guard *g = esp_transport_get_context_data(t);
  return esp_transport_close(g->inner);
}
static int poll_read_guard(esp_transport_handle_t t, int timeout) {
  guard *g = esp_transport_get_context_data(t);
  int ms = remaining(g, timeout);
  return ms ? esp_transport_poll_read(g->inner, ms) : 0;
}
static int poll_write_guard(esp_transport_handle_t t, int timeout) {
  guard *g = esp_transport_get_context_data(t);
  int ms = remaining(g, timeout);
  return ms ? esp_transport_poll_write(g->inner, ms) : 0;
}
static int destroy_guard(esp_transport_handle_t t) {
  guard *g = esp_transport_get_context_data(t);
  esp_transport_destroy(g->inner);
  free(g);
  return 0;
}
esp_http_client_handle_t sf_http_client(const sf_config *cfg, const char *path,
                                        unsigned total_ms) {
  if (!cfg || !path || path[0] != '/' || path[1] == '/' || strchr(path, '\r') ||
      strchr(path, '\n') || !total_ms)
    return NULL;
  bool tls = !strncmp(cfg->server, "https://", 8);
  if (!tls && strncmp(cfg->server, "http://", 7))
    return NULL;
  if (tls && !esp_sntp_enabled()) {
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
  }
  char url[800], auth[208];
  if (snprintf(url, sizeof(url), "%s%s", cfg->server, path) >= (int)sizeof(url))
    return NULL;
  guard *g = calloc(1, sizeof(*g));
  if (!g)
    return NULL;
  g->deadline = esp_timer_get_time() + (int64_t)total_ms * 1000;
  g->outer = esp_transport_init();
  g->inner = tls ? esp_transport_ssl_init() : esp_transport_tcp_init();
  if (!g->inner || !g->outer) {
    if (g->inner)
      esp_transport_destroy(g->inner);
    if (g->outer)
      esp_transport_destroy(g->outer);
    free(g);
    return NULL;
  }
  if (tls)
    esp_transport_ssl_crt_bundle_attach(g->inner, esp_crt_bundle_attach);
  esp_transport_set_context_data(g->outer, g);
  esp_transport_set_default_port(g->outer, tls ? 443 : 80);
  esp_transport_set_func(g->outer, connect_guard, read_guard, write_guard,
                         close_guard, poll_read_guard, poll_write_guard,
                         destroy_guard);
  esp_http_client_config_t c = {.url = url,
                                .timeout_ms = 10000,
                                .buffer_size = 4096,
                                .disable_auto_redirect = true,
                                .transport = g->outer,
                                .user_data = g};
  esp_http_client_handle_t h = esp_http_client_init(&c);
  if (!h) {
    esp_transport_destroy(g->outer);
    return NULL;
  }
  snprintf(auth, sizeof(auth), "Bearer %s", cfg->token);
  esp_http_client_set_header(h, "Authorization", auth);
  return h;
}
void sf_http_cleanup(esp_http_client_handle_t h) {
  if (!h)
    return;
  guard *g = NULL;
  esp_http_client_get_user_data(h, (void **)&g);
  esp_http_client_cleanup(h);
  if (g)
    esp_transport_destroy(g->outer);
}
