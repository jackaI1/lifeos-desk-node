#include "desk_drivers.h"
#include "desk_ssd1306.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "driver/uart_vfs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>
#define I2C_TIMEOUT_MS 100
#define DISPLAY_HOST SPI2_HOST
#define DISPLAY_CLOCK GPIO_NUM_18
#define DISPLAY_MOSI GPIO_NUM_23
#define DISPLAY_CS GPIO_NUM_27
#define DISPLAY_DC GPIO_NUM_26
#define DISPLAY_RESET GPIO_NUM_25

static esp_err_t display_init(desk_drivers_t *d) {
#if CONFIG_DESK_DISPLAY_SPI
    /* Set output latches before enabling GPIO drivers. Do not reset the retained
       display while Wi-Fi/API work is still pending. Board pull-ups hold idle. */
    gpio_set_level(DISPLAY_CS,1); gpio_set_level(DISPLAY_RESET,1); gpio_set_level(DISPLAY_DC,0);
    gpio_config_t gpio={.pin_bit_mask=(1ULL<<DISPLAY_CS)|(1ULL<<DISPLAY_DC)|(1ULL<<DISPLAY_RESET),
        .mode=GPIO_MODE_OUTPUT,.pull_up_en=GPIO_PULLUP_DISABLE,.pull_down_en=GPIO_PULLDOWN_DISABLE,
        .intr_type=GPIO_INTR_DISABLE};
    esp_err_t err=gpio_config(&gpio);
    if (err!=ESP_OK) return err;
    d->display_gpio_initialized=true;
    spi_bus_config_t bus={.mosi_io_num=DISPLAY_MOSI,.miso_io_num=-1,.sclk_io_num=DISPLAY_CLOCK,
        .quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=DESK_FRAME_SIZE};
    err=spi_bus_initialize(DISPLAY_HOST,&bus,SPI_DMA_CH_AUTO);
    if (err!=ESP_OK) return err;
    d->spi_initialized=true;
    spi_device_interface_config_t device={.clock_speed_hz=4000000,.mode=0,
        .spics_io_num=DISPLAY_CS,.queue_size=1};
    return spi_bus_add_device(DISPLAY_HOST,&device,&d->display_spi);
#else
    if (!d->bus) return ESP_ERR_INVALID_STATE;
    i2c_device_config_t device={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x3c,.scl_speed_hz=100000};
    return i2c_master_bus_add_device(d->bus,&device,&d->display_i2c);
#endif
}
esp_err_t desk_drivers_init(desk_drivers_t *d) {
    *d=(desk_drivers_t){0};
    i2c_master_bus_config_t config={.i2c_port=I2C_NUM_0,.sda_io_num=GPIO_NUM_21,
        .scl_io_num=GPIO_NUM_22,.clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7};
    esp_err_t sensor_error=i2c_new_master_bus(&config,&d->bus);
    if (sensor_error==ESP_OK) {
        i2c_device_config_t sensor={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x44,.scl_speed_hz=100000};
        sensor_error=i2c_master_bus_add_device(d->bus,&sensor,&d->sensor);
    }
    esp_err_t display_error=display_init(d);
    return sensor_error!=ESP_OK ? sensor_error : display_error;
}
esp_err_t desk_sensor_read(desk_drivers_t *d,desk_reading_t *reading) {
    if (!d->sensor) return ESP_ERR_INVALID_STATE;
    const uint8_t command[]={0x24,0x00}; uint8_t bytes[6];
    esp_err_t err=i2c_master_transmit(d->sensor,command,sizeof command,I2C_TIMEOUT_MS);
    if (err!=ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(20));
    err=i2c_master_receive(d->sensor,bytes,sizeof bytes,I2C_TIMEOUT_MS);
    if (err==ESP_OK && !desk_decode_sht31(bytes,reading)) return ESP_ERR_INVALID_CRC;
    return err;
}
static bool display_write(void *context,bool data,const uint8_t *bytes,size_t length) {
    desk_drivers_t *d=context;
#if CONFIG_DESK_DISPLAY_SPI
    if (gpio_set_level(DISPLAY_DC,data?1:0)!=ESP_OK) return false;
    spi_transaction_t transfer={.length=length*8,.tx_buffer=bytes};
    /* Synchronous transfer: D/C cannot change until all bytes are clocked out.
       The IDF DMA driver copies non-DMA/alignment-constrained input if needed. */
    return spi_device_transmit(d->display_spi,&transfer)==ESP_OK;
#else
    uint8_t chunk[33]; chunk[0]=data?0x40:0x00;
    for (size_t offset=0;offset<length;offset+=32) {
        size_t count=length-offset; if (count>32) count=32;
        memcpy(chunk+1,bytes+offset,count);
        if (i2c_master_transmit(d->display_i2c,chunk,count+1,I2C_TIMEOUT_MS)!=ESP_OK) return false;
    }
    return true;
#endif
}
esp_err_t desk_display_frame(desk_drivers_t *d,const uint8_t frame[DESK_FRAME_SIZE]) {
#if CONFIG_DESK_DISPLAY_SPI
    if (!d->display_spi) return ESP_ERR_INVALID_STATE;
    /* SSD1306 reset is active low. Keep data transfers out of the reset interval. */
    gpio_set_level(DISPLAY_RESET,0); vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level(DISPLAY_RESET,1); vTaskDelay(pdMS_TO_TICKS(10));
#else
    if (!d->display_i2c) return ESP_ERR_INVALID_STATE;
#endif
    return desk_ssd1306_frame(frame,display_write,d) ? ESP_OK : ESP_FAIL;
}
void desk_drivers_deinit(desk_drivers_t *d) {
    if (d->sensor) i2c_master_bus_rm_device(d->sensor);
    if (d->display_i2c) i2c_master_bus_rm_device(d->display_i2c);
    if (d->bus) i2c_del_master_bus(d->bus);
    if (d->display_spi) spi_bus_remove_device(d->display_spi);
    if (d->spi_initialized) spi_bus_free(DISPLAY_HOST);
    if (d->display_gpio_initialized) {
        /* Release to external CS/RESET pull-ups and D/C pull-down during sleep. */
        gpio_set_level(DISPLAY_CS,1); gpio_set_level(DISPLAY_RESET,1); gpio_set_level(DISPLAY_DC,0);
        gpio_reset_pin(DISPLAY_CS); gpio_reset_pin(DISPLAY_RESET); gpio_reset_pin(DISPLAY_DC);
        gpio_set_pull_mode(DISPLAY_CS,GPIO_FLOATING); gpio_set_pull_mode(DISPLAY_RESET,GPIO_FLOATING);
        gpio_set_pull_mode(DISPLAY_DC,GPIO_FLOATING);
    }
    *d=(desk_drivers_t){0};
}
esp_err_t desk_uart_init(void) {
    uart_config_t config={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,
        .stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    esp_err_t err=uart_param_config(UART_NUM_0,&config);
    if (err==ESP_OK) err=uart_set_pin(UART_NUM_0,GPIO_NUM_1,GPIO_NUM_3,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE);
    if (err==ESP_OK) err=uart_driver_install(UART_NUM_0,256,512,0,NULL,0);
    if (err==ESP_OK) uart_vfs_dev_use_driver(UART_NUM_0);
    return err;
}
esp_err_t desk_uart_log_cycle(const desk_reading_t *reading,uint32_t queued,uint32_t dropped,bool upload_acked) {
    if (!uart_is_driver_installed(UART_NUM_0)) return ESP_ERR_INVALID_STATE;
    char line[200];
    if (!desk_format_cycle_log(line,sizeof line,reading,queued,dropped,upload_acked)) return ESP_ERR_INVALID_SIZE;
    size_t length=strlen(line);
    return uart_write_bytes(UART_NUM_0,line,length)==(int)length ? ESP_OK : ESP_FAIL;
}
void desk_uart_drain(void) {
    fflush(stdout); fflush(stderr);
    if (uart_is_driver_installed(UART_NUM_0)) uart_wait_tx_done(UART_NUM_0,pdMS_TO_TICKS(250));
}
