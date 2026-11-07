// Digital control model: ref_pulse is synchronous to clk; this is not an analog oscillator.
module pll_control #(parameter integer INJECT_BUG = 0) (
    input logic clk, reset, ref_pulse,
    input logic [3:0] ratio,
    output logic feedback, up, down, locked,
    output logic [3:0] control
);
    logic [3:0] div_count;
    logic [2:0] stable;
    wire [3:0] limit = (ratio < 2) ? 4'd2 : ratio;
    wire tick = (div_count == limit - (INJECT_BUG != 0 ? 4'd2 : 4'd1));
    // The phase detector must never request both directions at once.
`ifndef SYNTHESIS
    assert property (@(posedge clk) disable iff (reset) !(up && down));
`endif

    always_ff @(posedge clk) begin
        if (reset) begin
            div_count <= 0; feedback <= 0; up <= 0; down <= 0;
            control <= 8; stable <= 0; locked <= 0;
        end else begin
            if (tick) div_count <= 0;
            else div_count <= div_count + 1'b1;
            feedback <= tick;
            up <= ref_pulse && !tick;
            down <= tick && !ref_pulse;
            if (ref_pulse && !tick && control != 15) control <= control + 1'b1;
            else if (tick && !ref_pulse && control != 0) control <= control - 1'b1;
            if (ref_pulse && tick) begin
                if (stable < 4) stable <= stable + 1'b1;
                if (stable >= 3) locked <= 1;
            end else if (ref_pulse || tick) begin
                stable <= 0; locked <= 0;
            end
        end
    end
endmodule
