#include <esp_log.h>
#include <iot_button.h>
#include <led_driver.h>

#include <esp_log.h>

#define LED_GPIO_PIN GPIO_NUM_27
#define LED_CHANNEL 0 /* LEDC_CHANNEL_0 */
#define BUTTON_GPIO_PIN GPIO_NUM_39

led_driver_config_t led_driver_get_config()
{
    ESP_LOGW("device.c", "led_driver_get_config() called");

    led_driver_config_t config = {
        .gpio = LED_GPIO_PIN,
        .channel = LED_CHANNEL,
    };
    return config;
}

button_config_t button_driver_get_config()
{
    button_config_t config = {
        .type = BUTTON_TYPE_GPIO,
        .gpio_button_config = {
            .gpio_num = BUTTON_GPIO_PIN,
            .active_level = 0,
        }
    };
    return config;
}
