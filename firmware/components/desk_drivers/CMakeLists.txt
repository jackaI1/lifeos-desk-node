idf_component_register(SRCS "desk_drivers.c" "desk_ssd1306.c" INCLUDE_DIRS "include"
    REQUIRES desk_core esp_driver_i2c esp_driver_gpio esp_driver_spi esp_driver_uart freertos)
