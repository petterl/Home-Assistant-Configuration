#pragma once

// Patched to use the public uart::UARTComponent API instead of inheriting the
// internal IDFUARTComponent / ESP8266UartComponent classes.
//
// The wrapper only ever delegated to the wrapped UART reference (never used any
// inherited member), so inheriting the platform-specific component only made the
// build fragile: those headers (uart_component_esp_idf.h / _esp8266.h) and their
// class layouts are ESPHome internals that change between releases. Everything we
// need — set_baud_rate(), load_settings(), available(), read_array() — is part of
// the public uart::UARTComponent interface and works on every platform.
//
// Original: https://github.com/aquaticus/esphome-iec62056

#include "esphome/components/uart/uart.h"
#include "esphome/core/hal.h"  // millis(), yield()

namespace esphome {
namespace iec62056 {

static const uint32_t TIMEOUT = 20;  // default value in uart implementation is 100ms

class IEC62056UART final {
 public:
  explicit IEC62056UART(uart::UARTComponent &uart) : uart_(uart) {}

  // Dynamically reconfigure the baud rate using the public UART API.
  void update_baudrate(uint32_t baudrate) {
    this->uart_.set_baud_rate(baudrate);
    this->uart_.load_settings(false);
  }

  bool read_one_byte(uint8_t *data) {
    if (!this->check_read_timeout_quick_(1))
      return false;
    return this->uart_.read_array(data, 1);
  }

 protected:
  bool check_read_timeout_quick_(size_t len) {
    if (uart_.available() >= int(len))
      return true;

    uint32_t start_time = millis();
    while (uart_.available() < int(len)) {
      if (millis() - start_time > TIMEOUT) {
        return false;
      }
      yield();
    }
    return true;
  }

  uart::UARTComponent &uart_;
};

}  // namespace iec62056
}  // namespace esphome
