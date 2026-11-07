#include "drivers.hpp"
#include <cstdint>
#ifdef DESK_RTOS
extern "C" {
#include "FreeRTOS.h"
#include "task.h"
}
#endif
static volatile uint32_t &reg(uintptr_t address) {
    return *reinterpret_cast<volatile uint32_t *>(address);
}
class StmUart final : public desk::Uart {
  public:
    StmUart() {
        reg(0x40023840) |= 1U << 17;
        reg(0x4000440c) = 0x2008;
    }
    bool byte(uint8_t value) override {
        for (unsigned i = 0; i < 100000; ++i)
            if (reg(0x40004400) & 0x80U) {
                reg(0x40004404) = value;
                return true;
            }
        return false;
    }
};
class StmI2c final : public desk::I2c {
    desk::Result wait(uint32_t bits) {
        for (unsigned n = 0; n < 100000; ++n) {
            auto sr = reg(0x40005414);
            if (sr & 0x400U)
                return desk::Result::nack;
            if ((sr & bits) == bits)
                return desk::Result::ok;
        }
        return desk::Result::timeout;
    }
    desk::Result start(uint8_t addr) {
        reg(0x40005400) |= 0x100;
        auto r = wait(1);
        if (r != desk::Result::ok)
            return r;
        reg(0x40005410) = addr;
        r = wait(2);
        auto status2 = static_cast<uint32_t>(reg(0x40005418));
        (void)status2;
        return r;
    }

  public:
    StmI2c() {
        reg(0x40023840) |= 1U << 21;
        reg(0x40005404) = 16;
        reg(0x4000541c) = 80;
        reg(0x40005420) = 17;
        reg(0x40005400) = 0x401;
    }
    desk::Result transfer(uint8_t address, const uint8_t *tx, size_t txsize, uint8_t *rx,
                          size_t rxsize) override {
        auto result = start(static_cast<uint8_t>(address << 1));
        for (size_t i = 0; result == desk::Result::ok && i < txsize; ++i) {
            result = wait(0x80);
            if (result == desk::Result::ok)
                reg(0x40005410) = tx[i];
        }
        reg(0x40005400) |= 0x200;
        if (result != desk::Result::ok)
            return result;
        result = start(static_cast<uint8_t>((address << 1) | 1U));
        for (size_t i = 0; result == desk::Result::ok && i < rxsize; ++i) {
            result = wait(0x40);
            if (result == desk::Result::ok)
                rx[i] = static_cast<uint8_t>(reg(0x40005410));
        }
        reg(0x40005400) |= 0x200;
        return result;
    }
};
extern "C" {
void __cxa_pure_virtual() {
    for (;;) {
    }
}
volatile uint32_t hardfault_registers[10];
volatile uint32_t trigger_fault = 0;
void hardfault_record(uint32_t *frame) {
    for (unsigned i = 0; i < 8; ++i)
        hardfault_registers[i] = frame[i];
    hardfault_registers[8] = reg(0xe000ed28);
    hardfault_registers[9] = reg(0xe000ed2c);
    for (;;)
        __asm volatile("nop");
}
__attribute__((naked)) void HardFault_Handler() {
    __asm volatile("tst lr,#4\nite eq\nmrseq r0,msp\nmrsne r0,psp\nb hardfault_record");
}
__attribute__((noinline)) void injected_fault() { __asm volatile("udf #0"); }
#ifndef DESK_RTOS
volatile uint32_t ticks = 0;
void SysTick_Handler() { ++ticks; }
#else
void vApplicationGetIdleTaskMemory(StaticTask_t **tcb, StackType_t **stack, uint32_t *size) {
    static StaticTask_t task;
    static StackType_t memory[configMINIMAL_STACK_SIZE];
    *tcb = &task;
    *stack = memory;
    *size = configMINIMAL_STACK_SIZE;
}
void vApplicationStackOverflowHook(TaskHandle_t, char *) {
    for (;;) {
    }
}
#endif
void firmware_main() {
    /* GDB can request the fault before peripheral setup or timer waits. */
    if (trigger_fault)
        injected_fault();
    StmUart uart;
    desk::Logger log(uart);
    StmI2c i2c;
    desk::Sensor sensor(i2c);
    int32_t temperature = 0;
    uint32_t humidity = 0;
    auto status = sensor.read(temperature, humidity);
    if (status == desk::Result::ok && temperature == 25000 && humidity >= 49999 &&
        humidity <= 50002)
        log.text("SENSOR PASS temperature=25000 humidity=50001\n");
    else if (status == desk::Result::timeout)
        log.text("SENSOR FAIL timeout\n");
    else if (status == desk::Result::nack)
        log.text("SENSOR FAIL nack\n");
    else
        log.text("SENSOR FAIL crc/value\n");
#ifdef DESK_RTOS
    log.text("FREERTOS PASS scheduled sensor task\n");
#else
    reg(0xe000e014) = 72000 - 1;
    reg(0xe000e010) = 7;
    while (ticks < 10)
        __asm volatile("wfi");
    log.text("BAREMETAL PASS timer interrupt\n");
#endif
    while (!trigger_fault) {
#ifdef DESK_RTOS
        vTaskDelay(1);
#else
        __asm volatile("wfi");
#endif
    }
    injected_fault();
}
#ifdef DESK_RTOS
static void sensor_task(void *) {
    firmware_main();
    vTaskDelete(nullptr);
}
void start_main() {
    static StaticTask_t task;
    static StackType_t stack[512];
    xTaskCreateStatic(sensor_task, "sensor", 512, nullptr, 2, stack, &task);
    vTaskStartScheduler();
    for (;;) {
    }
}
#else
void start_main() { firmware_main(); }
#endif
}
