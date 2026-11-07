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
	mkdir -p $(BUILD)
	cppcheck --std=c11 --enable=warning,style,performance,portability --error-exitcode=1 --addon=misra --suppress=misra-c2012-8.7 --suppress=misra-c2012-2.5 --inline-suppr --xml --xml-version=2 alert.c 2> $(BUILD)/cppcheck.xml
clean:
	rm -rf $(BUILD)
