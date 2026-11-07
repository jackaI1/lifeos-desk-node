ENTRY(_start)
SECTIONS {
  . = 0;
  .text : { *(.text.init) *(.text*) }
  . = ALIGN(4096);
  .data : { *(.data*) *(.rodata*) *(.bss*) }
}
