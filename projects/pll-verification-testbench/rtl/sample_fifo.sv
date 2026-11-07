// Queue for 32-bit PLL status samples. A full queue can replace the popped word.
module sample_fifo #(parameter integer WIDTH=32, DEPTH=8) (
    input logic clk, reset, push, pop,
    input logic [WIDTH-1:0] data_in,
    output logic [WIDTH-1:0] data_out,
    output wire empty, full,
    output logic [$clog2(DEPTH+1)-1:0] count
);
    localparam integer PTR_W = DEPTH > 1 ? $clog2(DEPTH) : 1;
    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [PTR_W-1:0] rd, wr;
    wire take = pop && !empty;
    wire put = push && (!full || take);
    assign empty = count == 0;
    assign full = count == DEPTH;
    assign data_out = empty ? '0 : mem[rd];
    always_ff @(posedge clk) begin
        if (reset) begin rd <= 0; wr <= 0; count <= 0; end
        else begin
            if (put) begin
                mem[wr] <= data_in;
                wr <= wr == DEPTH-1 ? '0 : wr + 1'b1;
            end
            if (take) rd <= rd == DEPTH-1 ? '0 : rd + 1'b1;
            case ({put,take})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: begin end
            endcase
        end
    end
`ifndef SYNTHESIS
    assert property (@(posedge clk) disable iff (reset) count <= DEPTH);
    assert property (@(posedge clk) disable iff (reset) rd < DEPTH && wr < DEPTH);
    assert property (@(posedge clk) disable iff (reset) full && push && !pop |=> reset || $stable(count));
    assert property (@(posedge clk) disable iff (reset) empty && pop && !push |=> reset || $stable(count));
`endif
endmodule
