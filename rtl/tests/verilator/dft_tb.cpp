// Verilator testbench for the reading buffer's scan chain and March C- self-test.
//
// 1. Functional: random push and pop traffic against a software queue, including
//    overflow, checked every cycle.
// 2. Scan: the control flops are shifted in and out with several patterns. The
//    output must return each pattern exactly.
// 3. Self-test, fault free: BIST must finish with no failure.
// 4. Self-test, injected faults: every memory bit (8 words x 32 bits) is forced to 0
//    and to 1, one at a time. BIST must fail and report the faulty word.
// 5. Scan, injected faults: every control flop is forced to 0 and to 1, one at a time.
//    The shifted patterns must show a mismatch.
// Prints a coverage report and exits 1 if a functional check fails or a fault is missed.
#include <cstdint>
#include <cstdio>
#include <deque>
#include <random>
#include <vector>

#include "Vreading_buffer.h"
#include "verilated.h"

namespace {

constexpr int kDepth = 8;
constexpr int kWidth = 32;
constexpr int kControlBits = 3 * 3 + 2;   // 3*AW + 2 for AW = 3

struct Bench {
    Vreading_buffer dut;
    uint64_t cycle = 0;

    void tick() {
        dut.clk = 1; dut.eval(); dut.clk = 0; dut.eval();
        ++cycle;
    }
    void reset() {
        dut.rst_n = 0;
        dut.push = 0; dut.pop = 0; dut.scan_en = 0; dut.scan_in = 0; dut.bist_start = 0;
        dut.mem_fault_en = 0; dut.scan_fault_en = 0;
        tick(); tick();
        dut.rst_n = 1;
        tick();
    }
};

int failures = 0;
void expect(bool condition, const char *what, uint64_t cycle) {
    if (!condition) {
        std::printf("FAIL cycle %llu: %s\n", static_cast<unsigned long long>(cycle), what);
        ++failures;
    }
}

void functional(Bench &b) {
    b.reset();
    std::deque<uint32_t> model;
    bool model_overflow = false;
    std::mt19937 rng(20260);
    for (int step = 0; step < 20000; ++step) {
        bool push = (rng() % 100) < 55;
        bool pop = (rng() % 100) < 45;
        uint32_t value = rng();
        b.dut.push = push;
        b.dut.push_data = value;
        b.dut.pop = pop;
        b.dut.eval();
        expect(b.dut.empty == model.empty(), "empty flag", b.cycle);
        expect(b.dut.full == (model.size() == kDepth), "full flag", b.cycle);
        expect(b.dut.overflow == model_overflow, "overflow flag", b.cycle);
        if (!model.empty()) {
            expect(b.dut.head_data == model.front(), "head data", b.cycle);
        }
        // Model the same edge: pop first, then push (a push into a full buffer drops the oldest).
        bool did_pop = pop && !model.empty();
        if (did_pop) model.pop_front();
        if (push) {
            if (model.size() == kDepth) {
                model.pop_front();
                model_overflow = true;
            }
            model.push_back(value);
        }
        b.tick();
    }
    b.dut.push = 0;
    b.dut.pop = 0;
    std::printf("functional: 20000 random cycles, queue and overflow match the model\n");
}

std::vector<uint32_t> scan_patterns() {
    std::vector<uint32_t> patterns = {0x0, 0x7FF, 0x555, 0x2AA};
    for (int i = 0; i < kControlBits; ++i) {
        patterns.push_back(1u << i);
        patterns.push_back(~(1u << i) & ((1u << kControlBits) - 1));
    }
    return patterns;
}

// Shifts a pattern in while reading it out; returns true when every bit comes back.
bool shift_pattern(Bench &b, uint32_t pattern) {
    std::vector<int> out(2 * kControlBits, 0);
    b.dut.scan_en = 1;
    b.dut.push = 0;
    b.dut.pop = 0;
    for (int t = 0; t < 2 * kControlBits; ++t) {
        int bit = t < kControlBits ? (pattern >> (kControlBits - 1 - t)) & 1 : 0;
        b.dut.scan_in = bit;
        b.dut.eval();
        out[t] = b.dut.scan_out;
        b.tick();
    }
    b.dut.scan_en = 0;
    // Bit j, shifted in before edge j, reaches the last flop and is read before edge kControlBits + j.
    for (int j = 0; j < kControlBits; ++j) {
        int want = (pattern >> (kControlBits - 1 - j)) & 1;
        if (out[kControlBits + j] != want) return false;
    }
    return true;
}

void scan_fault_free(Bench &b) {
    b.reset();
    for (uint32_t pattern : scan_patterns()) {
        expect(shift_pattern(b, pattern), "scan chain returns the shifted pattern", b.cycle);
    }
    std::printf("scan chain: %zu patterns shift through all %d control flops unchanged\n",
                scan_patterns().size(), kControlBits);
}

bool run_bist(Bench &b, int max_cycles) {
    b.dut.bist_start = 1;
    b.tick();
    b.dut.bist_start = 0;
    for (int i = 0; i < max_cycles; ++i) {
        if (b.dut.bist_done) return true;
        b.tick();
    }
    return b.dut.bist_done;
}

void self_test(Bench &b) {
    b.reset();
    expect(run_bist(b, 500), "BIST finishes on a fault-free buffer", b.cycle);
    expect(!b.dut.bist_fail, "BIST reports no failure on a fault-free buffer", b.cycle);
    std::printf("self-test fault free: done=%d fail=%d\n", b.dut.bist_done, b.dut.bist_fail);
}

}  // namespace

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    Bench b;
    functional(b);
    scan_fault_free(b);
    self_test(b);

    int mem_total = 0, mem_detected = 0, mem_located = 0;
    for (int addr = 0; addr < kDepth; ++addr) {
        for (int bit = 0; bit < kWidth; ++bit) {
            for (int value = 0; value < 2; ++value) {
                b.reset();
                b.dut.mem_fault_en = 1;
                b.dut.mem_fault_addr = addr;
                b.dut.mem_fault_bit = bit;
                b.dut.mem_fault_value = value;
                ++mem_total;
                bool done = run_bist(b, 500);
                if (done && b.dut.bist_fail) ++mem_detected;
                if (done && b.dut.bist_fail && b.dut.bist_fail_addr == addr) ++mem_located;
                if (!(done && b.dut.bist_fail && b.dut.bist_fail_addr == addr)) {
                    std::printf("MISSED memory stuck-at-%d: word %d bit %d\n", value, addr, bit);
                }
            }
        }
    }

    int scan_total = 0, scan_detected = 0;
    for (int bit = 0; bit < kControlBits; ++bit) {
        for (int value = 0; value < 2; ++value) {
            b.reset();
            b.dut.scan_fault_en = 1;
            b.dut.scan_fault_bit = bit;
            b.dut.scan_fault_value = value;
            ++scan_total;
            bool all_match = true;
            for (uint32_t pattern : scan_patterns()) {
                if (!shift_pattern(b, pattern)) { all_match = false; break; }
            }
            if (!all_match) ++scan_detected;
            else std::printf("MISSED scan stuck-at-%d: flop %d\n", value, bit);
        }
    }

    std::printf("COVERAGE memory stuck-at: detected %d/%d (%.2f%%), failing word located %d/%d\n",
                mem_detected, mem_total, 100.0 * mem_detected / mem_total, mem_located, mem_total);
    std::printf("COVERAGE scan chain stuck-at: detected %d/%d (%.2f%%)\n",
                scan_detected, scan_total, 100.0 * scan_detected / scan_total);
    bool complete = mem_detected == mem_total && mem_located == mem_total && scan_detected == scan_total;
    std::printf("RESULT %s failures=%d\n", (complete && failures == 0) ? "PASS" : "FAIL", failures);
    return (complete && failures == 0) ? 0 : 1;
}
