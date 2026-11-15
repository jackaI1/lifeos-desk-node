# Host tests for the STM32 IMU filter. Nothing here needs the ARM toolchain.
#
#   make test          build with ASan + UBSan, run the C tests and the Python comparison
#   make tables        regenerate src/imu_tables.h and reference/imu_tables.py
#   make traces        regenerate traces/*.csv
#   make clean         remove build/
#
# The ARM build of the HAL port lives in hal/ and is checked by CI (see
# .github/workflows/stm32-imu.yml), which fetches the STM32CubeF4 headers.

CC ?= cc
PY ?= python3
SAN ?= -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer
CFLAGS = -std=c11 -Wall -Wextra -Werror -pedantic -g -O1 $(SAN) -Iinclude -Isrc

.PHONY: test tables traces arm-check clean

# Cortex-M4 build check of the HAL port and the pure C core. The STM32 HAL, device
# and core headers are not in this repository. CI clones them with sparse checkouts
# and passes their paths in, for example:
#   make arm-check HAL_INC=... CMSIS_DEVICE=... CMSIS_CORE=...
ARM_CC ?= arm-none-eabi-gcc
HAL_INC ?=
CMSIS_DEVICE ?=
CMSIS_CORE ?=
ARM_FLAGS = -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -DSTM32F411xE \
            -std=c11 -Wall -Wextra -Werror -Os -ffunction-sections -fdata-sections

test: build/test_core build/imu_replay
	./build/test_core
	IMU_REPLAY=build/imu_replay $(PY) tests/test_reference.py

build:
	mkdir -p build

build/test_core: tests/test_core.c src/imu_core.c include/imu_core.h src/imu_tables.h | build
	$(CC) $(CFLAGS) tests/test_core.c src/imu_core.c -lm -o $@

build/imu_replay: tools/imu_replay.c src/imu_core.c include/imu_core.h src/imu_tables.h | build
	$(CC) $(CFLAGS) tools/imu_replay.c src/imu_core.c -o $@

arm-check: build/arm/imu_mpu6050_hal.o build/arm/imu_core.o
	$(ARM_CC) --version | head -1
	arm-none-eabi-size build/arm/imu_mpu6050_hal.o build/arm/imu_core.o

build/arm/imu_mpu6050_hal.o: hal/imu_mpu6050_hal.c hal/imu_mpu6050_hal.h hal/stm32f4xx_hal_conf.h include/imu_core.h src/imu_tables.h | build/arm
	$(ARM_CC) $(ARM_FLAGS) -Ihal -Iinclude -isystem $(HAL_INC) -isystem $(CMSIS_DEVICE) -isystem $(CMSIS_CORE) -c $< -o $@

build/arm/imu_core.o: src/imu_core.c include/imu_core.h src/imu_tables.h | build/arm
	$(ARM_CC) $(ARM_FLAGS) -Iinclude -Isrc -c $< -o $@

build/arm:
	mkdir -p build/arm

tables:
	$(PY) tools/gen_tables.py

traces:
	$(PY) tools/make_traces.py

clean:
	rm -rf build
