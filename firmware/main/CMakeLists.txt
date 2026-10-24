idf_component_register(SRCS "main.c" "state.c" "display.c" "protocol.c" "network.c" "web.c" "local.c" "rom.c" "http_guard.c"
 INCLUDE_DIRS "." REQUIRES tcp_transport esp_wifi esp_event esp_netif nvs_flash esp_http_server esp_http_client app_update spi_flash esp_driver_spi esp_driver_gpio fatfs sdmmc json lwip mbedtls esp_timer esp_system esp_pm
 EMBED_FILES "../assets/index.html" "../assets/setup.bin" "../assets/welcome.bin")
if(CONFIG_SF_TEST_MODE)
 target_sources(${COMPONENT_LIB} PRIVATE "selftest.c" "network_fault_test.c")
 target_add_binary_data(${COMPONENT_LIB} "../test-fixtures/nas-sync.json" BINARY)
 target_add_binary_data(${COMPONENT_LIB} "../test-fixtures/nas-frame.bin" BINARY)
 target_add_binary_data(${COMPONENT_LIB} "../test-assets/panic.bin" BINARY)
endif()

if(CONFIG_SF_RUNTIME_TEST)
 target_sources(${COMPONENT_LIB} PRIVATE "runtime_test.c")
endif()

target_link_libraries(${COMPONENT_LIB} INTERFACE "-u sf_hardware")
