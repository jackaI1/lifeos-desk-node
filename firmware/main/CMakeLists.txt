idf_component_register(SRCS "app_main.c" "desk_network.c" INCLUDE_DIRS "."
    REQUIRES desk_core desk_drivers esp_wifi esp_event esp_netif esp_http_client
    mbedtls bootloader_support nvs_flash esp_timer esp_hw_support lwip)
