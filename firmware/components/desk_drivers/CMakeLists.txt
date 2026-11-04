idf_component_register(SRCS "desk_drivers.c" INCLUDE_DIRS "include"
    REQUIRES desk_core esp_driver_i2c esp_driver_gpio freertos)
