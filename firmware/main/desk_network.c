#include "desk_network.h"
#include "sdkconfig.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_sntp.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "freertos/event_groups.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define CONNECTED BIT0
#define FAILED BIT1
static const char *TAG="desk_net";
typedef struct { EventGroupHandle_t events; unsigned attempts; } wifi_wait_t;
static void wifi_event(void *arg,esp_event_base_t base,int32_t id,void *data) {
    (void)data;
    wifi_wait_t *wait=arg;
    if (base==IP_EVENT && id==IP_EVENT_STA_GOT_IP) xEventGroupSetBits(wait->events,CONNECTED);
    else if (base==WIFI_EVENT && (id==WIFI_EVENT_STA_START || id==WIFI_EVENT_STA_DISCONNECTED)) {
        if (wait->attempts++<3) esp_wifi_connect();
        else xEventGroupSetBits(wait->events,FAILED);
    }
}
static esp_err_t response_event(esp_http_client_event_t *event) {
    if (event->event_id==HTTP_EVENT_ON_DATA && event->data_len>0) {
        desk_body_t *body=event->user_data;
        if (!desk_body_append(body,event->data,(size_t)event->data_len)) return ESP_FAIL;
    }
    return ESP_OK;
}
static bool request(const char *path,const char *payload,char *response,size_t capacity) {
    char url[256], auth[160];
    int n=snprintf(url,sizeof url,"%s%s",CONFIG_DESK_API_URL,path);
    if (n<0 || (size_t)n>=sizeof url) return false;
    n=snprintf(auth,sizeof auth,"Bearer %s",CONFIG_DESK_API_TOKEN);
    if (n<0 || (size_t)n>=sizeof auth) return false;
    desk_body_t body; desk_body_init(&body,response,capacity);
    esp_http_client_config_t config={.url=url,.timeout_ms=5000,.event_handler=response_event,
        .user_data=&body,.crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,
        .buffer_size=1024,.buffer_size_tx=1024};
    esp_http_client_handle_t client=esp_http_client_init(&config);
    if (!client) return false;
    esp_err_t err=esp_http_client_set_header(client,"Authorization",auth);
    if (err==ESP_OK) err=esp_http_client_set_header(client,"Accept","application/json");
    if (payload && err==ESP_OK) {
        err=esp_http_client_set_method(client,HTTP_METHOD_POST);
        if (err==ESP_OK) err=esp_http_client_set_header(client,"Content-Type","application/json");
        if (err==ESP_OK) err=esp_http_client_set_post_field(client,payload,(int)strlen(payload));
    }
    if (err==ESP_OK) err=esp_http_client_perform(client);
    bool ok=err==ESP_OK && !body.overflow && esp_http_client_get_status_code(client)==200 &&
        esp_http_client_is_complete_data_received(client);
    esp_http_client_cleanup(client);
    return ok;
}
static bool configuration_valid(void) {
    size_t ssid=strlen(CONFIG_DESK_WIFI_SSID), password=strlen(CONFIG_DESK_WIFI_PASSWORD);
    size_t token=strlen(CONFIG_DESK_API_TOKEN), url=strlen(CONFIG_DESK_API_URL);
    if (!ssid || ssid>32 || password>63 || token<32 || token>128 || !url || url>230 ||
        strchr(CONFIG_DESK_API_TOKEN,'\r') || strchr(CONFIG_DESK_API_TOKEN,'\n') ||
        strchr(CONFIG_DESK_API_URL,'?') || strchr(CONFIG_DESK_API_URL,'#') ||
        strchr(CONFIG_DESK_API_URL,'@') || CONFIG_DESK_API_URL[url-1]=='/') return false;
    if (!strncmp(CONFIG_DESK_API_URL,"https://",8)) return true;
#ifdef CONFIG_DESK_ALLOW_HTTP
    if (!strncmp(CONFIG_DESK_API_URL,"http://",7)) return true;
#endif
    return false;
}
void desk_network_task(void *argument) {
    const desk_network_request_t *job=argument;
    desk_network_result_t result={0};
    wifi_wait_t wait={0};
    esp_event_handler_instance_t wifi_handler=NULL, ip_handler=NULL;
    esp_netif_t *netif=NULL;
    bool wifi_initialized=false, wifi_started=false, sntp_started=false;
    char *response=NULL,*payload=NULL;
    if (!configuration_valid()) { ESP_LOGW(TAG,"Configure Wi-Fi and desk API in menuconfig"); goto done; }
    wait.events=xEventGroupCreate(); if (!wait.events) goto done;
    if (esp_netif_init()!=ESP_OK || esp_event_loop_create_default()!=ESP_OK) goto done;
    netif=esp_netif_create_default_wifi_sta(); if (!netif) goto done;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init)!=ESP_OK) goto done;
    wifi_initialized=true;
    if (esp_wifi_set_storage(WIFI_STORAGE_RAM)!=ESP_OK) goto done;
    if (esp_event_handler_instance_register(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_event,&wait,&wifi_handler)!=ESP_OK) goto done;
    if (esp_event_handler_instance_register(IP_EVENT,IP_EVENT_STA_GOT_IP,wifi_event,&wait,&ip_handler)!=ESP_OK) goto done;
    wifi_config_t wifi={0};
    memcpy(wifi.sta.ssid,CONFIG_DESK_WIFI_SSID,strlen(CONFIG_DESK_WIFI_SSID));
    memcpy(wifi.sta.password,CONFIG_DESK_WIFI_PASSWORD,strlen(CONFIG_DESK_WIFI_PASSWORD));
    wifi.sta.pmf_cfg.capable=true;
    if (esp_wifi_set_mode(WIFI_MODE_STA)!=ESP_OK || esp_wifi_set_config(WIFI_IF_STA,&wifi)!=ESP_OK) goto done;
    if (esp_wifi_start()!=ESP_OK) goto done;
    wifi_started=true;
    EventBits_t bits=xEventGroupWaitBits(wait.events,CONNECTED|FAILED,pdFALSE,pdFALSE,
        pdMS_TO_TICKS(CONFIG_DESK_WIFI_TIMEOUT_SECONDS*1000));
    if (!(bits&CONNECTED)) { ESP_LOGW(TAG,"Wi-Fi deadline reached; retaining offline readings"); goto done; }
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0,CONFIG_DESK_SNTP_SERVER);
    esp_sntp_init(); sntp_started=true;
    for (unsigned i=0;i<50 && time(NULL)<1704067200;i++) vTaskDelay(pdMS_TO_TICKS(100));
    response=malloc(2048); payload=malloc(DESK_PAYLOAD_SIZE);
    if (!response || !payload) goto done;
    /* With an unset RTC, TLS certificate checks fail closed. HTTP demo can run without UTC. */
    if (request("/v1/next",NULL,response,2048)) result.event_valid=desk_parse_event(response,&result.event);
    if (job->ring->count && desk_encode_readings(payload,DESK_PAYLOAD_SIZE,job->device,job->session,job->ring) &&
        request("/v1/readings",payload,response,2048)) {
        const desk_reading_t *last=desk_ring_at(job->ring,job->ring->count-1);
        result.upload_acked=desk_ack_matches(response,job->ring->count,last->sequence);
    }
done:
    free(response); free(payload);
    if (sntp_started) esp_sntp_stop();
    /* Unregister before stopping, so disconnect events cannot reconnect during shutdown. */
    if (wifi_handler) esp_event_handler_instance_unregister(WIFI_EVENT,ESP_EVENT_ANY_ID,wifi_handler);
    if (ip_handler) esp_event_handler_instance_unregister(IP_EVENT,IP_EVENT_STA_GOT_IP,ip_handler);
    if (wifi_started) esp_wifi_stop();
    if (wifi_initialized) esp_wifi_deinit();
    if (netif) esp_netif_destroy_default_wifi(netif);
    if (wait.events) vEventGroupDelete(wait.events);
    xQueueSend(job->result_queue,&result,0);
    vTaskDelete(NULL);
}
