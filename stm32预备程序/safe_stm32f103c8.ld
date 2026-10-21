ENTRY(Reset_Handler)
MEMORY {
 FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
 RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 20K
}
_estack = ORIGIN(RAM) + LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) . = ALIGN(4); } > FLASH
 .ARM.extab : { *(.ARM.extab*) } > FLASH
 .ARM.exidx : { __exidx_start = .; *(.ARM.exidx*) __exidx_end = .; } > FLASH
 .data : {
   . = ALIGN(4); _sdata = .; *(.data*) . = ALIGN(4); _edata = .;
 } > RAM AT> FLASH
 _sidata = LOADADDR(.data);
 .bss (NOLOAD) : {
   . = ALIGN(4); _sbss = .; *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .;
 } > RAM
 .heap_stack (NOLOAD) : {
   . = ALIGN(8); end = .; _end = .; . += 0x200; . += 0x800;
 } > RAM
 /DISCARD/ : { *(.note.GNU-stack) *(.comment) }
}

