/* Bluetooth Low Energy peripheral on the NimBLE stack. Only the wake window is on the air:
   the node advertises, serves reads and notifications, then the caller goes to deep sleep. */
#include "desk_ble.h"
#include "desk_ess.h"
#include "desk_radio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "host/ble_att.h"
#include "host/ble_gatt.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "nimble/hci_common.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "os/os_mbuf.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "esp_timer.h"
#include <string.h>

#define DESK_BLE_SAMPLE_MS 10000U
#define DESK_BLE_ENVIRONMENTAL_SENSING 0x181AU
#define DESK_BLE_TEMPERATURE 0x2A6EU
#define DESK_BLE_HUMIDITY 0x2A6FU

static const char *TAG = "desk_ble";
static int gap_event(struct ble_gap_event *event, void *arg);
static const char *device_name = "Desk room sensor";
static const ble_uuid16_t environmental_uuid = BLE_UUID16_INIT(DESK_BLE_ENVIRONMENTAL_SENSING);
static portMUX_TYPE value_lock = portMUX_INITIALIZER_UNLOCKED;
static uint8_t own_addr_type;
static volatile bool window_open;
static uint16_t connection = BLE_HS_CONN_HANDLE_NONE;
static uint16_t temperature_handle, humidity_handle, sample_handle;
static uint8_t temperature_bytes[2], humidity_bytes[2], sample_bytes[DESK_BLE_SIZE];

static int read_bytes(const uint8_t *value, size_t length, struct ble_gatt_access_ctxt *ctxt) {
    if (ctxt->op != BLE_GATT_ACCESS_OP_READ_CHR)
        return BLE_ATT_ERR_UNLIKELY;
    uint8_t copy[DESK_BLE_SIZE];
    portENTER_CRITICAL(&value_lock);
    memcpy(copy, value, length);
    portEXIT_CRITICAL(&value_lock);
    return os_mbuf_append(ctxt->om, copy, length) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static int access_temperature(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    (void)conn; (void)attr; (void)arg;
    return read_bytes(temperature_bytes, sizeof temperature_bytes, ctxt);
}

static int access_humidity(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    (void)conn; (void)attr; (void)arg;
    return read_bytes(humidity_bytes, sizeof humidity_bytes, ctxt);
}

static int access_sample(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    (void)conn; (void)attr; (void)arg;
    return read_bytes(sample_bytes, sizeof sample_bytes, ctxt);
}

/* Environmental Sensing (0x181A) temperature and humidity, plus the original custom
   16-byte sample (0xFFF0/0xFFF1) that tools/check_radio.py still decodes. NimBLE adds the
   client configuration descriptor for each notifying characteristic. */
static const struct ble_gatt_svc_def gatt_services[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(DESK_BLE_ENVIRONMENTAL_SENSING),
        .characteristics = (struct ble_gatt_chr_def[]){
            {
                .uuid = BLE_UUID16_DECLARE(DESK_BLE_TEMPERATURE),
                .access_cb = access_temperature,
                .val_handle = &temperature_handle,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
            },
            {
                .uuid = BLE_UUID16_DECLARE(DESK_BLE_HUMIDITY),
                .access_cb = access_humidity,
                .val_handle = &humidity_handle,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
            },
            {0},
        },
    },
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = BLE_UUID16_DECLARE(0xFFF0),
        .characteristics = (struct ble_gatt_chr_def[]){
            {
                .uuid = BLE_UUID16_DECLARE(0xFFF1),
                .access_cb = access_sample,
                .val_handle = &sample_handle,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
            },
            {0},
        },
    },
    {0},
};

static void advertise(void) {
    struct ble_hs_adv_fields fields = {0};
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.uuids16 = &environmental_uuid;
    fields.num_uuids16 = 1;
    fields.uuids16_is_complete = 1;
    fields.name = (const uint8_t *)device_name;
    fields.name_len = (uint8_t)strlen(device_name);
    fields.name_is_complete = 1;
    if (ble_gap_adv_set_fields(&fields) != 0) {
        ESP_LOGW(TAG, "advertising fields rejected");
        return;
    }
    struct ble_gap_adv_params params = {0};
    params.conn_mode = BLE_GAP_CONN_MODE_UND;
    params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    if (ble_gap_adv_start(own_addr_type, NULL, BLE_HS_FOREVER, &params, gap_event, NULL) != 0)
        ESP_LOGW(TAG, "advertising did not start");
}

static int gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0)
            connection = event->connect.conn_handle;
        else if (window_open)
            advertise();
        break;
    case BLE_GAP_EVENT_DISCONNECT:
        connection = BLE_HS_CONN_HANDLE_NONE;
        if (window_open)
            advertise();
        break;
    case BLE_GAP_EVENT_ADV_COMPLETE:
        if (window_open)
            advertise();
        break;
    case BLE_GAP_EVENT_SUBSCRIBE:
        /* A new subscriber gets the current value straight away. */
        if (event->subscribe.cur_notify)
            ble_gatts_chr_updated(event->subscribe.attr_handle);
        break;
    default:
        break;
    }
    return 0;
}

static void on_sync(void) {
    if (ble_hs_id_infer_auto(0, &own_addr_type) != 0) {
        ESP_LOGW(TAG, "no Bluetooth address");
        return;
    }
    advertise();
}

static void on_reset(int reason) {
    ESP_LOGW(TAG, "NimBLE reset, reason=%d", reason);
}

static void host_task(void *param) {
    (void)param;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

static void store_values(const desk_ess_value_t *value) {
    portENTER_CRITICAL(&value_lock);
    desk_ess_encode(value, temperature_bytes, humidity_bytes);
    portEXIT_CRITICAL(&value_lock);
}

static void publish(const desk_reading_t *reading, desk_ess_notify_t *state, uint64_t now_ms) {
    desk_ess_value_t value;
    if (!desk_ess_from_reading(reading, &value)) {
        ESP_LOGW(TAG, "sample outside the service range; not published");
        return;
    }
    store_values(&value);
    if (!desk_ess_should_notify(state, &value, now_ms, DESK_BLE_SAMPLE_MS))
        return;
    desk_ess_mark_notified(state, &value, now_ms);
    if (connection != BLE_HS_CONN_HANDLE_NONE) {
        ble_gatts_chr_updated(temperature_handle);
        ble_gatts_chr_updated(humidity_handle);
    }
}

static uint64_t now_ms(void) {
    return (uint64_t)esp_timer_get_time() / 1000U;
}

esp_err_t desk_ble_window(desk_ble_sampler_t sampler, void *context, const desk_reading_t *first,
                          uint32_t seconds) {
    if (!sampler || !first || seconds == 0)
        return ESP_ERR_INVALID_ARG;
    desk_ess_value_t value;
    if (!desk_ess_from_reading(first, &value))
        return ESP_ERR_INVALID_ARG;
    desk_radio_reading_t legacy = {first->sequence, first->temperature_mc, (uint32_t)first->humidity_mpermil};
    if (!desk_ble_encode(sample_bytes, sizeof sample_bytes, &legacy))
        return ESP_ERR_INVALID_ARG;
    store_values(&value);

    esp_err_t err = nimble_port_init();
    if (err != ESP_OK)
        return err;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.reset_cb = on_reset;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    int rc = ble_gatts_count_cfg(gatt_services);
    if (rc == 0)
        rc = ble_gatts_add_svcs(gatt_services);
    if (rc == 0)
        rc = ble_svc_gap_device_name_set(device_name);
    if (rc != 0) {
        ESP_LOGE(TAG, "GATT table rejected, rc=%d", rc);
        return ESP_FAIL;
    }

    uint64_t start = now_ms();
    uint64_t deadline = start + (uint64_t)seconds * 1000U;
    desk_ess_notify_t notify = {0};
    desk_ess_mark_notified(&notify, &value, start);
    window_open = true;
    nimble_port_freertos_init(host_task);

    while (now_ms() < deadline) {
        uint64_t remaining = deadline - now_ms();
        vTaskDelay(pdMS_TO_TICKS(remaining < DESK_BLE_SAMPLE_MS ? remaining : DESK_BLE_SAMPLE_MS));
        if (now_ms() >= deadline)
            break;
        desk_reading_t reading;
        if (sampler(context, &reading))
            publish(&reading, &notify, now_ms());
        else
            ESP_LOGW(TAG, "sensor sample skipped");
    }

    /* Stop advertising and end any connection. The deep sleep that follows also powers the radio down. */
    window_open = false;
    ble_gap_adv_stop();
    if (connection != BLE_HS_CONN_HANDLE_NONE)
        ble_gap_terminate(connection, BLE_ERR_REM_USER_CONN_TERM);
    return ESP_OK;
}
