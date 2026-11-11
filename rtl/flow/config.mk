# OpenROAD flow configuration for the sensor path on the open Nangate45 library.
# The sweep script (flow/run_sweep.sh) passes the clock file, utilization and
# variant name on the make command line. Paths are as seen inside the container,
# where this repository's rtl/ folder is mounted at /work.
export DESIGN_NAME = sensor_path
export PLATFORM = nangate45
export VERILOG_FILES = \
    /work/src/sht31_crc8_step.v \
    /work/src/crc8_word_stream.v \
    /work/src/sht31_frame_check.sv \
    /work/src/march_bist.v \
    /work/src/reading_buffer.v \
    /work/src/sensor_path.v
