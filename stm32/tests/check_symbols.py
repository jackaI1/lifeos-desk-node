"""Assert the linked firmware has no heap or C++ exception runtime entry points."""
from pathlib import Path
import subprocess
for image in (Path('stm32/build/bare.elf'),Path('stm32/build/rtos.elf')):
    result=subprocess.run(['arm-none-eabi-nm','--defined-only',str(image)],capture_output=True,text=True,check=True)
    symbols={line.split()[-1] for line in result.stdout.splitlines() if line.split()}
    forbidden={'malloc','calloc','realloc','free','_Znwj','_Znwm','__cxa_throw','__cxa_allocate_exception','pvPortMalloc','xTaskCreate'}
    assert not symbols&forbidden,(image,symbols&forbidden)
print('PASS: both linked ARM ELFs omit heap allocation and exception runtime entry points')
