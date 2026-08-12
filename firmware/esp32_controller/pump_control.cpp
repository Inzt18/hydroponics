#include "pump_control.h"

void PumpControl::begin(int relay_pin, uint32_t cooldown_ms) {
  _pin = relay_pin;
  _cooldown_ms = cooldown_ms;
  pinMode(_pin, OUTPUT);
  digitalWrite(_pin, LOW);
  _running = false;
  _last_run_ms = 0;
}

bool PumpControl::canRun() const {
  if (_running) return false;
  if (_last_run_ms == 0) return true;
  return (millis() - _last_run_ms) >= _cooldown_ms;
}

void PumpControl::runDose(uint16_t dose_ms) {
  if (dose_ms == 0 || _pin < 0) return;
  if (!canRun()) {
    Serial.println("[PUMP] cooldown active — skip");
    return;
  }
  digitalWrite(_pin, HIGH);
  _running = true;
  _stop_at_ms = millis() + dose_ms;
  _last_run_ms = millis();
  Serial.printf("[PUMP] ON for %u ms\n", dose_ms);
}

void PumpControl::update() {
  if (!_running) return;
  if ((int32_t)(millis() - _stop_at_ms) >= 0) {
    digitalWrite(_pin, LOW);
    _running = false;
    Serial.println("[PUMP] OFF");
  }
}
