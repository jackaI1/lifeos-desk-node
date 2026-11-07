// The processor can set the divider, capture status, and drain the sample FIFO.
// All RAM ports use the same combinational byte-window contract as rv32_core.
module pll_soc (
    input wire clk, reset, ref_pulse,
    output wire [31:0] imem_addr,
    input wire [31:0] imem_data,
    output wire [31:0] mem_addr, mem_wdata,
    output wire [3:0] mem_wstrb,
    output wire mem_read,
    input wire [31:0] mem_rdata,
    output wire retire_trap,
    output wire [31:0] test_number,
    output wire capture_valid,
    output wire mmio_write,
    output wire [31:0] capture_sample
);
    wire [3:0] bus_strobe;
    wire bus_read;
    wire selected=mem_addr[31:4]==28'h1000000;
    wire [31:0] bus_rdata;
    reg [3:0] ratio;
    reg hold_reset;
    wire feedback,up,down,locked;
    wire [3:0] control;
    wire [31:0] head;
    wire empty,full;
    wire [3:0] count;
    wire push=selected && mem_addr[3:0]==8 && |bus_strobe;
    wire pop=selected && mem_addr[3:0]==8 && bus_read;
    assign capture_sample={20'b0,ratio,control,locked,down,up,feedback};
    assign capture_valid=push && (!full || (pop && !empty)) && !reset;
    assign mmio_write=selected && |bus_strobe && !reset;
    assign bus_rdata = !selected ? mem_rdata : mem_addr[3:0]==4 ? capture_sample :
        mem_addr[3:0]==8 ? head : mem_addr[3:0]==12 ? {26'b0,full,empty,count} : {23'b0,hold_reset,4'b0,ratio};
    assign mem_wstrb=selected ? 4'b0 : bus_strobe;
    assign mem_read=bus_read && !selected;
    always @(posedge clk) begin
        if (reset) begin ratio<=2; hold_reset<=1; end
        else if (selected && mem_addr[3:0]==0 && |bus_strobe) begin
            ratio<=mem_wdata[3:0]; hold_reset<=mem_wdata[8];
        end
    end
    pll_control pll(.clk(clk),.reset(reset || hold_reset),.ref_pulse(ref_pulse),
        .ratio(ratio),.feedback(feedback),.up(up),.down(down),.locked(locked),.control(control));
    sample_fifo #(.DEPTH(8)) samples(.clk(clk),.reset(reset),.push(push),.pop(pop),
        .data_in(capture_sample),.data_out(head),.empty(empty),.full(full),.count(count));
    rv32_core cpu(.clk(clk),.reset(reset),.imem_addr(imem_addr),.imem_data(imem_data),
        .dmem_addr(mem_addr),.dmem_wdata(mem_wdata),.dmem_wstrb(bus_strobe),.dmem_read(bus_read),
        .dmem_rdata(bus_rdata),.retire_trap(retire_trap),.test_number(test_number),
        .retire_valid(),.retire_pc(),.retire_insn(),.retire_data(),.retire_rd(),
        .stall_event(),.flush_event(),.forward_event());
endmodule
