*** Settings ***
Suite Setup                   Setup
Suite Teardown                Teardown
Test Setup                    Reset Emulation
Resource                      ${RENODEKEYWORDS}

*** Test Cases ***
Bare Metal Sensor And Timer
    Execute Command           include @${CURDIR}/Sht31.cs
    Execute Command           mach create
    Execute Command           machine LoadPlatformDescription @${CURDIR}/desk.repl
    Execute Command           sysbus LoadELF @${CURDIR}/../build/bare.elf
    Create Terminal Tester    sysbus.usart2
    Start Emulation
    Wait For Line On Uart     SENSOR PASS temperature=25000 humidity=50001
    Wait For Line On Uart     BAREMETAL PASS timer interrupt

FreeRTOS Sensor Task
    Execute Command           include @${CURDIR}/Sht31.cs
    Execute Command           mach create
    Execute Command           machine LoadPlatformDescription @${CURDIR}/desk.repl
    Execute Command           sysbus LoadELF @${CURDIR}/../build/rtos.elf
    Create Terminal Tester    sysbus.usart2
    Start Emulation
    Wait For Line On Uart     SENSOR PASS temperature=25000 humidity=50001
    Wait For Line On Uart     FREERTOS PASS scheduled sensor task
