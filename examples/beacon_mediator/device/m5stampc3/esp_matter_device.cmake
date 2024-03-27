cmake_minimum_required(VERSION 3.5)
if (NOT ("${IDF_TARGET}" STREQUAL "esp32c3" ))
    message(FATAL_ERROR "please set esp32c3 as the IDF_TARGET using 'idf.py set-target esp32c3'")
endif()

SET(device_type     $ENV{ESP_MATTER_DEVICE_PATH})
SET(led_type        ws2812)
SET(button_type     iot)

SET(extra_components_dirs_append    "$ENV{ESP_MATTER_PATH}/device_hal/led_driver"
                                    "$ENV{ESP_MATTER_PATH}/device_hal/button_driver/iot_button")
