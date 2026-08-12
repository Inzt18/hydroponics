#pragma once

#include <Arduino.h>

class PumpControl {
 public:
  void begin(int relay_pin, uint32_t cooldown_ms);
  bool canRun() const;
  void runDose(uint16_t dose_ms);
  void update();  // call from loop()
  bool isRunning() const { return _running; }

 private:
  int _pin = -1;
  uint32_t _cooldown_ms = 0;
  uint32_t _last_run_ms = 0;
  uint32_t _stop_at_ms = 0;
  bool _running = false;
};
