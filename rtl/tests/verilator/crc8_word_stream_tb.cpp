// Verilator testbench for crc8_word_stream.
// Reads vector lines "<word hex4> <check hex2> <expected 0|1> <frame> <word index>",
// drives one word per clock, and checks the block's verdict one clock later.
// Prints "W <frame> <word> <ok>" for each word, then a RESULT line. Exits 1 on any mismatch.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "Vcrc8_word_stream.h"
#include "verilated.h"

struct Vector {
    uint16_t word;
    uint8_t check;
    int expected;
    int frame;
    int index;
};

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);
    if (argc < 2) {
        std::fprintf(stderr, "usage: %s vectors.txt\n", argv[0]);
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::fprintf(stderr, "cannot open %s\n", argv[1]);
        return 2;
    }
    std::vector<Vector> vectors;
    std::string data;
    int expected, frame, index;
    std::string check_hex;
    while (in >> data >> check_hex >> expected >> frame >> index) {
        if (data.size() != 4 || check_hex.size() != 2) {
            std::fprintf(stderr, "bad vector line near %s\n", data.c_str());
            return 2;
        }
        Vector v{static_cast<uint16_t>(std::stoul(data, nullptr, 16)),
                 static_cast<uint8_t>(std::stoul(check_hex, nullptr, 16)), expected, frame, index};
        vectors.push_back(v);
    }

    Vcrc8_word_stream dut;
    dut.clk = 0;
    dut.rst_n = 0;
    dut.in_valid = 0;
    dut.in_word = 0;
    dut.in_check = 0;
    for (int i = 0; i < 2; ++i) {
        dut.clk = 1; dut.eval(); dut.clk = 0; dut.eval();
    }
    dut.rst_n = 1;

    int mismatches = 0, good = 0, bad = 0;
    // Word n is presented before the clock edge of cycle n; its verdict is registered on that edge.
    for (size_t n = 0; n < vectors.size(); ++n) {
        const Vector &v = vectors[n];
        dut.in_valid = 1;
        dut.in_word = v.word;
        dut.in_check = v.check;
        dut.clk = 1; dut.eval(); dut.clk = 0; dut.eval();
        if (!dut.out_valid) {
            std::printf("MISSING result for frame %d word %d\n", v.frame, v.index);
            ++mismatches;
            continue;
        }
        bool ok = dut.out_ok;
        std::printf("W %d %d %d\n", v.frame, v.index, ok ? 1 : 0);
        if (ok != (v.expected == 1)) {
            std::printf("MISMATCH frame %d word %d: rtl=%d reference=%d\n", v.frame, v.index,
                        ok ? 1 : 0, v.expected);
            ++mismatches;
        }
        if (ok) ++good; else ++bad;
    }
    std::printf("RESULT words=%zu good=%d bad=%d mismatches=%d\n", vectors.size(), good, bad, mismatches);
    return mismatches == 0 ? 0 : 1;
}
