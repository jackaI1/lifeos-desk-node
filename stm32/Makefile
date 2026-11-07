PREFIX ?= arm-none-eabi-
CC = $(PREFIX)gcc
CXX = $(PREFIX)g++
FREERTOS ?= build/FreeRTOS-Kernel-10.6.2
COMMON = -mcpu=cortex-m4 -mthumb -mfloat-abi=softfp -mfpu=fpv4-sp-d16 -g -O0 -ffunction-sections -fdata-sections -Iinclude -Wall -Wextra -Werror
CXXFLAGS = $(COMMON) -std=c++17 -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit
LDFLAGS = -mcpu=cortex-m4 -mthumb -mfloat-abi=softfp -mfpu=fpv4-sp-d16 -Tmemory.ld -nostartfiles -Wl,--gc-sections --specs=nosys.specs
.PHONY: all clean
all: build/bare.elf build/rtos.elf
build:
	mkdir -p build
build/FreeRTOS-Kernel-10.6.2: | build
	curl -fLsS https://github.com/FreeRTOS/FreeRTOS-Kernel/archive/refs/tags/V10.6.2.tar.gz | tar xz -C build
build/drivers.o: src/drivers.cpp include/drivers.hpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/bare-start.o: src/startup.c | build
	$(CC) $(COMMON) -c $< -o $@
build/bare-platform.o: src/platform.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/bare.elf: build/bare-start.o build/bare-platform.o build/drivers.o
	$(CXX) $(LDFLAGS) $^ -o $@
build/rtos.elf: src/startup.c src/platform.cpp build/drivers.o build/FreeRTOS-Kernel-10.6.2
	$(CC) $(COMMON) -DDESK_RTOS -c src/startup.c -o build/rtos-start.o
	$(CXX) $(CXXFLAGS) -DDESK_RTOS -I$(FREERTOS)/include -I$(FREERTOS)/portable/GCC/ARM_CM4F -c src/platform.cpp -o build/rtos-platform.o
	$(CC) $(COMMON) -I$(FREERTOS)/include -I$(FREERTOS)/portable/GCC/ARM_CM4F -c $(FREERTOS)/tasks.c -o build/tasks.o
	$(CC) $(COMMON) -I$(FREERTOS)/include -I$(FREERTOS)/portable/GCC/ARM_CM4F -c $(FREERTOS)/list.c -o build/list.o
	$(CC) $(COMMON) -I$(FREERTOS)/include -I$(FREERTOS)/portable/GCC/ARM_CM4F -c $(FREERTOS)/queue.c -o build/queue.o
	$(CC) $(COMMON) -I$(FREERTOS)/include -I$(FREERTOS)/portable/GCC/ARM_CM4F -c $(FREERTOS)/portable/GCC/ARM_CM4F/port.c -o build/port.o
	$(CXX) $(LDFLAGS) build/rtos-start.o build/rtos-platform.o build/drivers.o build/tasks.o build/list.o build/queue.o build/port.o -o $@
clean:
	rm -rf build
