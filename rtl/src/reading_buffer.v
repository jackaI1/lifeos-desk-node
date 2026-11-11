// Eight-entry buffer for good sensor readings, with a scan chain and a self-test.
//
// Functional use: `push` stores one reading at the tail; `pop` removes the oldest
// one. When the buffer is full, a push overwrites the oldest reading and sets
// `overflow`, which stays set until reset. Pushes and pops are ignored while the
// self-test runs or while the scan chain is shifting.
//
// Scan chain: the control flops (head, tail, count and overflow) form one shift
// chain. With `scan_en` high, `scan_in` enters the first flop and `scan_out`
// leaves the last one on each clock. Each flop has a 2:1 mux in front of it.
//
// Test hooks (`mem_fault_*` and `scan_fault_*`) force one memory bit or one
// chain flop to a fixed value. They exist for the Verilator testbench, which
// injects stuck-at faults. Tie them to 0 in a production design.
module reading_buffer #(
    parameter AW    = 3,
    parameter WIDTH = 32
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             push,
    input  wire [WIDTH-1:0] push_data,
    input  wire             pop,
    output wire [WIDTH-1:0] head_data,
    output wire             empty,
    output wire             full,
    output wire             overflow,
    input  wire             scan_en,
    input  wire             scan_in,
    output wire             scan_out,
    input  wire             bist_start,
    output wire             bist_busy,
    output wire             bist_done,
    output wire             bist_fail,
    output wire [AW-1:0]    bist_fail_addr,
    input  wire             mem_fault_en,
    input  wire [AW-1:0]    mem_fault_addr,
    input  wire [4:0]       mem_fault_bit,
    input  wire             mem_fault_value,
    input  wire             scan_fault_en,
    input  wire [3:0]       scan_fault_bit,
    input  wire             scan_fault_value
);
    localparam DEPTH = 1 << AW;
    localparam NC = 3*AW + 2;        // head, tail, count (AW+1 bits) and overflow

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [NC-1:0]    ctrl;            // {overflow, count, tail, head}

    wire [AW-1:0] head  = ctrl[AW-1:0];
    wire [AW-1:0] tail  = ctrl[2*AW-1:AW];
    wire [AW:0]   count = ctrl[3*AW:2*AW];
    wire          ovf   = ctrl[3*AW+1];

    assign empty    = (count == 0);
    assign full     = (count == DEPTH);
    assign overflow = ovf;

    wire [AW-1:0]    bist_addr;
    wire             bist_we;
    wire [WIDTH-1:0] bist_wdata;

    // Memory read path, with the optional stuck-at hook applied.
    wire [AW-1:0]    rd_addr  = bist_busy ? bist_addr : head;
    wire [WIDTH-1:0] raw_read = mem[rd_addr];
    wire [WIDTH-1:0] bit_mask = {{(WIDTH-1){1'b0}}, 1'b1} << mem_fault_bit;
    wire             hit      = mem_fault_en && (rd_addr == mem_fault_addr);
    wire [WIDTH-1:0] read_data = !hit ? raw_read
                               : (mem_fault_value ? (raw_read | bit_mask) : (raw_read & ~bit_mask));
    assign head_data = read_data;

    // Self-test drives the memory while it is busy.
    march_bist #(.AW(AW), .WIDTH(WIDTH)) u_bist (
        .clk(clk), .rst_n(rst_n), .start(bist_start),
        .busy(bist_busy), .done(bist_done), .fail(bist_fail), .fail_addr(bist_fail_addr),
        .addr(bist_addr), .we(bist_we), .wdata(bist_wdata), .rdata(read_data));

    wire do_pop  = pop && !empty && !bist_busy && !scan_en;
    wire do_push = push && !bist_busy && !scan_en;

    always @(posedge clk) begin
        if (do_push) mem[tail] <= push_data;
        else if (bist_busy && bist_we) mem[bist_addr] <= bist_wdata;
    end

    reg [AW-1:0] n_head, n_tail;
    reg [AW:0]   n_count;
    reg          n_ovf;
    reg [NC-1:0] next_ctrl;
    always @* begin
        n_head = head;
        n_tail = tail;
        n_count = count;
        n_ovf = ovf;
        if (do_pop) begin
            n_head = head + 1'b1;
            n_count = count - 1'b1;
        end
        if (do_push) begin
            n_tail = tail + 1'b1;
            if (full && !do_pop) begin
                n_head = head + 1'b1;   // overwrite the oldest reading
                n_ovf = 1'b1;
            end else begin
                n_count = n_count + 1'b1;
            end
        end
        if (bist_busy) begin
            n_head = head;
            n_tail = tail;
            n_count = count;
            n_ovf = ovf;
        end
        next_ctrl = scan_en ? {ctrl[NC-2:0], scan_in} : {n_ovf, n_count, n_tail, n_head};
        if (scan_fault_en) next_ctrl[scan_fault_bit] = scan_fault_value;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) ctrl <= {NC{1'b0}};
        else        ctrl <= next_ctrl;
    end

    assign scan_out = ctrl[NC-1];
endmodule
