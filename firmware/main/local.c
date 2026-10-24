#include "driver/sdspi_host.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"
#include "stillframe.h"
#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#define SF_LOCAL_INDEX_MAX 262144
static bool index_valid(cJSON *j);
static sdmmc_card_t *card;
static bool spi_ready;
void sf_local_unmount(void) {
  if (!sf_sd)
    return;
  esp_vfs_fat_sdcard_unmount("/sd", card);
  card = NULL;
  sf_sd = false;
}
esp_err_t sf_local_mount(void) {
  if (sf_sd)
    return ESP_OK;
  if (!spi_ready) {
    spi_bus_config_t b = {.mosi_io_num = 3,
                          .miso_io_num = 5,
                          .sclk_io_num = 8,
                          .quadwp_io_num = -1,
                          .quadhd_io_num = -1,
                          .max_transfer_sz = 4096};
    esp_err_t e = spi_bus_initialize(SPI2_HOST, &b, SPI_DMA_CH_AUTO);
    if (e)
      return e;
    spi_ready = true;
  }
  sdmmc_host_t host = SDSPI_HOST_DEFAULT();
  host.slot = SPI2_HOST;
  sdspi_device_config_t slot = SDSPI_DEVICE_CONFIG_DEFAULT();
  slot.gpio_cs = 15;
  slot.host_id = SPI2_HOST;
  esp_vfs_fat_sdmmc_mount_config_t m = {.format_if_mount_failed = false,
                                        .max_files = 5,
                                        .allocation_unit_size = 16384};
  esp_err_t e = esp_vfs_fat_sdspi_mount("/sd", &host, &slot, &m, &card);
  if (e)
    return e;
  mkdir("/sd/stillframe", 0775);
  sf_sd = true;
  return ESP_OK;
}
static cJSON *read_index_file(const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return NULL;
  fseek(f, 0, SEEK_END);
  long size = ftell(f);
  rewind(f);
  if (size < 1 || size > SF_LOCAL_INDEX_MAX) {
    fclose(f);
    return NULL;
  }
  char *data = malloc(size + 1);
  if (!data) {
    fclose(f);
    return NULL;
  }
  size_t used = fread(data, 1, size, f);
  fclose(f);
  data[used] = 0;
  cJSON *j = used == (size_t)size ? cJSON_Parse(data) : NULL;
  free(data);
  if (j && !index_valid(j)) {
    cJSON_Delete(j);
    return NULL;
  }
  return j;
}
static cJSON *index_read(void) {
  cJSON *j = read_index_file("/sd/stillframe/index.json");
  if (j)
    return j;
  j = read_index_file("/sd/stillframe/index.bak");
  if (j)
    return j;
  struct stat st;
  if (stat("/sd/stillframe", &st))
    return NULL;
  if (access("/sd/stillframe/index.json", F_OK) == 0 ||
      access("/sd/stillframe/index.bak", F_OK) == 0)
    return NULL;
  j = cJSON_CreateObject();
  cJSON_AddArrayToObject(j, "categories");
  cJSON_AddArrayToObject(j, "photos");
  return j;
}
static esp_err_t index_save(cJSON *j) {
  char *s = cJSON_PrintUnformatted(j);
  if (!s)
    return ESP_ERR_NO_MEM;
  if (strlen(s) > SF_LOCAL_INDEX_MAX || !index_valid(j)) {
    free(s);
    return ESP_ERR_INVALID_SIZE;
  }
  FILE *f = fopen("/sd/stillframe/index.tmp", "wb");
  if (!f) {
    free(s);
    return ESP_FAIL;
  }
  bool ok = fwrite(s, 1, strlen(s), f) == strlen(s);
  free(s);
  if (fclose(f))
    ok = false;
  // FAT rename cannot replace an existing path: keep a recoverable backup
  // across the operation.
  if (!ok)
    return ESP_FAIL;
  // Preserve the last parseable index, even if recovering from a corrupt
  // primary.
  cJSON *previous = read_index_file("/sd/stillframe/index.json");
  if (previous) {
    cJSON_Delete(previous);
    remove("/sd/stillframe/index.bak");
    if (rename("/sd/stillframe/index.json", "/sd/stillframe/index.bak"))
      return ESP_FAIL;
  } else
    remove("/sd/stillframe/index.json");
  return rename("/sd/stillframe/index.tmp", "/sd/stillframe/index.json") == 0
             ? ESP_OK
             : ESP_FAIL;
}
static const char *str(cJSON *j, const char *name) {
  cJSON *v = cJSON_GetObjectItemCaseSensitive(j, name);
  return cJSON_IsString(v) ? v->valuestring : "";
}
static bool id_ok(const char *id) {
  if (!*id || strlen(id) > 48)
    return false;
  for (; *id; id++)
    if (!isalnum((unsigned char)*id) && *id != '-' && *id != '_')
      return false;
  return true;
}
static cJSON *find(cJSON *a, const char *id) {
  cJSON *p;
  cJSON_ArrayForEach(p, a) if (!strcmp(str(p, "id"), id)) return p;
  return NULL;
}
static bool index_valid(cJSON *j) {
  cJSON *photos = cJSON_GetObjectItemCaseSensitive(j, "photos"),
        *cats = cJSON_GetObjectItemCaseSensitive(j, "categories"), *p;
  if (!cJSON_IsArray(photos) || !cJSON_IsArray(cats))
    return false;
  cJSON_ArrayForEach(p, cats) {
    const char *id = str(p, "id"), *parent = str(p, "parentId");
    if (!id_ok(id) || find(cats, id) != p || !str(p, "name")[0] ||
        strlen(str(p, "name")) > 120)
      return false;
    for (int depth = 0; parent[0]; depth++) {
      if (depth >= 16 || !strcmp(parent, id))
        return false;
      cJSON *ancestor = find(cats, parent);
      if (!ancestor)
        return false;
      parent = str(ancestor, "parentId");
    }
  }
  cJSON_ArrayForEach(p, photos) {
    const char *id = str(p, "id"), *sha = str(p, "sha256"),
               *category = str(p, "categoryId");
    if (!id_ok(id) || find(photos, id) != p || strlen(sha) != 64 ||
        strlen(str(p, "title")) > 159 || (category[0] && !find(cats, category)))
      return false;
    for (int i = 0; i < 64; i++)
      if (!isxdigit((unsigned char)sha[i]))
        return false;
  }
  return true;
}
#ifdef CONFIG_SF_TEST_MODE
bool sf_test_local_index_valid(cJSON *j) {
  char *s = cJSON_PrintUnformatted(j);
  bool ok = s && strlen(s) <= SF_LOCAL_INDEX_MAX && index_valid(j);
  free(s);
  return ok;
}
#endif
static void decode_url(char *s) {
  char *r = s, *w = s;
  while (*r) {
    if (*r == '%' && r[1] && r[2] && isxdigit((unsigned char)r[1]) &&
        isxdigit((unsigned char)r[2])) {
      char hex[3] = {r[1], r[2], 0};
      *w++ = (char)strtol(hex, NULL, 16);
      r += 3;
    } else {
      *w++ = *r == '+' ? ' ' : *r;
      r++;
    }
  }
  *w = 0;
}
static void filename(char *path, size_t cap, const char *id) {
  snprintf(path, cap, "/sd/stillframe/%s.bin", id);
}
static esp_err_t sendjson(httpd_req_t *r, cJSON *j) {
  char *s = cJSON_PrintUnformatted(j);
  if (!s)
    return ESP_ERR_NO_MEM;
  httpd_resp_set_type(r, "application/json");
  esp_err_t e = httpd_resp_sendstr(r, s);
  free(s);
  return e;
}
static esp_err_t fail(httpd_req_t *r, const char *message) {
  httpd_resp_set_status(r, "400 Bad Request");
  return httpd_resp_sendstr(r, message);
}
static bool in_category(cJSON *cats, const char *current, const char *chosen) {
  for (int depth = 0; depth < 16; depth++) {
    if (!strcmp(current, chosen))
      return true;
    if (!*current)
      return false;
    cJSON *c = find(cats, current);
    if (!c)
      return false;
    current = str(c, "parentId");
  }
  return false;
}
esp_err_t sf_local_cycle(void) {
  cJSON *j = index_read();
  if (!j)
    return ESP_FAIL;
  sf_config cfg;
  sf_snapshot(&cfg);
  cJSON *a = cJSON_GetObjectItem(j, "photos"),
        *cats = cJSON_GetObjectItem(j, "categories");
  int selected = -1, found = -1, count = 0;
  cJSON *p;
  cJSON_ArrayForEach(p, a) {
    if (cfg.category[0] &&
        !in_category(cats, str(p, "categoryId"), cfg.category))
      continue;
    if (!strcmp(str(p, "id"), cfg.photo_id))
      found = count;
    count++;
  }
  if (!count) {
    cJSON_Delete(j);
    sf_message("请在本地相册上传照片");
    return ESP_OK;
  }
  selected = cfg.random ? (int)(esp_random() % count) : (found + 1) % count;
  if (cfg.random && count > 1 && selected == found)
    selected = (selected + 1 + esp_random() % (count - 1)) % count;
  uint8_t *pixels =
      heap_caps_malloc(SF_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!pixels) {
    cJSON_Delete(j);
    return ESP_ERR_NO_MEM;
  }
  esp_err_t e = ESP_ERR_NOT_FOUND;
  // A missing or corrupt photo must not pin playback to that same index on
  // every retry. Try each eligible entry once, preserving the current frame.
  for (int attempt = 0; attempt < count; attempt++) {
    int wanted = (selected + attempt) % count, at = 0;
    cJSON *photo = NULL;
    cJSON_ArrayForEach(p, a) {
      if (cfg.category[0] &&
          !in_category(cats, str(p, "categoryId"), cfg.category))
        continue;
      if (at++ == wanted) {
        photo = p;
        break;
      }
    }
    esp_task_wdt_reset();
    if (!photo)
      continue;
    char shown_sha[65];
    sf_photo_sha(shown_sha);
    if (!strcmp(str(photo, "id"), cfg.photo_id) &&
        !strcasecmp(str(photo, "sha256"), shown_sha)) {
      sf_message("本地照片未变化，保留当前画面");
      e = ESP_OK;
      break;
    }
    char path[128];
    filename(path, sizeof(path), str(photo, "id"));
    FILE *f = fopen(path, "rb");
    if (!f) {
      if (errno == ENOENT)
        continue;
      e = ESP_FAIL;
      break;
    }
    size_t used = 0;
    while (used < SF_BYTES) {
      size_t chunk = SF_BYTES - used < 16384 ? SF_BYTES - used : 16384;
      size_t n = fread(pixels + used, 1, chunk, f);
      used += n;
      esp_task_wdt_reset();
      if (n != chunk)
        break;
    }
    int extra = fgetc(f);
    bool read_error = ferror(f);
    fclose(f);
    e = read_error     ? ESP_FAIL
        : extra == EOF ? sf_validate_frame(pixels, used, str(photo, "sha256"))
                       : ESP_ERR_INVALID_SIZE;
    if (e)
      continue;
    e = sf_display(pixels);
    if (!e) {
      strlcpy(cfg.photo_id, str(photo, "id"), sizeof(cfg.photo_id));
      e = sf_save(&cfg);
      if (!e) {
        esp_err_t saved_sha = sf_save_photo_sha(str(photo, "sha256"));
        if (saved_sha)
          ESP_LOGW("local", "display SHA was not persisted: %s",
                   esp_err_to_name(saved_sha));
        sf_message("本地照片已更新");
      }
    }
    break;
  }
  free(pixels);
  cJSON_Delete(j);
  return e;
}

esp_err_t sf_local_api(void *request) {
  httpd_req_t *r = request;
  if (!sf_sd && sf_local_mount())
    return fail(r, "未检测到 MicroSD 卡，请插卡后重试");
  cJSON *j = index_read();
  if (!j) {
    sf_local_unmount();
    return fail(r, "本地相册索引损坏，请检查 MicroSD 卡");
  }
  cJSON *photos = cJSON_GetObjectItem(j, "photos"),
        *cats = cJSON_GetObjectItem(j, "categories");
  esp_err_t e = ESP_OK;
  bool storage_error = false;
  char remove_after[128] = {0};
  if (strncmp(r->uri, "/api/local/bin", 14) == 0) {
    char query[512], id[64], sha[65], title[160], category[64];
    if (httpd_req_get_url_query_str(r, query, sizeof(query)) ||
        httpd_query_key_value(query, "id", id, sizeof(id)) || !id_ok(id)) {
      e = fail(r, "照片 ID 无效");
      goto done;
    }
    char path[128];
    filename(path, sizeof(path), id);
    if (r->method == HTTP_GET) {
      FILE *f = fopen(path, "rb");
      if (!f) {
        e = fail(r, "照片不存在");
        goto done;
      }
      httpd_resp_set_type(r, "application/octet-stream");
      uint8_t chunk[4096];
      size_t n;
      while ((n = fread(chunk, 1, sizeof(chunk), f))) {
        e = httpd_resp_send_chunk(r, (char *)chunk, n);
        if (e)
          break;
      }
      if (ferror(f)) {
        storage_error = true;
        e = ESP_FAIL;
      }
      fclose(f);
      if (!e)
        e = httpd_resp_send_chunk(r, NULL, 0);
      goto done;
    }
    if (r->content_len != SF_BYTES ||
        httpd_req_get_hdr_value_str(r, "X-SHA256", sha, sizeof(sha)) ||
        strlen(sha) != 64 || find(photos, id)) {
      e = fail(r, "照片大小、校验值或 ID 无效");
      goto done;
    }
    title[0] = category[0] = 0;
    httpd_query_key_value(query, "title", title, sizeof(title));
    httpd_query_key_value(query, "category", category, sizeof(category));
    decode_url(title);
    decode_url(category);
    if (category[0] && !find(cats, category)) {
      e = fail(r, "分类不存在");
      goto done;
    }
    uint8_t *data =
        heap_caps_malloc(SF_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!data) {
      e = fail(r, "内存不足");
      goto done;
    }
    size_t used = 0;
    int64_t upload_deadline = esp_timer_get_time() + 120000000LL;
    while (used < SF_BYTES && esp_timer_get_time() < upload_deadline) {
      int n = httpd_req_recv(r, (char *)data + used, SF_BYTES - used);
      if (n <= 0)
        break;
      used += n;
    }
    e = sf_validate_frame(data, used, sha);
    if (!e) {
      FILE *f = fopen(path, "wb");
      if (!f) {
        storage_error = true;
        e = ESP_FAIL;
      } else {
        if (fwrite(data, 1, SF_BYTES, f) != SF_BYTES) {
          storage_error = true;
          e = ESP_FAIL;
        }
        if (fclose(f)) {
          storage_error = true;
          e = ESP_FAIL;
        }
      }
    }
    free(data);
    if (!e) {
      cJSON *photo = cJSON_CreateObject();
      cJSON_AddStringToObject(photo, "id", id);
      cJSON_AddStringToObject(photo, "title", title[0] ? title : id);
      cJSON_AddStringToObject(photo, "categoryId", category);
      cJSON_AddStringToObject(photo, "sha256", sha);
      cJSON_AddItemToArray(photos, photo);
      e = index_save(j);
      storage_error = e != ESP_OK;
    }
    if (e) {
      remove(path);
      e = fail(r, "上传失败，照片未加入相册");
    } else
      e = httpd_resp_sendstr(r, "照片已上传");
    goto done;
  }
  if (r->method == HTTP_GET) {
    uint64_t total = 0, free_space = 0;
    if (esp_vfs_fat_info("/sd", &total, &free_space) != ESP_OK) {
      sf_local_unmount();
      cJSON_Delete(j);
      return fail(r, "MicroSD 卡读取失败，请重新插卡后重试");
    }
    cJSON_AddNumberToObject(j, "totalBytes", total);
    cJSON_AddNumberToObject(j, "freeBytes", free_space);
    e = sendjson(r, j);
    goto done;
  }
  if (r->content_len <= 0 || r->content_len > 1024) {
    e = fail(r, "请求无效");
    goto done;
  }
  char buf[1025];
  size_t used = 0;
  int64_t action_deadline = esp_timer_get_time() + 10000000LL;
  while (used < r->content_len && esp_timer_get_time() < action_deadline) {
    int n = httpd_req_recv(r, buf + used, r->content_len - used);
    if (n <= 0)
      break;
    used += n;
  }
  buf[used] = 0;
  cJSON *action = used == r->content_len ? cJSON_Parse(buf) : NULL;
  if (!action) {
    e = fail(r, "JSON 无效");
    goto done;
  }
  const char *op = str(action, "action"), *id = str(action, "id");
  if (!strcmp(op, "category")) {
    const char *name = str(action, "name"), *parent = str(action, "parentId");
    if (!id_ok(id) || !*name || strlen(name) > 120 ||
        (parent[0] && !find(cats, parent)) || !strcmp(parent, id)) {
      e = ESP_ERR_INVALID_ARG;
    } else {
      const char *ancestor = parent;
      for (int depth = 0; *ancestor && depth < 17; depth++) {
        if (!strcmp(ancestor, id) || depth == 16) {
          e = ESP_ERR_INVALID_ARG;
          break;
        }
        cJSON *p = find(cats, ancestor);
        ancestor = p ? str(p, "parentId") : "";
      }
      if (!e) {
        cJSON *c = find(cats, id);
        if (!c) {
          c = cJSON_CreateObject();
          cJSON_AddStringToObject(c, "id", id);
          cJSON_AddStringToObject(c, "name", name);
          cJSON_AddStringToObject(c, "parentId", parent);
          cJSON_AddItemToArray(cats, c);
        } else {
          cJSON_ReplaceItemInObject(c, "name", cJSON_CreateString(name));
          cJSON_ReplaceItemInObject(c, "parentId", cJSON_CreateString(parent));
        }
      }
    }
  } else if (!strcmp(op, "deletePhoto")) {
    cJSON *p = find(photos, id);
    if (!p || !id_ok(id))
      e = ESP_ERR_INVALID_ARG;
    else {
      cJSON_DetachItemViaPointer(photos, p);
      cJSON_Delete(p);
      filename(remove_after, sizeof(remove_after), id);
    }
  } else if (!strcmp(op, "deleteCategory")) {
    cJSON *p;
    bool used_category = false;
    cJSON_ArrayForEach(p, cats) if (!strcmp(str(p, "parentId"), id))
        used_category = true;
    cJSON_ArrayForEach(p, photos) if (!strcmp(str(p, "categoryId"), id))
        used_category = true;
    p = find(cats, id);
    if (used_category || !p)
      e = ESP_ERR_INVALID_ARG;
    else {
      cJSON_DetachItemViaPointer(cats, p);
      cJSON_Delete(p);
    }
  } else
    e = ESP_ERR_INVALID_ARG;
  if (!e) {
    e = index_save(j);
    if (e)
      storage_error = true;
  }
  if (!e && remove_after[0])
    remove(remove_after);
  cJSON_Delete(action);
  e = e ? fail(r,
               "保存失败：请检查分类名称、父分类，删除前请先移走照片和子分类")
        : httpd_resp_sendstr(r, "已保存");
done:
  cJSON_Delete(j);
  if (storage_error)
    sf_local_unmount();
  return e;
}
