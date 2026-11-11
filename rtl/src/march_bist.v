// March C- memory self-test for the reading buffer.
//
// Six passes over every word, in this order:
//   up   (w0)     up   (r0,w1)   up   (r1,w0)
//   down (r0,w1)  down (r1,w0)   any  (r0)
// Each word holds all zeros or all ones, so every bit is read as both 0 and 1.
// A stuck-at cell fails a read in one of these passes. The first failing address
// is kept for the report. Start with `start` while `busy` is low; `done` stays
// high until the next start.
module march_bist #(
    parameter AW    = 3,
    parameter WIDTH = 32
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             start,
    output reg              busy,
    output reg              done,
    output reg              fail,
    output reg  [AW-1:0]    fail_addr,
    output wire [AW-1:0]    addr,
    output wire             we,
    output wire [WIDTH-1:0] wdata,
    input  wire [WIDTH-1:0] rdata
);
    localparam [2:0] LAST_ELEMENT = 3'd5;

    reg [2:0]    element;   // 0..5, the six passes above
    reg          sub;       // 0 or 1: second operation of a pass
    reg [AW-1:0] cursor;    // word being tested in this pass

    // Operation table. kind 0 = read, 1 = write; value 0 or 1 is the word pattern.
    reg       op_write;
    reg       op_value;
    reg       op_descending;
    reg       two_ops;
    always @* begin
        op_write = 1'b0;
        op_value = 1'b0;
        op_descending = 1'b0;
        two_ops = 1'b1;
        case (element)
            3'd0: begin op_write = 1'b1; op_value = 1'b0; two_ops = 1'b0; end
            3'd1: begin op_write = sub; op_value = sub ? 1'b1 : 1'b0; end
            3'd2: begin op_write = sub; op_value = sub ? 1'b0 : 1'b1; end
            3'd3: begin op_write = sub; op_value = sub ? 1'b1 : 1'b0; op_descending = 1'b1; end
            3'd4: begin op_write = sub; op_value = sub ? 1'b0 : 1'b1; op_descending = 1'b1; end
            default: begin op_write = 1'b0; op_value = 1'b0; two_ops = 1'b0; end
        endcase
        if (element == 3'd5) op_descending = 1'b0;
    end

    wire [WIDTH-1:0] pattern = op_value ? {WIDTH{1'b1}} : {WIDTH{1'b0}};
    wire             last_sub = !two_ops || sub;
    wire             last_word = op_descending ? (cursor == {AW{1'b0}}) : (cursor == {AW{1'b1}});
    wire             expect_ok = (rdata == pattern);

    assign addr  = cursor;
    assign we    = busy && op_write;
    assign wdata = pattern;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            busy <= 1'b0;
            done <= 1'b0;
            fail <= 1'b0;
            fail_addr <= {AW{1'b0}};
            element <= 3'd0;
            sub <= 1'b0;
            cursor <= {AW{1'b0}};
        end else if (!busy) begin
            if (start) begin
                busy <= 1'b1;
                done <= 1'b0;
                fail <= 1'b0;
                fail_addr <= {AW{1'b0}};
                element <= 3'd0;
                sub <= 1'b0;
                cursor <= {AW{1'b0}};
            end
        end else begin
            if (!op_write && !expect_ok && !fail) begin
                fail <= 1'b1;
                fail_addr <= cursor;
            end
            if (!last_sub) begin
                sub <= 1'b1;
            end else begin
                sub <= 1'b0;
                if (last_word) begin
                    if (element == LAST_ELEMENT) begin
                        busy <= 1'b0;
                        done <= 1'b1;
                    end else begin
                        element <= element + 3'd1;
                        cursor <= {AW{1'b0}};
                    end
                end else begin
                    cursor <= op_descending ? cursor - 1'b1 : cursor + 1'b1;
                end
            end
        end
    end
endmodule
