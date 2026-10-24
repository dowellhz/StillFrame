#pragma once
#include "esp_http_client.h"
#include "stillframe.h"
// Caller owns the returned client and must use sf_http_cleanup (also frees the
// guarded TCP/TLS transport). No redirects or cross-origin credentials.
esp_http_client_handle_t sf_http_client(const sf_config *cfg, const char *path,
                                        unsigned total_ms);
void sf_http_cleanup(esp_http_client_handle_t client);
