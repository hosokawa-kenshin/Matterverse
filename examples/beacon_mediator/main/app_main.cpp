#include <esp_err.h>
#include <esp_log.h>
#include <nvs_flash.h>

#include <esp_matter.h>
#include <esp_matter_commissioner.h>
#include <esp_matter_console.h>
#include <esp_matter_controller_console.h>
#include <esp_matter_controller_cluster_command.h>
#include <esp_matter_controller_write_command.h>
#include <esp_matter_ota.h>
#include <esp_route_hook.h>

#include <esp_matter_controller_pairing_command.h>
#include <esp_matter_controller_utils.h>

#include <device.h>

#include <app_reset.h>

/*BLE*/
#include "esp_nimble_hci.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "host/ble_hs.h"
#include "host/util/util.h"
#include "console/console.h"
#include "services/gap/ble_svc_gap.h"
#include "esp_ibeacon_api.h"

#include "store/config/ble_store_config.h"

#include "math.h"

#include <is_commissioned.h>

uint64_t pincode = static_cast<uint64_t>(20202021);

/*-----------------------------BLE start-----------------------------*/
static int blecent_gap_event(struct ble_gap_event *event, void *arg);
extern "C" void ble_store_config_init(void);
static const char *tag = "NimBLE_BLE_CENT";

/**
 * Initiates the GAP general discovery procedure.
 */
static void
blecent_scan(void)
{
    uint8_t own_addr_type;
    struct ble_gap_disc_params disc_params;
    int rc;

    /* Figure out address to use while advertising (no privacy for now) */
    rc = ble_hs_id_infer_auto(0, &own_addr_type);
    if (rc != 0)
    {
        MODLOG_DFLT(ERROR, "error determining address type; rc=%d\n", rc);
        return;
    }

    /* Tell the controller to filter duplicates; we don't want to process
     * repeated advertisements from the same device.
     */
    disc_params.filter_duplicates = 1;

    /**
     * Perform a passive scan.  I.e., don't send follow-up scan requests to
     * each advertiser.
     */
    disc_params.passive = 1;

    /* Use defaults for the rest of the parameters. */
    disc_params.itvl = 0;
    disc_params.window = 0;
    disc_params.filter_policy = 0;
    disc_params.limited = 0;

    rc = ble_gap_disc(own_addr_type, BLE_HS_FOREVER, &disc_params,
                      blecent_gap_event, NULL);
    if (rc != 0)
    {
        MODLOG_DFLT(ERROR, "Error initiating GAP discovery procedure; rc=%d\n",
                    rc);
    }
}

static int
blecent_gap_event(struct ble_gap_event *event, void *arg)
{
    struct ble_hs_adv_fields fields;
    int rc;
    esp_ble_ibeacon_t *ibeacon_data;
    uint16_t major, minor;
    int8_t tx_power, rssi;

    switch (event->type)
    {
    case BLE_GAP_EVENT_DISC:
        rc = ble_hs_adv_parse_fields(&fields, event->disc.data,
                                     event->disc.length_data);
        if (rc != 0)
        {
            return 0;
        }
        //*tx_power*//

        ibeacon_data = (esp_ble_ibeacon_t *)(event->disc.data);
        char buf[100];
        sprintf(buf, "%x %x %x %x %x %x %x %x %x %x %x %x %x %x %x %x", ibeacon_data->ibeacon_vendor.proximity_uuid[0], ibeacon_data->ibeacon_vendor.proximity_uuid[1], ibeacon_data->ibeacon_vendor.proximity_uuid[2], ibeacon_data->ibeacon_vendor.proximity_uuid[3], ibeacon_data->ibeacon_vendor.proximity_uuid[4], ibeacon_data->ibeacon_vendor.proximity_uuid[5], ibeacon_data->ibeacon_vendor.proximity_uuid[6], ibeacon_data->ibeacon_vendor.proximity_uuid[7], ibeacon_data->ibeacon_vendor.proximity_uuid[8], ibeacon_data->ibeacon_vendor.proximity_uuid[9], ibeacon_data->ibeacon_vendor.proximity_uuid[10], ibeacon_data->ibeacon_vendor.proximity_uuid[11], ibeacon_data->ibeacon_vendor.proximity_uuid[12], ibeacon_data->ibeacon_vendor.proximity_uuid[13], ibeacon_data->ibeacon_vendor.proximity_uuid[14], ibeacon_data->ibeacon_vendor.proximity_uuid[15]);
        // if(!strcmp(buf,"0 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff")){
        printf("UUID: %s\n", buf);
        major = ENDIAN_CHANGE_U16(ibeacon_data->ibeacon_vendor.major);
        minor = ENDIAN_CHANGE_U16(ibeacon_data->ibeacon_vendor.minor);
        printf("Major: %u\nMinor: %u\n", major, minor);
        //*tx_power*//
        tx_power = ibeacon_data->ibeacon_vendor.measured_power;
        rssi = event->disc.rssi;
        printf("RSSI: %d\nMeasured_Power: %d\n", rssi, tx_power);
        double distance = pow(10.0, (tx_power - rssi) / 20.0) * 25.5;
        uint8_t distance_meter = static_cast<uint8_t>(distance);
        double distance_after = static_cast<double>(distance_meter);
        //   printf("Distance(lf): %lf\nDistance_recv(lf): %lf\n\n",distance/25.5,distance_after/25.5);
        printf("is_commissioned: %d\n", is_commissioned);
        uint16_t msg_i = distance_meter << 8 | static_cast<uint8_t>(minor);
        char msg[10];
        sprintf(msg, "%u", msg_i);
        printf("%s\n", msg);
        uint8_t receive_uuid = msg_i & 0x00FF;
        uint8_t receive_distance = (msg_i & 0xFF00) >> 8;
        printf("%u\n%u\n", receive_uuid, receive_distance);
        /* Write command */
        if (is_commissioned && distance < 10)
        {
            using namespace chip::app::Clusters;
            chip::DeviceLayer::StackLock lock;
            esp_matter::controller::send_write_attr_command(static_cast<uint64_t>(1), static_cast<uint16_t>(1), OnOff::Id, OnOff::Attributes::OffWaitTime::Id, msg);
        }
        // }
        return 0;

    default:
        return 0;
    }
}

static void
blecent_on_reset(int reason)
{
    MODLOG_DFLT(ERROR, "Resetting state; reason=%d\n", reason);
}

static void
blecent_on_sync(void)
{
    int rc;

    /* Make sure we have proper identity address set (public preferred) */
    rc = ble_hs_util_ensure_addr(0);
    assert(rc == 0);
    blecent_scan();
}

void blecent_host_task(void *param)
{
    ESP_LOGI(tag, "BLE Host Task Started");
    /* This function will return only when nimble_port_stop() is executed */
    nimble_port_run();

    nimble_port_freertos_deinit();
}

/*-----------------------------BLE end-----------------------------*/
/*--------------------------Matter start---------------------------*/

static const char *TAG = "app_main";

typedef void *app_driver_handle_t;

using namespace esp_matter;
using namespace esp_matter::attribute;
using namespace esp_matter::endpoint;

static void app_event_cb(const ChipDeviceEvent *event, intptr_t arg)
{
    switch (event->Type)
    {
    case chip::DeviceLayer::DeviceEventType::PublicEventTypes::kInterfaceIpAddressChanged:
        ESP_LOGI(TAG, "Interface IP Address changed");
        break;
    case chip::DeviceLayer::DeviceEventType::kCommissioningComplete:
        ESP_LOGI(TAG, "Commissioning complete");
        blecent_scan();
        break;

    case chip::DeviceLayer::DeviceEventType::kFailSafeTimerExpired:
        ESP_LOGI(TAG, "Commissioning failed, fail safe timer expired");
        break;

    case chip::DeviceLayer::DeviceEventType::kCommissioningSessionStarted:
        ESP_LOGI(TAG, "Commissioning session started");
        break;

    case chip::DeviceLayer::DeviceEventType::kCommissioningSessionStopped:
        ESP_LOGI(TAG, "Commissioning session stopped");
        break;

    case chip::DeviceLayer::DeviceEventType::kCommissioningWindowOpened:
        ESP_LOGI(TAG, "Commissioning window opened");
        break;

    case chip::DeviceLayer::DeviceEventType::kCommissioningWindowClosed:
        ESP_LOGI(TAG, "Commissioning window closed");
        break;

    case chip::DeviceLayer::DeviceEventType::kFabricRemoved:
        ESP_LOGI(TAG, "Fabric removed successfully");
        break;

    case chip::DeviceLayer::DeviceEventType::kFabricWillBeRemoved:
        ESP_LOGI(TAG, "Fabric will be removed");
        break;

    case chip::DeviceLayer::DeviceEventType::kFabricUpdated:
        ESP_LOGI(TAG, "Fabric is updated");
        break;

    case chip::DeviceLayer::DeviceEventType::kFabricCommitted:
        ESP_LOGI(TAG, "Fabric is committed");
        break;

    default:
        break;
    }
}

static void app_driver_button_toggle_cb(void *, void *)
{
    ESP_LOGI(TAG, "Toggle button pressed");
    controller::pairing_on_network(static_cast<uint64_t>(1), pincode);
}

static app_driver_handle_t app_driver_button_init()
{
    /* Initialize button */
    button_config_t config = button_driver_get_config();
    button_handle_t handle = iot_button_create(&config);
    iot_button_register_cb(handle, BUTTON_PRESS_DOWN, app_driver_button_toggle_cb, NULL);
    return (app_driver_handle_t)handle;
}

/*--------------------------Matter end---------------------------*/
extern "C" void app_main()
{
    int rc;
    is_commissioned = 0;
    esp_err_t err = ESP_OK;
    /* Initialize the ESP NVS layer */
    nvs_flash_init();
    ESP_ERROR_CHECK(esp_nimble_hci_and_controller_init());
    nimble_port_init();

    /* Configure the host. */
    ble_hs_cfg.reset_cb = blecent_on_reset;
    ble_hs_cfg.sync_cb = blecent_on_sync;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    /* Set the default device name. */
    rc = ble_svc_gap_device_name_set("nimble-blecent");
    assert(rc == 0);

    /* XXX Need to have template for store */
    ble_store_config_init();
    nimble_port_freertos_init(blecent_host_task);

    app_driver_handle_t button_handle = app_driver_button_init();
    app_reset_button_register(button_handle);

    /* Matter start */
    err = esp_matter::start(app_event_cb);
    if (err != ESP_OK)
    {
        /// ESP_LOGE(TAG, "Matter start failed: %d", err);
    }

    esp_matter::console::diagnostics_register_commands();
    esp_matter::console::wifi_register_commands();
    esp_matter::console::init();

    esp_matter::lock::chip_stack_lock(portMAX_DELAY);
    esp_matter::commissioner::init(5580);
    esp_matter::lock::chip_stack_unlock();

    esp_matter::console::controller_register_commands();
}
