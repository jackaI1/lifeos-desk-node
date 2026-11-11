// One byte of the SHT31 CRC-8: polynomial 0x31, MSB first, as in the datasheet
// and in firmware/components/desk_core/desk_core.c (desk_crc8).
// Feed a running CRC and the next data byte; get the updated CRC.
module sht31_crc8_step (
    input  wire [7:0] crc_in,
    input  wire [7:0] data_in,
    output wire [7:0] crc_out
);
    function [7:0] crc_byte;
        input [7:0] crc;
        input [7:0] data;
        integer i;
        reg [7:0] value;
        begin
            value = crc ^ data;
            for (i = 0; i < 8; i = i + 1) begin
                value = value[7] ? ((value << 1) ^ 8'h31) : (value << 1);
            end
            crc_byte = value;
        end
    endfunction

    assign crc_out = crc_byte(crc_in, data_in);
endmodule
