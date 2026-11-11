// Checks SHT31 sensor frames as their bytes arrive, one per clock.
//
// A frame is six bytes: temperature MSB, LSB, CRC, humidity MSB, LSB, CRC.
// The transport marks the final byte of a transfer with in_last. A transfer
// that ends before the sixth byte is a truncated frame and is counted, not
// checked. A complete frame is good when both checksums match, and bad otherwise.
// The firmware makes the same decision in desk_decode_sht31().
module sht31_frame_check (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        in_valid,
    input  logic [7:0]  in_data,
    input  logic        in_last,
    output logic        frame_valid,      // one-cycle pulse for every frame event
    output logic        frame_good,       // complete frame, both CRCs match
    output logic        frame_bad,        // complete frame, at least one CRC wrong
    output logic        frame_truncated,  // transfer ended before six bytes
    output logic [15:0] temp_raw,         // last good frame's temperature word
    output logic [15:0] hum_raw,          // last good frame's humidity word
    output logic [15:0] good_count,       // all counters saturate at 65535
    output logic [15:0] bad_count,
    output logic [15:0] truncated_count,
    output logic [15:0] bad_temp_count,   // bad frames where the temperature CRC failed
    output logic [15:0] bad_hum_count     // bad frames where the humidity CRC failed
);
    logic [2:0] index;          // position of the next byte in the frame, 0..5
    logic [7:0] running_crc;    // CRC of the bytes of the word being received
    logic [7:0] t_msb, t_lsb, h_msb, h_lsb;
    logic       temp_ok;        // temperature checksum matched at byte 2

    logic [7:0] crc_in, crc_next;
    assign crc_in = (index == 3'd0 || index == 3'd3) ? 8'hFF : running_crc;

    sht31_crc8_step u_crc (.crc_in(crc_in), .data_in(in_data), .crc_out(crc_next));

    wire is_data_byte = (index == 3'd0) || (index == 3'd1) || (index == 3'd3) || (index == 3'd4);
    wire check_matches = (in_data == running_crc);  // only meaningful at index 2 and 5
    wire frame_ends = (index == 3'd5);
    wire ends_early = in_last && !frame_ends;

    function automatic logic [15:0] bump(input logic [15:0] value);
        bump = (value == 16'hFFFF) ? value : value + 16'd1;
    endfunction

`ifndef SYNTHESIS
    // Simulation check: a frame event is exactly one of good, bad or truncated.
    always @(posedge clk) begin
        if (frame_valid)
            assert (frame_good + frame_bad + frame_truncated == 1)
                else $error("sht31_frame_check: frame event without exactly one outcome");
        if (!frame_valid)
            assert (!frame_good && !frame_bad && !frame_truncated)
                else $error("sht31_frame_check: outcome flag without frame_valid");
    end
`endif

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            index           <= 3'd0;
            running_crc     <= 8'hFF;
            t_msb           <= 8'd0;
            t_lsb           <= 8'd0;
            h_msb           <= 8'd0;
            h_lsb           <= 8'd0;
            temp_ok         <= 1'b0;
            frame_valid     <= 1'b0;
            frame_good      <= 1'b0;
            frame_bad       <= 1'b0;
            frame_truncated <= 1'b0;
            temp_raw        <= 16'd0;
            hum_raw         <= 16'd0;
            good_count      <= 16'd0;
            bad_count       <= 16'd0;
            truncated_count <= 16'd0;
            bad_temp_count  <= 16'd0;
            bad_hum_count   <= 16'd0;
        end else begin
            frame_valid     <= 1'b0;
            frame_good      <= 1'b0;
            frame_bad       <= 1'b0;
            frame_truncated <= 1'b0;
            if (in_valid) begin
                if (is_data_byte) running_crc <= crc_next;
                case (index)
                    3'd0: t_msb <= in_data;
                    3'd1: t_lsb <= in_data;
                    3'd3: h_msb <= in_data;
                    3'd4: h_lsb <= in_data;
                    default: ;
                endcase
                if (index == 3'd2) temp_ok <= check_matches;

                if (frame_ends) begin
                    frame_valid <= 1'b1;
                    if (temp_ok && check_matches) begin
                        frame_good <= 1'b1;
                        temp_raw   <= {t_msb, t_lsb};
                        hum_raw    <= {h_msb, h_lsb};
                        good_count <= bump(good_count);
                    end else begin
                        frame_bad <= 1'b1;
                        bad_count <= bump(bad_count);
                        if (!temp_ok)       bad_temp_count <= bump(bad_temp_count);
                        if (!check_matches) bad_hum_count  <= bump(bad_hum_count);
                    end
                    index       <= 3'd0;
                    running_crc <= 8'hFF;
                end else if (ends_early) begin
                    frame_valid     <= 1'b1;
                    frame_truncated <= 1'b1;
                    truncated_count <= bump(truncated_count);
                    index           <= 3'd0;
                    running_crc     <= 8'hFF;
                end else begin
                    index <= index + 3'd1;
                end
            end
        end
    end
endmodule
