# Builds the Verilator testbenches and runs them. Run from rtl/ with `make test-crc` or `make test-dft`.
VERILATOR ?= verilator
RTL := ../../src
BUILD := ../../build/verilator

crc: $(BUILD)/crc8_word_stream_tb
	$(BUILD)/crc8_word_stream_tb ../../build/crc_vectors.txt | tee ../../build/crc8_word_stream_tb.log | tail -1
	@grep -q '^RESULT words=.* mismatches=0$$' ../../build/crc8_word_stream_tb.log

dft: $(BUILD)/dft_tb
	$(BUILD)/dft_tb | tee ../../build/dft_report.txt

$(BUILD)/crc8_word_stream_tb: $(RTL)/crc8_word_stream.v $(RTL)/sht31_crc8_step.v crc8_word_stream_tb.cpp
	@mkdir -p $(BUILD)
	$(VERILATOR) --cc --exe --build -Wall -Wno-DECLFILENAME --top-module crc8_word_stream \
	  --Mdir $(BUILD)/crc --prefix Vcrc8_word_stream -o $(CURDIR)/$@ \
	  $(RTL)/crc8_word_stream.v $(RTL)/sht31_crc8_step.v crc8_word_stream_tb.cpp > $(BUILD)/crc-build.log 2>&1 || (tail -40 $(BUILD)/crc-build.log; exit 1)

$(BUILD)/dft_tb: $(RTL)/reading_buffer.v $(RTL)/march_bist.v $(RTL)/sht31_crc8_step.v dft_tb.cpp
	@mkdir -p $(BUILD)
	$(VERILATOR) --cc --exe --build -Wall -Wno-DECLFILENAME --top-module reading_buffer \
	  --Mdir $(BUILD)/dft --prefix Vreading_buffer -o $(CURDIR)/$@ \
	  $(RTL)/reading_buffer.v $(RTL)/march_bist.v dft_tb.cpp > $(BUILD)/dft-build.log 2>&1 || (tail -40 $(BUILD)/dft-build.log; exit 1)

board: $(BUILD)/board_tb
	$(BUILD)/board_tb | tee ../../build/board_tb.log | tail -1
	@grep -q '^RESULT transfers=[0-9]* failures=0$$' ../../build/board_tb.log

$(BUILD)/board_tb: $(RTL)/uart_rx.v $(RTL)/uart_tx.v $(RTL)/sensor_path.v $(RTL)/sht31_frame_check.sv \
  $(RTL)/sht31_crc8_step.v $(RTL)/reading_buffer.v $(RTL)/march_bist.v \
  ../../board/icebreaker/desk_board_top.v board_tb.cpp
	@mkdir -p $(BUILD)
	$(VERILATOR) --cc --exe --build -Wall -Wno-DECLFILENAME -Wno-UNUSED -Wno-fatal --top-module desk_board_top \
	  --Mdir $(BUILD)/board --prefix Vdesk_board_top -o $(CURDIR)/$@ \
	  $(RTL)/uart_rx.v $(RTL)/uart_tx.v $(RTL)/sensor_path.v $(RTL)/sht31_frame_check.sv \
	  $(RTL)/sht31_crc8_step.v $(RTL)/reading_buffer.v $(RTL)/march_bist.v \
	  ../../board/icebreaker/desk_board_top.v board_tb.cpp > $(BUILD)/board-build.log 2>&1 || (tail -40 $(BUILD)/board-build.log; exit 1)

.PHONY: crc dft board
