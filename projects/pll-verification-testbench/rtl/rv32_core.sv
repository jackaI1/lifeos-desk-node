// Five stages, combinational instruction and byte-window data memory ports.
// FAST_ALU selects a four-bit carry-select adder; 0 retains the timing baseline.
module rv32_core #(parameter integer FAST_ALU=1, FLUSH_BUG=0) (
    input wire clk, reset,
    output wire [31:0] imem_addr,
    input wire [31:0] imem_data,
    output wire [31:0] dmem_addr, dmem_wdata,
    output wire [3:0] dmem_wstrb,
    output wire dmem_read,
    input wire [31:0] dmem_rdata,
    output logic retire_valid, retire_trap,
    output logic [31:0] retire_pc, retire_insn, retire_data,
    output logic [4:0] retire_rd,
    output wire [31:0] test_number,
    output wire stall_event, flush_event, forward_event
);
    logic [31:0] regs [0:31];
    logic [31:0] pc, fd_pc, fd_insn, dx_pc, dx_insn, dx_a, dx_b;
    logic fd_valid, dx_valid;
    logic xm_valid, xm_write, xm_load, xm_store, xm_trap;
    logic [31:0] xm_pc, xm_insn, xm_result, xm_b;
    logic [4:0] xm_rd;
    logic [2:0] xm_f3;
    logic mw_valid, mw_write, mw_trap;
    logic [31:0] mw_pc, mw_insn, mw_result;
    logic [4:0] mw_rd;
    wire [6:0] op = dx_insn[6:0];
    wire [2:0] f3 = dx_insn[14:12];
    wire [4:0] rs1 = dx_insn[19:15], rs2 = dx_insn[24:20];
    wire [31:0] imm_i = {{20{dx_insn[31]}},dx_insn[31:20]};
    wire [31:0] imm_s = {{20{dx_insn[31]}},dx_insn[31:25],dx_insn[11:7]};
    wire [31:0] imm_b = {{19{dx_insn[31]}},dx_insn[31],dx_insn[7],dx_insn[30:25],dx_insn[11:8],1'b0};
    wire [31:0] imm_j = {{11{dx_insn[31]}},dx_insn[31],dx_insn[19:12],dx_insn[20],dx_insn[30:21],1'b0};
    wire m1 = xm_valid && xm_write && !xm_load && xm_rd != 0 && xm_rd == rs1;
    wire m2 = xm_valid && xm_write && !xm_load && xm_rd != 0 && xm_rd == rs2;
    wire w1 = mw_valid && mw_write && mw_rd != 0 && mw_rd == rs1;
    wire w2 = mw_valid && mw_write && mw_rd != 0 && mw_rd == rs2;
    wire [31:0] a = rs1 == 0 ? 0 : m1 ? xm_result : w1 ? mw_result : dx_a;
    wire [31:0] b = rs2 == 0 ? 0 : m2 ? xm_result : w2 ? mw_result : dx_b;
    wire [6:0] dop = fd_insn[6:0];
    wire uses1 = dop == 7'h33 || dop == 7'h13 || dop == 7'h03 || dop == 7'h23 || dop == 7'h63 || dop == 7'h67;
    wire uses2 = dop == 7'h33 || dop == 7'h23 || dop == 7'h63;
    wire stall = fd_valid && dx_valid && op == 7'h03 && dx_insn[11:7] != 0 &&
        ((uses1 && fd_insn[19:15] == dx_insn[11:7]) || (uses2 && fd_insn[24:20] == dx_insn[11:7]));

    function automatic [31:0] add32(input [31:0] lhs, rhs, input sub);
        reg [31:0] y, sum;
        reg [32:0] carry;
        reg [4:0] z0, z1;
        integer k;
        begin
            y = rhs ^ {32{sub}};
            carry = 0; carry[0] = sub; sum = 0;
            if (FAST_ALU != 0) begin
                for (k=0; k<8; k=k+1) begin
                    z0 = {1'b0,lhs[k*4+:4]} + {1'b0,y[k*4+:4]};
                    z1 = {1'b0,lhs[k*4+:4]} + {1'b0,y[k*4+:4]} + 5'd1;
                    {carry[(k+1)*4],sum[k*4+:4]} = carry[k*4] ? z1 : z0;
                end
            end else begin
                for (k=0; k<32; k=k+1) begin
                    sum[k] = lhs[k] ^ y[k] ^ carry[k];
                    carry[k+1] = (lhs[k] & y[k]) | ((lhs[k] ^ y[k]) & carry[k]);
                end
            end
            add32 = sum;
        end
    endfunction

    wire [31:0] alu_b = op == 7'h33 ? b : op == 7'h23 ? imm_s : imm_i;
    wire subtract = op == 7'h33 && f3 == 0 && dx_insn[30];
    wire [31:0] added = add32(a, alu_b, subtract);
    logic [31:0] result, target;
    logic write_rd, load_op, store_op, trap_op, redirect, branch_taken;
    always_comb begin
        result=0; target=dx_pc+imm_b; write_rd=0; load_op=0; store_op=0;
        trap_op=0; redirect=0; branch_taken=0;
        case (f3)
            0: branch_taken = a == b;
            1: branch_taken = a != b;
            4: branch_taken = $signed(a) < $signed(b);
            5: branch_taken = $signed(a) >= $signed(b);
            6: branch_taken = a < b;
            7: branch_taken = a >= b;
            default: branch_taken=0;
        endcase
        case (op)
            7'h37: begin result={dx_insn[31:12],12'b0}; write_rd=1; end
            7'h17: begin result=dx_pc+{dx_insn[31:12],12'b0}; write_rd=1; end
            7'h6f: begin result=dx_pc+4; target=dx_pc+imm_j; write_rd=1; redirect=1; end
            7'h67: begin result=dx_pc+4; target=added & 32'hfffffffe; write_rd=1; redirect=1; end
            7'h63: redirect=branch_taken;
            7'h03: begin result=added; write_rd=1; load_op=1; end
            7'h23: begin result=added; store_op=1; end
            7'h13,7'h33: begin
                write_rd=1;
                case (f3)
                    0: result=added;
                    1: result=a << alu_b[4:0];
                    2: result={31'b0,$signed(a) < $signed(alu_b)};
                    3: result={31'b0,a < alu_b};
                    4: result=a ^ alu_b;
                    5: result=dx_insn[30] ? $unsigned($signed(a) >>> alu_b[4:0]) : a >> alu_b[4:0];
                    6: result=a | alu_b;
                    7: result=a & alu_b;
                endcase
            end
            // FENCE.I redirects to discard prefetched instructions after code stores.
            7'h0f: begin redirect=f3==1; target=dx_pc+4; end
            7'h73: begin trap_op=1; redirect=1; target=dx_pc; end
            default: begin trap_op=1; redirect=1; target=dx_pc; end
        endcase
    end
    wire flush = dx_valid && redirect;
    assign imem_addr=pc;
    assign dmem_addr=xm_result;
    assign dmem_wdata=xm_b;
    assign dmem_read=xm_valid && xm_load && !reset;
    assign dmem_wstrb=(!reset && xm_valid && xm_store) ? (xm_f3==0 ? 4'b0001 : xm_f3==1 ? 4'b0011 : 4'b1111) : 0;
    logic [31:0] loaded;
    always_comb begin
        case (xm_f3)
            0: loaded={{24{dmem_rdata[7]}},dmem_rdata[7:0]};
            1: loaded={{16{dmem_rdata[15]}},dmem_rdata[15:0]};
            4: loaded={24'b0,dmem_rdata[7:0]};
            5: loaded={16'b0,dmem_rdata[15:0]};
            default: loaded=dmem_rdata;
        endcase
    end
    assign test_number=regs[3];
    assign stall_event=stall && !flush;
    assign flush_event=flush;
    assign forward_event=dx_valid && (m1 || m2 || w1 || w2);
    integer i;
    always_ff @(posedge clk) begin
        if (reset) begin
            pc<=0; fd_valid<=0; dx_valid<=0; xm_valid<=0; mw_valid<=0;
            retire_valid<=0; retire_trap<=0;
            fd_pc<=0; fd_insn<=0; dx_pc<=0; dx_insn<=0; dx_a<=0; dx_b<=0;
            xm_write<=0; xm_load<=0; xm_store<=0; xm_trap<=0;
            xm_pc<=0; xm_insn<=0; xm_result<=0; xm_b<=0; xm_rd<=0; xm_f3<=0;
            mw_write<=0; mw_trap<=0; mw_pc<=0; mw_insn<=0; mw_result<=0; mw_rd<=0;
            retire_pc<=0; retire_insn<=0; retire_data<=0; retire_rd<=0;
            for (i=0;i<32;i=i+1) regs[i]<=0;
        end else begin
            regs[0]<=0;
            if (mw_valid && mw_write && mw_rd!=0) regs[mw_rd]<=mw_result;
            retire_valid<=mw_valid; retire_pc<=mw_pc; retire_insn<=mw_insn;
            retire_rd<=mw_write ? mw_rd : 0; retire_data<=mw_result;
            retire_trap<=mw_valid && mw_trap;
            mw_valid<=xm_valid; mw_write<=xm_write; mw_trap<=xm_trap;
            mw_pc<=xm_pc; mw_insn<=xm_insn; mw_rd<=xm_rd;
            mw_result<=xm_load ? loaded : xm_result;
            xm_valid<=dx_valid; xm_write<=write_rd; xm_load<=load_op;
            xm_store<=store_op; xm_trap<=trap_op; xm_pc<=dx_pc; xm_insn<=dx_insn;
            xm_result<=result; xm_b<=b; xm_rd<=dx_insn[11:7]; xm_f3<=f3;
            if (flush) begin
                pc<=target; dx_valid<=0;
                if (FLUSH_BUG==0) fd_valid<=0;
            end else if (stall) dx_valid<=0;
            else begin
                pc<=pc+4; fd_pc<=pc; fd_insn<=imem_data; fd_valid<=1;
                dx_pc<=fd_pc; dx_insn<=fd_insn; dx_valid<=fd_valid;
                dx_a <= fd_insn[19:15]==0 ? 0 :
                    mw_valid && mw_write && mw_rd==fd_insn[19:15] ? mw_result : regs[fd_insn[19:15]];
                dx_b <= fd_insn[24:20]==0 ? 0 :
                    mw_valid && mw_write && mw_rd==fd_insn[24:20] ? mw_result : regs[fd_insn[24:20]];
            end
        end
    end
`ifdef FORMAL
    reg past_valid=0;
    always @(posedge clk) begin
        past_valid<=1;
        if (!past_valid) assume(reset);
        if (past_valid && !$past(reset) && !reset) begin
            assert(regs[0]==0);
            if ($past(flush)) begin
                assert(pc==$past(target));
                assert(!fd_valid && !dx_valid);
            end else if ($past(stall)) begin
                assert(pc==$past(pc));
                assert(fd_valid==$past(fd_valid) && fd_insn==$past(fd_insn));
                assert(!dx_valid);
            end else assert(pc==$past(pc)+4);
            if (dx_valid) begin
                if (rs1==0) assert(a==0);
                else if (m1) assert(a==xm_result);
                else if (w1) assert(a==mw_result);
                if (rs2==0) assert(b==0);
                else if (m2) assert(b==xm_result);
                else if (w2) assert(b==mw_result);
            end
            cover(flush && fd_valid);
            cover(stall);
            cover(dx_valid && m1 && w1);
        end
    end
`endif
endmodule
