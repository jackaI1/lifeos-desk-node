// CRC-8 over a stream of 16-bit SHT31 words.
//
// Each word is two data bytes, the same unit the sensor sends before its
// checksum byte. The block computes the CRC of both bytes starting from 0xFF
// and compares it with the checksum that came with the word. The result comes
// out one clock later, so the block adds one register stage and no stalls.
module crc8_word_stream (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        in_valid,
    input  wire [15:0] in_word,   // {MSB, LSB} as the sensor sends them
    input  wire [7:0]  in_check,  // the checksum byte that followed the word
    output reg         out_valid,
    output reg  [7:0]  out_crc,   // CRC computed by the block
    output reg         out_ok     // out_crc == in_check
);
    wire [7:0] after_msb;
    wire [7:0] after_lsb;
    sht31_crc8_step u_msb (.crc_in(8'hFF),     .data_in(in_word[15:8]), .crc_out(after_msb));
    sht31_crc8_step u_lsb (.crc_in(after_msb), .data_in(in_word[7:0]),  .crc_out(after_lsb));

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out_valid <= 1'b0;
            out_crc   <= 8'h00;
            out_ok    <= 1'b0;
        end else begin
            out_valid <= in_valid;
            if (in_valid) begin
                out_crc <= after_lsb;
                out_ok  <= (after_lsb == in_check);
            end
        end
    end
endmodule
