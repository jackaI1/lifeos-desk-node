#include <stdint.h>
extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;
extern void start_main(void), HardFault_Handler(void), SysTick_Handler(void);
#ifdef DESK_RTOS
extern void vPortSVCHandler(void), xPortPendSVHandler(void), xPortSysTickHandler(void);
#endif
static void Default_Handler(void) {
    for (;;) {
    }
}
void Reset_Handler(void) {
    uint32_t *source = &_sidata;
    for (uint32_t *p = &_sdata; p < &_edata;)
        *p++ = *source++;
    for (uint32_t *p = &_sbss; p < &_ebss;)
        *p++ = 0;
    start_main();
    for (;;) {
    }
}
__attribute__((section(".isr_vector"), used)) void (*const vectors[16])(void) = {
    (void (*)(void))&_estack,
    Reset_Handler,
    Default_Handler,
    HardFault_Handler,
    Default_Handler,
    Default_Handler,
    Default_Handler,
    0,
    0,
    0,
    0,
#ifdef DESK_RTOS
    vPortSVCHandler,
    Default_Handler,
    0,
    xPortPendSVHandler,
    xPortSysTickHandler
#else
    Default_Handler,
    Default_Handler,
    0,
    Default_Handler,
    SysTick_Handler
#endif
};
