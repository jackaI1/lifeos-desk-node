// Bare-metal adapter for upstream riscv-tests; no privileged runtime required.
#ifndef PLL_RISCV_TEST_H
#define PLL_RISCV_TEST_H
#define RVTEST_RV32U
#define RVTEST_RV64U
#define TESTNUM gp
#define RVTEST_CODE_BEGIN .section .text.init; .globl _start; _start:
#define RVTEST_CODE_END
#define RVTEST_PASS li gp, 1; ecall
#define RVTEST_FAIL slli gp, gp, 1; ori gp, gp, 3; ecall
#define RVTEST_DATA_BEGIN .balign 16;
#define RVTEST_DATA_END
#endif
