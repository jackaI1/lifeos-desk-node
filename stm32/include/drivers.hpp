#pragma once
#include <cstddef>
#include <cstdint>
namespace desk {
enum class Result { ok, nack, timeout, crc };
class I2c {
  public:
    virtual Result transfer(uint8_t address, const uint8_t *tx, size_t txsize, uint8_t *rx,
                            size_t rxsize) = 0;

  protected:
    ~I2c() = default;
};
class Uart {
  public:
    virtual bool byte(uint8_t value) = 0;

  protected:
    ~Uart() = default;
};
uint8_t crc(const uint8_t *data, size_t size);
class Sensor {
    I2c &bus_;

  public:
    explicit Sensor(I2c &bus) : bus_(bus) {}
    Result read(int32_t &temperature_mc, uint32_t &humidity_mpermil);
};
class Logger {
    Uart &uart_;

  public:
    explicit Logger(Uart &uart) : uart_(uart) {}
    bool text(const char *message, size_t maximum = 96);
};
} // namespace desk
