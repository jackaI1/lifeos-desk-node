#include "desk_drivers.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#define I2C_TIMEOUT_MS 100

esp_err_t desk_drivers_init(desk_drivers_t *d) {
    *d=(desk_drivers_t){0};
    i2c_master_bus_config_t config={.i2c_port=I2C_NUM_0,.sda_io_num=GPIO_NUM_21,
        .scl_io_num=GPIO_NUM_22,.clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7};
    esp_err_t err=i2c_new_master_bus(&config,&d->bus);
    if (err!=ESP_OK) return err;
    i2c_device_config_t sensor={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x44,.scl_speed_hz=100000};
    i2c_device_config_t display=sensor; display.device_address=0x3c;
    err=i2c_master_bus_add_device(d->bus,&sensor,&d->sensor);
    if (err==ESP_OK) err=i2c_master_bus_add_device(d->bus,&display,&d->display);
    if (err!=ESP_OK) desk_drivers_deinit(d);
    return err;
}
esp_err_t desk_sensor_read(desk_drivers_t *d,desk_reading_t *reading) {
    if (!d->sensor) return ESP_ERR_INVALID_STATE;
    const uint8_t command[]={0x24,0x00}; uint8_t bytes[6];
    esp_err_t err=i2c_master_transmit(d->sensor,command,sizeof command,I2C_TIMEOUT_MS);
    if (err!=ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(20)); /* High repeatability worst-case conversion <16 ms. */
    err=i2c_master_receive(d->sensor,bytes,sizeof bytes,I2C_TIMEOUT_MS);
    if (err==ESP_OK && !desk_decode_sht31(bytes,reading)) return ESP_ERR_INVALID_CRC;
    return err;
}
esp_err_t desk_display_frame(desk_drivers_t *d,const uint8_t frame[DESK_FRAME_SIZE]) {
    if (!d->display) return ESP_ERR_INVALID_STATE;
    /* SSD1306 128x64 internal charge pump, horizontal address mode. */
    const uint8_t init[]={0x00,0xae,0xd5,0x80,0xa8,0x3f,0xd3,0x00,0x40,0x8d,0x14,
        0x20,0x00,0xa1,0xc8,0xda,0x12,0x81,0x40,0xd9,0xf1,0xdb,0x40,0xa4,0xa6,0x2e,
        0x21,0,127,0x22,0,7};
    esp_err_t err=i2c_master_transmit(d->display,init,sizeof init,I2C_TIMEOUT_MS);
    uint8_t chunk[33]; chunk[0]=0x40;
    for (size_t offset=0;err==ESP_OK && offset<DESK_FRAME_SIZE;offset+=32) {
        memcpy(chunk+1,frame+offset,32);
        err=i2c_master_transmit(d->display,chunk,sizeof chunk,I2C_TIMEOUT_MS);
    }
    const uint8_t on[]={0x00,0xaf};
    if (err==ESP_OK) err=i2c_master_transmit(d->display,on,sizeof on,I2C_TIMEOUT_MS);
    return err;
}
void desk_drivers_deinit(desk_drivers_t *d) {
    if (d->sensor) i2c_master_bus_rm_device(d->sensor);
    if (d->display) i2c_master_bus_rm_device(d->display);
    if (d->bus) i2c_del_master_bus(d->bus);
    *d=(desk_drivers_t){0};
    /* External pull-ups keep the OLED bus idle during CPU sleep. */
}
