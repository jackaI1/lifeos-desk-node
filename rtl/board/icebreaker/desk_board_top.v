// Board top for an iCEBreaker (Lattice iCE40UP5K FPGA, 12 MHz oscillator).
//
// The computer sends sensor transfers over the board's USB serial port at
// 115200 baud. Each transfer is one length byte N (1 to 255) followed by N
// sensor bytes. The bytes go into sensor_path, which checks the SHT31 frames
// and keeps the good ones. After each transfer the board replies with six
// bytes: good, bad and truncated frame counts, each as high byte then low
// byte. Wait for the six reply bytes before sending the next transfer.
//
// LEDs: green is lit while a transfer is arriving; red is lit once any frame
// has been bad or truncated.
module desk_board_top (
    input  wire clk,        // 12 MHz board oscillator
    input  wire ftdi_rxd,   // serial data from the computer (FTDI chip)
    output wire ftdi_txd,   // serial data to the computer
    output wire ledg,
    output wire ledr
);
    localparam DIV = 104;   // 12 MHz / 115200 baud, rounded

    // Power-on reset: hold the design in reset for 16 clocks. The iCE40 flops
    // start at 0 when the bitstream loads, so the counter needs no initial value.
    // verilator lint_off SYNCASYNCNET
    reg [3:0] por_cnt;
    wire      rst_n = (por_cnt == 4'hF);
    // verilator lint_on SYNCASYNCNET
    always @(posedge clk) begin
        if (!rst_n) por_cnt <= por_cnt + 4'd1;
    end

    wire       rx_valid;
    wire [7:0] rx_byte;
    uart_rx #(.DIV(DIV)) u_rx (
        .clk(clk), .rst_n(rst_n), .rx(ftdi_rxd),
        .valid(rx_valid), .data(rx_byte));

    localparam S_LEN    = 3'd0;  // waiting for a length byte
    localparam S_DATA   = 3'd1;  // passing sensor bytes into sensor_path
    localparam S_FLUSH  = 3'd2;  // the last byte is being counted
    localparam S_SEND   = 3'd3;  // capture the counters for the reply
    localparam S_TXBYTE = 3'd4;  // start one reply byte
    localparam S_TXSTART= 3'd5;  // give the transmitter a cycle to go busy
    localparam S_TXWAIT = 3'd6;  // wait for that byte to finish

    reg [2:0]  st;
    reg [7:0]  remain;          // sensor bytes still to come in this transfer
    reg        in_valid;
    reg [7:0]  in_data;
    reg        in_last;
    reg [47:0] reply;           // counters waiting to be sent, top byte first
    reg [2:0]  left;            // reply bytes not yet started
    reg        tx_start;
    reg [7:0]  tx_data;

    wire        frame_valid, frame_good, frame_bad, frame_truncated;
    wire [15:0] good_count, bad_count, truncated_count;
    wire [15:0] bad_temp_count, bad_hum_count;
    wire [31:0] head_unused;
    wire        buffer_empty, buffer_full, buffer_overflow, scan_out;
    wire        bist_busy, bist_done, bist_fail;
    wire [2:0]  bist_fail_addr;

    wire        tx_busy;

    sensor_path u_path (
        .clk(clk), .rst_n(rst_n),
        .in_valid(in_valid), .in_data(in_data), .in_last(in_last),
        .frame_valid(frame_valid), .frame_good(frame_good), .frame_bad(frame_bad),
        .frame_truncated(frame_truncated),
        .good_count(good_count), .bad_count(bad_count), .truncated_count(truncated_count),
        .bad_temp_count(bad_temp_count), .bad_hum_count(bad_hum_count),
        .pop(1'b0), .head_data(head_unused), .buffer_empty(buffer_empty),
        .buffer_full(buffer_full), .buffer_overflow(buffer_overflow),
        .scan_en(1'b0), .scan_in(1'b0), .scan_out(scan_out),
        .bist_start(1'b0), .bist_busy(bist_busy), .bist_done(bist_done),
        .bist_fail(bist_fail), .bist_fail_addr(bist_fail_addr),
        .mem_fault_en(1'b0), .mem_fault_addr(3'd0), .mem_fault_bit(5'd0),
        .mem_fault_value(1'b0),
        .scan_fault_en(1'b0), .scan_fault_bit(4'd0), .scan_fault_value(1'b0));

    uart_tx #(.DIV(DIV)) u_tx (
        .clk(clk), .rst_n(rst_n), .start(tx_start), .data(tx_data),
        .busy(tx_busy), .tx(ftdi_txd));

    always @(posedge clk) begin
        if (!rst_n) begin
            st       <= S_LEN;
            remain   <= 8'd0;
            in_valid <= 1'b0;
            in_data  <= 8'd0;
            in_last  <= 1'b0;
            reply    <= 48'd0;
            left     <= 3'd0;
            tx_start <= 1'b0;
            tx_data  <= 8'd0;
        end else begin
            in_valid <= 1'b0;
            in_last  <= 1'b0;
            tx_start <= 1'b0;
            case (st)
                S_LEN: if (rx_valid && rx_byte != 8'd0) begin
                    remain <= rx_byte;
                    st     <= S_DATA;
                end
                S_DATA: if (rx_valid) begin
                    in_valid <= 1'b1;
                    in_data  <= rx_byte;
                    in_last  <= (remain == 8'd1);
                    remain   <= remain - 8'd1;
                    if (remain == 8'd1) st <= S_FLUSH;
                end
                // The last byte reaches sensor_path on the clock after it is
                // registered; by S_SEND the counters have all moved.
                S_FLUSH: st <= S_SEND;
                S_SEND: begin
                    reply <= {good_count, bad_count, truncated_count};
                    left  <= 3'd6;
                    st    <= S_TXBYTE;
                end
                S_TXBYTE: if (!tx_busy) begin
                    tx_data  <= reply[47:40];
                    reply    <= {reply[39:0], 8'd0};
                    tx_start <= 1'b1;
                    left     <= left - 3'd1;
                    st       <= S_TXSTART;
                end
                S_TXSTART: st <= S_TXWAIT;
                S_TXWAIT: if (!tx_busy) begin
                    st <= (left == 3'd0) ? S_LEN : S_TXBYTE;
                end
                default: st <= S_LEN;
            endcase
        end
    end

    assign ledg = (st != S_LEN);
    assign ledr = (bad_count != 16'd0) || (truncated_count != 16'd0);
endmodule
