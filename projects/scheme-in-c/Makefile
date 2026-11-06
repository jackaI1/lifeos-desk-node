CC = cc
CPPFLAGS = -Isrc
CFLAGS = -std=c11 -O2 -g -Wall -Wextra -Wpedantic -Werror
SOURCES = src/main.c src/runtime.c src/reader.c src/eval.c src/primitives.c
HEADERS = src/scheme.h
# Apple clang does not ship LeakSanitizer; Linux CI enables it.
LEAKS = $(if $(filter Darwin,$(shell uname -s)),0,1)

.PHONY: all test sanitize clean
all: build/scheme
build:
	mkdir -p build
build/scheme: $(SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SOURCES) -o $@
build/scheme-sanitize: $(SOURCES) $(HEADERS) | build
	$(CC) $(CPPFLAGS) $(CFLAGS) -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all $(SOURCES) -o $@
build/controller-driver: tests/thermostat.c tests/thermostat.h tests/controller_driver.c | build
	$(CC) $(CFLAGS) tests/thermostat.c tests/controller_driver.c -o $@
build/controller-driver-sanitize: tests/thermostat.c tests/thermostat.h tests/controller_driver.c | build
	$(CC) $(CFLAGS) -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=all tests/thermostat.c tests/controller_driver.c -o $@
test: build/scheme build/controller-driver
	python3 tests/run.py build/scheme
	python3 tests/test_controller.py build/controller-driver
sanitize: build/scheme-sanitize build/controller-driver-sanitize
	ASAN_OPTIONS=detect_leaks=$(LEAKS) UBSAN_OPTIONS=halt_on_error=1 python3 tests/run.py build/scheme-sanitize
	ASAN_OPTIONS=detect_leaks=$(LEAKS) UBSAN_OPTIONS=halt_on_error=1 python3 tests/test_controller.py build/controller-driver-sanitize
clean:
	rm -rf build
