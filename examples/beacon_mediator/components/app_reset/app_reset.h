#pragma once

#include <esp_err.h>

/** Register callbacks for Factory reset
 *
 * Register factory reset functionality on a button.
 *
 * @param[in] handle Button handle returned by iot_button_create().
 *
 * @return ESP_OK on success.
 * @return error in case of failure.
 */
esp_err_t app_reset_button_register(void *handle);
