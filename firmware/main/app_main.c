#include "desk_core.h"
#include "desk_drivers.h"
#include "desk_network.h"
#include "sdkconfig.h"
#include "esp_log.h"
#include "esp_attr.h"
#include "bootloader_random.h"
#include "esp_mac.h"
#include "esp_random.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "nvs_flash.h"
#include <stdio.h>
#include <string.h>
#include <time.h>

#define RTC_MAGIC 0x4445534bU
static const char *TAG="desk";
static RTC_DATA_ATTR struct {
    uint32_t magic, next_sequence;
    char session[17];
    desk_ring_t ring;
    desk_event_t event;
} retained;
static desk_drivers_t drivers;
static void new_session(void) {
    uint32_t random[2];
    /* Supply hardware entropy while Wi-Fi/ADC are inactive, including cold boot. */
    bootloader_random_enable();
    esp_fill_random(random,sizeof random);
    bootloader_random_disable();
    snprintf(retained.session,sizeof retained.session,"%08lx%08lx",
        (unsigned long)random[0],(unsigned long)random[1]);
}
typedef struct { bool valid; desk_reading_t reading; } sample_result_t;
static void sample_task(void *arg) {
    QueueHandle_t queue=(QueueHandle_t)arg;
    sample_result_t sample={0};
    sample.valid=desk_sensor_read(&drivers,&sample.reading)==ESP_OK;
    time_t now=time(NULL);
    sample.reading.timestamp=now>=1704067200 ? (int64_t)now : 0;
    xQueueSend(queue,&sample,0);
    vTaskDelete(NULL);
}
static void sleep_now(void) {
    /* Also safe on a deadline path where the network task has not cleaned up. */
    esp_wifi_stop();
    desk_drivers_deinit(&drivers);
    ESP_LOGW(TAG,"Sleeping %d s; queued=%lu lost=%lu",CONFIG_DESK_UPDATE_SECONDS,
        (unsigned long)retained.ring.count,(unsigned long)retained.ring.dropped);
    ESP_ERROR_CHECK(esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_DESK_UPDATE_SECONDS*1000000ULL));
    desk_uart_drain();
    esp_deep_sleep_start();
}
void app_main(void) {
    if (desk_uart_init()!=ESP_OK) ESP_LOGE(TAG,"UART0 driver unavailable; using boot console");
    if (esp_reset_reason()!=ESP_RST_DEEPSLEEP || retained.magic!=RTC_MAGIC ||
        !desk_ring_valid(&retained.ring) || retained.next_sequence==0 ||
        !memchr(retained.event.title,0,sizeof retained.event.title) ||
        !memchr(retained.event.when,0,sizeof retained.event.when) ||
        !memchr(retained.event.kind,0,sizeof retained.event.kind)) {
        memset(&retained,0,sizeof retained);
        retained.magic=RTC_MAGIC; retained.next_sequence=1;
        new_session();
        strcpy(retained.event.title,"Waiting for LifeOS");
    }
    /* Sequence wrap gets a fresh session only after the old FIFO drains. */
    if (retained.next_sequence==UINT32_MAX && !retained.ring.count) {
        new_session();
        retained.next_sequence=1;
    }
    esp_err_t nvs=nvs_flash_init();
    if (nvs!=ESP_OK) { ESP_LOGE(TAG,"NVS unavailable; flash erase needed for provisioning"); sleep_now(); }
    if (desk_drivers_init(&drivers)!=ESP_OK) ESP_LOGW(TAG,"One or more peripherals unavailable");
    sample_result_t sample={0};
    QueueHandle_t samples=xQueueCreate(1,sizeof sample);
    if (samples && drivers.sensor && xTaskCreate(sample_task,"sht31",3072,samples,4,NULL)==pdPASS) {
        if (xQueueReceive(samples,&sample,pdMS_TO_TICKS(2000))!=pdTRUE) {
            ESP_LOGE(TAG,"Sensor task deadline reached"); sleep_now();
        }
    }
    if (samples) vQueueDelete(samples);
    if (sample.valid && retained.next_sequence<UINT32_MAX) {
        sample.reading.sequence=retained.next_sequence++;
        desk_ring_push(&retained.ring,sample.reading);
    }
    uint8_t mac[6]; ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA));
    char device[13];
    snprintf(device,sizeof device,"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    desk_network_result_t result={0};
    QueueHandle_t results=xQueueCreate(1,sizeof result);
    desk_network_request_t job={.ring=&retained.ring,.device=device,.session=retained.session,.result_queue=results};
    if (results && xTaskCreate(desk_network_task,"lifeos_api",8192,&job,3,NULL)==pdPASS) {
        if (xQueueReceive(results,&result,pdMS_TO_TICKS(90000))!=pdTRUE) {
            ESP_LOGE(TAG,"Network cycle deadline reached; retaining FIFO"); sleep_now();
        }
    }
    if (results) vQueueDelete(results);
    if (result.event_valid) retained.event=result.event;
    if (result.upload_acked) {
        while (retained.ring.count) {
            uint32_t sequence=desk_ring_at(&retained.ring,0)->sequence;
            desk_ring_pop(&retained.ring,sequence);
        }
    }
    uint8_t frame[DESK_FRAME_SIZE];
    desk_render(frame,&retained.event,sample.valid?&sample.reading:NULL,result.event_valid,retained.ring.dropped);
    if (desk_display_frame(&drivers,frame)!=ESP_OK) ESP_LOGW(TAG,"Display unavailable");
    if (desk_uart_log_cycle(sample.valid?&sample.reading:NULL,retained.ring.count,
                            retained.ring.dropped,result.upload_acked)!=ESP_OK) ESP_LOGW(TAG,"Cycle log unavailable");
    sleep_now();
}
