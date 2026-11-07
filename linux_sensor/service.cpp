#include "desk_sensor.h"
#include <array>
#include <cerrno>
#include <csignal>
#include <chrono>
#include <fstream>
#include <thread>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <stdexcept>
#include <sys/ioctl.h>
#include <unistd.h>
class Device {
    int fd_;

  public:
    explicit Device(const char *path) : fd_(open(path, O_RDWR | O_CLOEXEC)) {
        if (fd_ < 0)
            throw std::runtime_error("open sensor failed");
    }
    ~Device() { close(fd_); }
    Device(const Device &) = delete;
    desk_registers get() {
        desk_registers data{};
        if (ioctl(fd_, DESK_GET, &data))
            throw std::runtime_error("GET failed");
        return data;
    }
    void inject(const desk_registers &data) {
        if (ioctl(fd_, DESK_INJECT, &data))
            throw std::runtime_error("INJECT failed");
    }
    void clear() {
        if (ioctl(fd_, DESK_CLEAR))
            throw std::runtime_error("CLEAR failed");
    }
    void test() {
        auto good = get();
        if (good.alarm)
            throw std::runtime_error("bad initial sample");
        desk_registers from_read{};
        if (read(fd_, &from_read, sizeof from_read) != sizeof from_read ||
            memcmp(from_read.raw, good.raw, 6))
            throw std::runtime_error("read/ioctl disagree");
        auto bad = good;
        bad.raw[2] ^= 1;
        inject(bad);
        if (!get().alarm)
            throw std::runtime_error("bad CRC not alarmed");
        inject(good);
        if (!get().alarm)
            throw std::runtime_error("alarm not held");
        clear();
        if (get().alarm)
            throw std::runtime_error("alarm did not clear");
        if (ioctl(fd_, _IO('D', 99)) != -1 || errno != ENOTTY)
            throw std::runtime_error("unknown ioctl accepted");
        std::cout << "PASS: I2C, read/ioctl, checksum fault, held alarm, clear and invalid ioctl"
                  << std::endl;
    }
};
static volatile std::sig_atomic_t running = 1;
static void stop(int) { running = 0; }
static void report(const desk_registers &sample) {
    if (sample.alarm) {
        std::cout << "{\"alarm\":true,\"temperature_mc\":null,\"humidity_mpermil\":null}"
                  << std::endl;
        return;
    }
    unsigned raw_t = unsigned(sample.raw[0]) * 256U + sample.raw[1],
             raw_h = unsigned(sample.raw[3]) * 256U + sample.raw[4];
    int t = -45000 + static_cast<int>((175000ULL * raw_t + 32767) / 65535);
    unsigned h = static_cast<unsigned>((100000ULL * raw_h + 32767) / 65535);
    std::cout << "{\"alarm\":false,\"temperature_mc\":" << t << ",\"humidity_mpermil\":" << h << "}"
              << std::endl;
}
static int hex(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return -1;
}
int main(int argc, char **argv) {
    try {
        Device device(argc > 1 ? argv[1] : "/dev/desk-sensor");
        if (argc > 2 && !strcmp(argv[2], "--self-test")) {
            device.test();
            return 0;
        }
        if (argc > 2 && !strcmp(argv[2], "--clear")) {
            device.clear();
            report(device.get());
            return 0;
        }
        if (argc > 2 && !strcmp(argv[2], "--replay")) {
            if (argc != 4)
                throw std::runtime_error("--replay needs a wire file");
            std::ifstream input(argv[3]);
            char line[80];
            if (!input.getline(line, sizeof line) || strcmp(line, "DESK_REPLAY_V1"))
                throw std::runtime_error("invalid replay header");
            unsigned commands = 0;
            while (input.getline(line, sizeof line)) {
                if (++commands > 4096)
                    throw std::runtime_error("too many replay commands");
                if (!strcmp(line, "U"))
                    continue;
                if (strlen(line) != 14 || line[0] != 'S' || line[1] != ' ')
                    throw std::runtime_error("invalid sensor replay line");
                desk_registers sample{};
                for (unsigned i = 0; i < 6; ++i) {
                    int hi = hex(line[2 + i * 2]), lo = hex(line[3 + i * 2]);
                    if (hi < 0 || lo < 0)
                        throw std::runtime_error("bad hex sensor byte");
                    sample.raw[i] = static_cast<unsigned char>(hi * 16 + lo);
                }
                device.inject(sample);
                report(device.get());
            }
            if (!input.eof())
                throw std::runtime_error("overlong replay line or read failure");
            return 0;
        }
        if (argc > 2 && strcmp(argv[2], "--watch"))
            throw std::runtime_error("unknown mode");
        std::signal(SIGTERM, stop);
        std::signal(SIGINT, stop);
        do {
            report(device.get());
            if (argc <= 2)
                break;
            std::this_thread::sleep_for(std::chrono::seconds(1));
        } while (running);
        return 0;
    } catch (const std::exception &e) {
        std::cerr << e.what() << std::endl;
        return 1;
    }
}
