/* One immutable sample per wake cycle. No personal event/calendar data in BLE. */
#include "desk_ble.h"
#include "desk_radio.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"
#include "esp_gatts_api.h"
#include "esp_timer.h"
#include <string.h>
static uint8_t payload[DESK_BLE_SIZE];
static uint16_t service_handle, value_handle;
static uint64_t last_notify;
static bool notified;
static esp_ble_adv_params_t advertising={.adv_int_min=0x40,.adv_int_max=0x80,
    .adv_type=ADV_TYPE_IND,.own_addr_type=BLE_ADDR_TYPE_PUBLIC,.channel_map=ADV_CHNL_ALL,
    .adv_filter_policy=ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY};
static void gap(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *param) {
    (void)param;
    if (event==ESP_GAP_BLE_ADV_DATA_SET_COMPLETE_EVT) esp_ble_gap_start_advertising(&advertising);
}
static void gatt(esp_gatts_cb_event_t event, esp_gatt_if_t interface, esp_ble_gatts_cb_param_t *p) {
    if (event==ESP_GATTS_REG_EVT && p->reg.status==ESP_GATT_OK) {
        esp_gatt_srvc_id_t service={.is_primary=true,.id={.inst_id=0,.uuid={.len=ESP_UUID_LEN_16,.uuid={.uuid16=0xfff0}}}};
        esp_ble_gap_set_device_name("Desk room sensor");
        esp_ble_gatts_create_service(interface,&service,4);
    } else if (event==ESP_GATTS_CREATE_EVT && p->create.status==ESP_GATT_OK) {
        service_handle=p->create.service_handle;
        esp_bt_uuid_t uuid={.len=ESP_UUID_LEN_16,.uuid={.uuid16=0xfff1}};
        esp_attr_value_t value={.attr_max_len=DESK_BLE_SIZE,.attr_len=DESK_BLE_SIZE,.attr_value=payload};
        esp_attr_control_t control={.auto_rsp=ESP_GATT_AUTO_RSP};
        esp_ble_gatts_add_char(service_handle,&uuid,ESP_GATT_PERM_READ,
            ESP_GATT_CHAR_PROP_BIT_READ|ESP_GATT_CHAR_PROP_BIT_NOTIFY,&value,&control);
    } else if (event==ESP_GATTS_ADD_CHAR_EVT && p->add_char.status==ESP_GATT_OK) {
        value_handle=p->add_char.attr_handle;
        esp_bt_uuid_t uuid={.len=ESP_UUID_LEN_16,.uuid={.uuid16=ESP_GATT_UUID_CHAR_CLIENT_CONFIG}};
        esp_ble_gatts_add_char_descr(service_handle,&uuid,ESP_GATT_PERM_READ|ESP_GATT_PERM_WRITE,NULL,NULL);
        esp_ble_gatts_start_service(service_handle);
        esp_ble_adv_data_t data={.set_scan_rsp=false,.include_name=true,.flag=ESP_BLE_ADV_FLAG_GEN_DISC|ESP_BLE_ADV_FLAG_BREDR_NOT_SPT};
        esp_ble_gap_config_adv_data(&data);
    } else if (event==ESP_GATTS_WRITE_EVT) {
        bool subscribe=p->write.handle==value_handle+1 && !p->write.is_prep && p->write.len==2 && p->write.value[0]==1 && p->write.value[1]==0;
        if (p->write.need_rsp) esp_ble_gatts_send_response(interface,p->write.conn_id,p->write.trans_id,
            subscribe || (p->write.len==2 && p->write.value[0]==0 && p->write.value[1]==0) ? ESP_GATT_OK : ESP_GATT_INVALID_ATTR_LEN,NULL);
        if (subscribe && desk_notify_due((uint64_t)esp_timer_get_time()/1000,&last_notify,&notified)) {
            esp_ble_gatts_send_indicate(interface,p->write.conn_id,value_handle,DESK_BLE_SIZE,payload,false);
        }
    } else if (event==ESP_GATTS_DISCONNECT_EVT) {
        esp_ble_gap_start_advertising(&advertising);
    }
}
esp_err_t desk_ble_start(const desk_reading_t *sample) {
    if (!sample) return ESP_ERR_INVALID_ARG;
    desk_radio_reading_t reading={sample->sequence,sample->temperature_mc,(uint32_t)sample->humidity_mpermil};
    if (!desk_ble_encode(payload,sizeof payload,&reading)) return ESP_ERR_INVALID_ARG;
    esp_bt_controller_config_t config=BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    esp_err_t err=esp_bt_controller_init(&config);
    if (err==ESP_OK) err=esp_bt_controller_enable(ESP_BT_MODE_BLE);
    if (err==ESP_OK) err=esp_bluedroid_init();
    if (err==ESP_OK) err=esp_bluedroid_enable();
    if (err==ESP_OK) err=esp_ble_gap_register_callback(gap);
    if (err==ESP_OK) err=esp_ble_gatts_register_callback(gatt);
    if (err==ESP_OK) err=esp_ble_gatts_app_register(0x42);
    return err;
}
