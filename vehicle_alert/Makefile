CC ?= cc
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -pedantic -O1 -g
BUILD ?= build
.PHONY: test analyze clean
test: $(BUILD)/test-alert
	cd $(BUILD) && ./test-alert
$(BUILD)/test-alert: alert.c alert.h test_alert.c
	mkdir -p $(BUILD)
	$(CC) $(CFLAGS) alert.c test_alert.c -o $@
analyze:
	./analyze.sh
clean:
	rm -rf $(BUILD)
