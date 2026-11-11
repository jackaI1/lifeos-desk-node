set(desk_srcs "app_main.c" "desk_network.c" "desk_health.c")
if(CONFIG_DESK_BLE_ENABLE)
    list(APPEND desk_srcs "desk_ble.c")
endif()
idf_component_register(SRCS ${desk_srcs} INCLUDE_DIRS "."
    REQUIRES bt desk_radio desk_core desk_ess desk_drivers desk_can esp_wifi esp_event esp_netif esp_http_client
    mbedtls bootloader_support nvs_flash esp_timer esp_hw_support lwip)
