# cocotb testbench for the SHT31 frame checker, run under Verilator.
# Run `make -C rtl wires` first so the replayed scenarios exist.
SIM ?= verilator
TOPLEVEL_LANG := verilog
RTL := $(abspath ../../src)
VERILOG_SOURCES := $(RTL)/sht31_crc8_step.v $(RTL)/sht31_frame_check.sv
TOPLEVEL := sht31_frame_check
MODULE := test_frame_check
export PYTHONPATH := $(abspath ../../scripts):$(PYTHONPATH)
EXTRA_ARGS += --assert
export WIRE_DIR ?= $(abspath ../../build/wire)

include $(shell cocotb-config --makefiles)/Makefile.sim
