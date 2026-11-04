CC ?= cc
BUILD ?= build
CFLAGS ?= -O2
WARN = -std=c11 -Wall -Wextra -Werror -pedantic
CORE = ../firmware/components/desk_core
VENDOR = ../firmware/tests/vendor

.PHONY: all test clean
all: $(BUILD)/desk-replay

$(BUILD):
	mkdir -p "$@"

$(BUILD)/cJSON.o: $(VENDOR)/cJSON.c $(VENDOR)/cJSON.h | $(BUILD)
	$(CC) -std=c11 $(CFLAGS) -Wno-deprecated-declarations -c $< -o "$@"

$(BUILD)/desk-replay: replay.c $(CORE)/desk_core.c $(CORE)/include/desk_core.h $(BUILD)/cJSON.o
	$(CC) $(WARN) $(CFLAGS) -I$(CORE)/include -I$(VENDOR) replay.c $(CORE)/desk_core.c $(BUILD)/cJSON.o -lm -o "$@"

test:
	./tests/run.sh

clean:
	rm -rf build
