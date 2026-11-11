// Sensor path: SHT31 frame check, then the reading buffer.
//
// Bytes come in from the sensor link. A good frame's temperature and humidity
// words are stored in the buffer. A bad or truncated frame is counted and dropped.
module sensor_path (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        in_valid,
    input  wire [7:0]  in_data,
    input  wire        in_last,
    output wire        frame_valid,
    output wire        frame_good,
    output wire        frame_bad,
    output wire        frame_truncated,
    output wire [15:0] good_count,
    output wire [15:0] bad_count,
    output wire [15:0] truncated_count,
    output wire [15:0] bad_temp_count,
    output wire [15:0] bad_hum_count,
    input  wire        pop,
    output wire [31:0] head_data,
    output wire        buffer_empty,
    output wire        buffer_full,
    output wire        buffer_overflow,
    input  wire        scan_en,
    input  wire        scan_in,
    output wire        scan_out,
    input  wire        bist_start,
    output wire        bist_busy,
    output wire        bist_done,
    output wire        bist_fail,
    output wire [2:0]  bist_fail_addr,
    input  wire        mem_fault_en,
    input  wire [2:0]  mem_fault_addr,
    input  wire [4:0]  mem_fault_bit,
    input  wire        mem_fault_value,
    input  wire        scan_fault_en,
    input  wire [3:0]  scan_fault_bit,
    input  wire        scan_fault_value
);
    wire [15:0] temp_raw, hum_raw;

    sht31_frame_check u_check (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_data(in_data), .in_last(in_last),
        .frame_valid(frame_valid), .frame_good(frame_good), .frame_bad(frame_bad),
        .frame_truncated(frame_truncated), .temp_raw(temp_raw), .hum_raw(hum_raw),
        .good_count(good_count), .bad_count(bad_count), .truncated_count(truncated_count),
        .bad_temp_count(bad_temp_count), .bad_hum_count(bad_hum_count));

    reading_buffer #(.AW(3), .WIDTH(32)) u_buffer (
        .clk(clk), .rst_n(rst_n),
        .push(frame_good), .push_data({temp_raw, hum_raw}),
        .pop(pop), .head_data(head_data), .empty(buffer_empty), .full(buffer_full),
        .overflow(buffer_overflow),
        .scan_en(scan_en), .scan_in(scan_in), .scan_out(scan_out),
        .bist_start(bist_start), .bist_busy(bist_busy), .bist_done(bist_done),
        .bist_fail(bist_fail), .bist_fail_addr(bist_fail_addr),
        .mem_fault_en(mem_fault_en), .mem_fault_addr(mem_fault_addr),
        .mem_fault_bit(mem_fault_bit), .mem_fault_value(mem_fault_value),
        .scan_fault_en(scan_fault_en), .scan_fault_bit(scan_fault_bit),
        .scan_fault_value(scan_fault_value));
endmodule
