CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -pedantic -O1 -g -fsanitize=address,undefined
.PHONY: all test clean
all: build/desk-switch
build:
	mkdir -p build
build/desk-switch: daemon.c switch.c switch.h | build
	$(CC) $(CFLAGS) daemon.c switch.c -o $@
build/test-switch: test_switch.c switch.c switch.h | build
	$(CC) $(CFLAGS) test_switch.c switch.c -o $@
test: all build/test-switch
	build/test-switch
clean:
	rm -rf build
