// Receives one byte at a time from a serial line: 8 data bits, least
// significant bit first, one stop bit, no parity. The line idles high.
//
// DIV is the number of clock cycles per bit. For a 12 MHz clock and 115200
// baud, DIV is 104 (12,000,000 / 115,200 = 104.2).
module uart_rx #(
    parameter DIV = 104
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       rx,
    output reg        valid,   // one-cycle pulse when a byte has been received
    output reg [7:0]  data
);
    reg [1:0]  sync;           // two flops bring the line into this clock domain
    reg        active;
    reg [15:0] tick;
    reg [3:0]  bitn;           // 0 = start bit, 1..8 = data bits, 9 = stop bit
    reg [7:0]  shift;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sync   <= 2'b11;
            active <= 1'b0;
            tick   <= 16'd0;
            bitn   <= 4'd0;
            shift  <= 8'd0;
            valid  <= 1'b0;
            data   <= 8'd0;
        end else begin
            valid <= 1'b0;
            sync  <= {sync[0], rx};
            if (!active) begin
                // Falling edge: the start bit begins. Sample in the middle of each bit.
                if (!sync[1]) begin
                    active <= 1'b1;
                    tick   <= DIV / 2;
                    bitn   <= 4'd0;
                end
            end else if (tick == 16'd0) begin
                tick <= DIV - 1;
                if (bitn == 4'd0) begin
                    // A start bit that has gone high again was only noise.
                    if (sync[1]) active <= 1'b0;
                    bitn <= 4'd1;
                end else if (bitn <= 4'd8) begin
                    shift <= {sync[1], shift[7:1]};
                    bitn  <= bitn + 4'd1;
                end else begin
                    valid  <= 1'b1;
                    data   <= shift;
                    active <= 1'b0;
                end
            end else begin
                tick <= tick - 16'd1;
            end
        end
    end
endmodule
