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
DSP = third_party/CMSIS-DSP
DSP_SRC = $(DSP)/Source/FilteringFunctions/arm_biquad_cascade_df1_q31.c \
          $(DSP)/Source/FilteringFunctions/arm_biquad_cascade_df1_init_q31.c
CFLAGS = -std=c11 -Wall -Wextra -Werror -pedantic -g -O1 $(SAN) -Iinclude -Isrc -I$(DSP)/Include -I$(DSP)/PrivateInclude

.PHONY: test tables traces arm-check deps clean

# CMSIS-DSP sources (pinned tag, fetched into third_party/, not committed)
deps:
	sh tools/fetch_cmsis_dsp.sh

# Cortex-M4 build check of the HAL port and the pure C core. The STM32 HAL, device
# and core headers are not in this repository. CI clones them with sparse checkouts
# and passes their paths in, for example:
#   make arm-check HAL_INC=... CMSIS_DEVICE=... CMSIS_CORE=...
ARM_CC ?= arm-none-eabi-gcc
HAL_INC ?=
CMSIS_DEVICE ?=
CMSIS_CORE ?=
ARM_FLAGS = -mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -DSTM32F411xE -DARM_MATH_CM4 \
            -std=c11 -Wall -Wextra -Werror -Os -ffunction-sections -fdata-sections

test: deps build/test_core build/imu_replay
	./build/test_core
	IMU_REPLAY=build/imu_replay $(PY) tests/test_reference.py

build:
	mkdir -p build

build/test_core: tests/test_core.c src/imu_core.c include/imu_core.h src/imu_tables.h $(DSP_SRC) | build
	$(CC) $(CFLAGS) tests/test_core.c src/imu_core.c $(DSP_SRC) -lm -o $@

build/imu_replay: tools/imu_replay.c src/imu_core.c include/imu_core.h src/imu_tables.h $(DSP_SRC) | build
	$(CC) $(CFLAGS) tools/imu_replay.c src/imu_core.c $(DSP_SRC) -o $@

arm-check: deps build/arm/imu_mpu6050_hal.o build/arm/imu_core.o build/arm/arm_biquad_cascade_df1_q31.o build/arm/arm_biquad_cascade_df1_init_q31.o
	$(ARM_CC) --version | head -1
	arm-none-eabi-size build/arm/*.o

build/arm/imu_mpu6050_hal.o: hal/imu_mpu6050_hal.c hal/imu_mpu6050_hal.h hal/stm32f4xx_hal_conf.h include/imu_core.h src/imu_tables.h | build/arm
	$(ARM_CC) $(ARM_FLAGS) -Ihal -Iinclude -isystem $(HAL_INC) -isystem $(CMSIS_DEVICE) -isystem $(CMSIS_CORE) -c $< -o $@

build/arm/imu_core.o: src/imu_core.c include/imu_core.h src/imu_tables.h | build/arm
	$(ARM_CC) $(ARM_FLAGS) -Iinclude -Isrc -I$(DSP)/Include -I$(DSP)/PrivateInclude -isystem $(CMSIS_CORE) -c $< -o $@

build/arm/arm_biquad_cascade_df1_%.o: $(DSP)/Source/FilteringFunctions/arm_biquad_cascade_df1_%.c | build/arm
	$(ARM_CC) $(ARM_FLAGS) -I$(DSP)/Include -I$(DSP)/PrivateInclude -isystem $(CMSIS_CORE) -c $< -o $@

build/arm:
	mkdir -p build/arm

tables:
	$(PY) tools/gen_tables.py

traces:
	$(PY) tools/make_traces.py

clean:
	rm -rf build
