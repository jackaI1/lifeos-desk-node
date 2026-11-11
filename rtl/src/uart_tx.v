// Sends one byte at a time on a serial line: start bit, 8 data bits (least
// significant first), one stop bit. The line idles high.
//
// Pulse `start` for one cycle while `busy` is low, with the byte on `data`.
// `busy` stays high until the stop bit has been sent.
module uart_tx #(
    parameter DIV = 104
) (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       start,
    input  wire [7:0] data,
    output wire       busy,
    output wire       tx
);
    reg        active;
    reg [9:0]  frame;          // bit 0 is the start bit, bit 9 the stop bit
    reg [3:0]  bitn;
    reg [15:0] tick;

    assign busy = active;
    assign tx   = active ? frame[0] : 1'b1;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active <= 1'b0;
            frame  <= 10'h3FF;
            bitn   <= 4'd0;
            tick   <= 16'd0;
        end else if (!active) begin
            if (start) begin
                frame  <= {1'b1, data, 1'b0};
                bitn   <= 4'd0;
                tick   <= DIV - 1;
                active <= 1'b1;
            end
        end else if (tick == 16'd0) begin
            tick  <= DIV - 1;
            frame <= {1'b1, frame[9:1]};
            bitn  <= bitn + 4'd1;
            if (bitn == 4'd9) active <= 1'b0;
        end else begin
            tick <= tick - 16'd1;
        end
    end
endmodule
