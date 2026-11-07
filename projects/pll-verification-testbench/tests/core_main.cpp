#include "Vrv32_core.h"
#include "verilated.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
#include <stdexcept>

// A byte-addressed test RAM supplies a four-byte window starting at addr.
int main(int argc, char** argv) {
    if (argc != 3) return 2;
    Verilated::commandArgs(argc, argv);
    Vrv32_core dut;
    std::vector<uint8_t> mem(1 << 20, 0);
    std::ifstream image(argv[1], std::ios::binary);
    if (!image) return 2;
    image.read(reinterpret_cast<char*>(mem.data()), mem.size());
    if (!image.eof()) return 2;
    std::ofstream trace(argv[2]);
    auto word = [&](uint32_t addr) -> uint32_t {
        if (addr > mem.size()-4) throw std::runtime_error("RAM read outside test memory");
        return uint32_t(mem[addr]) | uint32_t(mem[addr+1])<<8 |
            uint32_t(mem[addr+2])<<16 | uint32_t(mem[addr+3])<<24;
    };
    unsigned stalls=0, flushes=0, forwards=0, retired=0;
    for (unsigned cycle=0; cycle<100000; ++cycle) {
        dut.clk=0; dut.reset=cycle<2;
        dut.eval();
        dut.imem_data=word(dut.imem_addr);
        dut.dmem_rdata=dut.dmem_read ? word(dut.dmem_addr) : 0;
        dut.eval();
        // Commit RAM writes on the same edge as the memory stage.
        if (dut.dmem_wstrb) {
            if (dut.dmem_addr > mem.size()-4) return 3;
            for (unsigned i=0; i<4; ++i)
                if (dut.dmem_wstrb & (1<<i)) mem[dut.dmem_addr+i]=(dut.dmem_wdata>>(8*i))&255;
        }
        stalls+=!dut.reset && dut.stall_event;
        flushes+=!dut.reset && dut.flush_event;
        forwards+=!dut.reset && dut.forward_event;
        dut.clk=1; dut.eval();
        if (dut.retire_valid) {
            ++retired;
            trace << std::hex << dut.retire_pc << " " << dut.retire_insn << " "
                << unsigned(dut.retire_rd) << " " << dut.retire_data << "\n";
        }
        if (dut.retire_trap) {
            std::cout << "CORE cycles=" << std::dec << cycle << " retired=" << retired
                << " stalls=" << stalls << " flushes=" << flushes << " forwards=" << forwards
                << " test_number=" << dut.test_number << "\n";
            return dut.test_number == 1 && dut.retire_insn == 0x73 ? 0 : 1;
        }
    }
    std::cerr << "Processor timed out\n";
    return 1;
}
