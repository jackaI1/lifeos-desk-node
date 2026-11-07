#include "drivers.hpp"
namespace desk {
uint8_t crc(const uint8_t *data, size_t size) {
    uint8_t value = 0xff;
    for (size_t i = 0; i < size; ++i) {
        value ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            value = static_cast<uint8_t>((value << 1) ^ ((value & 128U) ? 0x31U : 0U));
    }
    return value;
}
Result Sensor::read(int32_t &temperature_mc, uint32_t &humidity_mpermil) {
    const uint8_t command[] = {0x24, 0x00};
    uint8_t raw[6] = {};
    auto result = bus_.transfer(0x44, command, 2, raw, 6);
    if (result != Result::ok)
        return result;
    if (crc(raw, 2) != raw[2] || crc(raw + 3, 2) != raw[5])
        return Result::crc;
    uint32_t t = static_cast<uint32_t>(raw[0]) * 256U + raw[1],
             h = static_cast<uint32_t>(raw[3]) * 256U + raw[4];
    temperature_mc = -45000 + static_cast<int32_t>((175000ULL * t + 32767) / 65535);
    humidity_mpermil = static_cast<uint32_t>((100000ULL * h + 32767) / 65535);
    return Result::ok;
}
bool Logger::text(const char *message, size_t maximum) {
    if (!message || maximum > 256)
        return false;
    size_t size = 0;
    while (size < maximum && message[size])
        ++size;
    if (size == maximum)
        return false;
    for (size_t i = 0; i < size; ++i)
        if (!uart_.byte(static_cast<uint8_t>(message[i])))
            return false;
    return true;
}
} // namespace desk
