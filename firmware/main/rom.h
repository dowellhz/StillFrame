#pragma once
#include "esp_app_desc.h"
#include "esp_app_format.h"
#include "esp_ota_ops.h"
#include "stillframe.h"
typedef struct {
  char magic[16], board[32], panel[24];
  uint32_t protocol;
  uint16_t width, height;
  uint32_t flags;
} sf_hardware_descriptor;
extern const sf_hardware_descriptor sf_hardware;
#define SF_ROM_HEADER_BYTES                                                    \
  (sizeof(esp_image_header_t) + sizeof(esp_image_segment_header_t) +           \
   sizeof(esp_app_desc_t) + sizeof(sf_hardware_descriptor))
bool sf_rom_header_valid(const uint8_t *buf, size_t len);
esp_err_t sf_running_sha(char out[65]);
esp_err_t sf_remote_update(cJSON *offer, const sf_config *cfg);

bool sf_boot_pending(void);
