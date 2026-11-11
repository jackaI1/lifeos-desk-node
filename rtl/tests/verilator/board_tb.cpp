// Verilator testbench for the iCEBreaker board top (rtl/board/icebreaker/desk_board_top.v).
//
// It acts as the computer: it sends transfers as serial bytes at 115200 baud on
// ftdi_rxd (104 clocks per bit at 12 MHz), and it decodes the six reply bytes
// on ftdi_txd. Every reply must match the good, bad and truncated counts that a
// Python-style reference model expects. Prints one line per transfer and a
// RESULT line. Exits 1 on any mismatch.
#include <cstdint>
#include <cstdio>
#include <vector>

#include "Vdesk_board_top.h"
#include "verilated.h"

static const int DIV = 104;  // clocks per serial bit

struct Board {
    Vdesk_board_top *top;
    int line = 1;
    int prev_tx = 1;
    // Reply decoder state
    bool mon_active = false;
    int mon_cnt = 0;
    int mon_k = 0;
    uint8_t mon_sh = 0;
    std::vector<uint8_t> replies;

    void cycle(int rx_line) {
        top->ftdi_rxd = rx_line;
        top->clk = 0;
        top->eval();
        top->clk = 1;
        top->eval();
        int tx = top->ftdi_txd;
        monitor(tx);
        prev_tx = tx;
    }

    void monitor(int tx) {
        if (!mon_active) {
            if (prev_tx == 1 && tx == 0) {
                mon_active = true;
                mon_cnt = DIV / 2;  // middle of the start bit
                mon_k = 0;
                mon_sh = 0;
            }
            return;
        }
        if (mon_cnt > 0) {
            mon_cnt--;
            return;
        }
        mon_cnt = DIV;
        if (mon_k == 0) {
            if (tx) mon_active = false;  // glitch, not a start bit
        } else if (mon_k <= 8) {
            mon_sh |= (uint8_t)(tx << (mon_k - 1));
        } else {
            replies.push_back(mon_sh);
            mon_active = false;
        }
        mon_k++;
    }

    void idle(int cycles) {
        for (int i = 0; i < cycles; i++) cycle(1);
    }

    void send_byte(uint8_t b) {
        for (int i = 0; i < DIV; i++) cycle(0);            // start bit
        for (int bit = 0; bit < 8; bit++)
            for (int i = 0; i < DIV; i++) cycle((b >> bit) & 1);
        for (int i = 0; i < DIV; i++) cycle(1);            // stop bit
    }

    // Sends one transfer and returns the six reply bytes.
    bool transfer(const std::vector<uint8_t> &payload, std::vector<uint8_t> &reply) {
        size_t before = replies.size();
        send_byte((uint8_t)payload.size());
        for (uint8_t b : payload) send_byte(b);
        for (int guard = 0; guard < 20000 && replies.size() < before + 6; guard++) cycle(1);
        if (replies.size() != before + 6) return false;
        reply.assign(replies.begin() + (long)before, replies.begin() + (long)before + 6);
        return true;
    }
};

static uint8_t crc8(const uint8_t *d, int n) {
    uint8_t crc = 0xFF;
    for (int i = 0; i < n; i++) {
        crc ^= d[i];
        for (int b = 0; b < 8; b++)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
    return crc;
}

static std::vector<uint8_t> frame(uint16_t temp, uint16_t hum) {
    uint8_t t[2] = {(uint8_t)(temp >> 8), (uint8_t)temp};
    uint8_t h[2] = {(uint8_t)(hum >> 8), (uint8_t)hum};
    return {t[0], t[1], crc8(t, 2), h[0], h[1], crc8(h, 2)};
}

static int failures = 0;
static int transfers = 0;

static void expect_counts(const char *name, const std::vector<uint8_t> &reply,
                          unsigned good, unsigned bad, unsigned trunc) {
    transfers++;
    unsigned g = (reply[0] << 8) | reply[1];
    unsigned b = (reply[2] << 8) | reply[3];
    unsigned t = (reply[4] << 8) | reply[5];
    bool ok = (g == good) && (b == bad) && (t == trunc);
    if (!ok) failures++;
    std::printf("T %-24s good=%u bad=%u trunc=%u %s\n", name, g, b, t, ok ? "ok" : "MISMATCH");
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    Vdesk_board_top *top = new Vdesk_board_top;
    Board board{top};

    board.idle(200);  // power-on reset takes 16 clocks; let the UART settle

    std::vector<uint8_t> reply;
    auto run = [&](const char *name, const std::vector<uint8_t> &payload,
                   unsigned good, unsigned bad, unsigned trunc) {
        if (!board.transfer(payload, reply)) {
            failures++;
            transfers++;
            std::printf("T %-24s no reply MISMATCH\n", name);
            return;
        }
        expect_counts(name, reply, good, bad, trunc);
    };

    // 1. One good frame.
    auto good1 = frame(0x6A5B, 0x8C2D);
    run("good frame", good1, 1, 0, 0);
    if (top->ledr != 0) { failures++; std::printf("T led red after good frame MISMATCH\n"); }

    // 2. A frame whose temperature checksum is wrong.
    auto bad1 = frame(0x5F10, 0x4A00);
    bad1[2] ^= 0x01;
    run("bad temperature CRC", bad1, 1, 1, 0);
    if (top->ledr != 1) { failures++; std::printf("T led red after bad frame MISMATCH\n"); }

    // 3. A zero length byte is ignored and sends no reply.
    size_t before_zero = board.replies.size();
    board.send_byte(0x00);
    board.idle(3000);
    if (board.replies.size() != before_zero) { failures++; std::printf("T zero length MISMATCH\n"); }
    transfers++;
    std::printf("T %-24s no reply ok\n", "zero length ignored");

    // 4. A transfer that stops after three bytes is a truncated frame.
    run("truncated frame", {0x12, 0x34, 0x56}, 1, 1, 1);

    // 5. Two good frames sent in one transfer.
    std::vector<uint8_t> two = good1;
    auto good2 = frame(0x0102, 0xFFEE);
    two.insert(two.end(), good2.begin(), good2.end());
    run("two good frames", two, 3, 1, 1);

    // 6. A frame whose humidity checksum is wrong.
    auto bad2 = frame(0x7777, 0x1234);
    bad2[5] ^= 0x80;
    run("bad humidity CRC", bad2, 3, 2, 1);

    top->final();
    delete top;
    std::printf("RESULT transfers=%d failures=%d\n", transfers, failures);
    return failures == 0 ? 0 : 1;
}
