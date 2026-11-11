# Checks for the desk node's SHT31 checksum hardware and the reading buffer.
#   make lint      Verilator lint of every top module
#   make wires     replay the Scheme scenarios into build/wire/*.wire
#   make test      all simulations (cocotb, Verilator C++ benches, pytest cross-checks)
#   make synth     Yosys synthesis to an iCE40 FPGA-style netlist and a cell report
#   make clean     remove build outputs
REPLAY := ../replay
BUILD := build
PY ?= $(CURDIR)/.venv/bin/python
SCHEME := $(REPLAY)/scheme
WIRES := $(BUILD)/wire/outage.wire $(BUILD)/wire/clean.wire $(BUILD)/wire/corrupt.wire $(BUILD)/wire/mixed-corruption.wire
TOPS := sht31_frame_check crc8_word_stream reading_buffer sensor_path
SRC := src/sht31_crc8_step.v src/crc8_word_stream.v src/sht31_frame_check.sv src/march_bist.v src/reading_buffer.v src/sensor_path.v

.PHONY: lint wires test test-frame test-crc test-dft test-python synth clean

lint:
	@for top in $(TOPS); do \
	  echo "== lint $$top"; \
	  verilator --lint-only -Wall -Wno-DECLFILENAME --top-module $$top $(SRC) || exit 1; \
	done

define WIRE_RULE
$(BUILD)/wire/$(1).wire: $(2) $(REPLAY)/compile.scm
	@mkdir -p $(BUILD)/wire
	GUILE_AUTO_COMPILE=0 guile --no-auto-compile -L $(SCHEME) $(REPLAY)/compile.scm < $$< > $$@
endef
$(eval $(call WIRE_RULE,outage,$(REPLAY)/examples/outage.scm))
$(eval $(call WIRE_RULE,clean,../capture/examples/clean.scm))
$(eval $(call WIRE_RULE,corrupt,../capture/examples/corrupt.scm))
$(eval $(call WIRE_RULE,mixed-corruption,scenarios/mixed-corruption.scm))

wires: $(WIRES)

$(BUILD)/crc_vectors.txt: $(WIRES) scripts/make_vectors.py scripts/sht31_ref.py
	$(PY) scripts/make_vectors.py $(WIRES) --out $@

test-frame: wires
	$(MAKE) -C tests/cocotb WIRE_DIR=$(CURDIR)/$(BUILD)/wire

test-crc: wires $(BUILD)/crc_vectors.txt
	$(MAKE) -C tests/verilator crc

test-dft:
	$(MAKE) -C tests/verilator dft

test-python: test-crc test-dft
	$(PY) -m pytest tests/test_reference.py -q

test: lint test-frame test-python

synth:
	@mkdir -p $(BUILD)
	yosys -q -l $(BUILD)/synth.log synth/synth_ice40.ys
	@python3 scripts/synth_summary.py $(BUILD) | tee $(BUILD)/synth_summary.txt

clean:
	rm -rf $(BUILD) tests/cocotb/sim_build tests/cocotb/results.xml tests/cocotb/__pycache__ tests/verilator/obj_dir
