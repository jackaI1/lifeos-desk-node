# Builds and runs the integer-only C detector against the Python reference vectors.
CC ?= cc
BUILD ?= build
CFLAGS ?= -O2
WARN = -std=c11 -Wall -Wextra -Werror -pedantic

.PHONY: test clean
test: $(BUILD)/test_anomaly_int8
	$(BUILD)/test_anomaly_int8

$(BUILD)/test_anomaly_int8: test_anomaly_int8.c anomaly_int8.c anomaly_int8.h model_params.h test_vectors.h
	mkdir -p $(BUILD)
	$(CC) $(WARN) $(CFLAGS) -I. test_anomaly_int8.c anomaly_int8.c -o $@

clean:
	rm -rf $(BUILD)
