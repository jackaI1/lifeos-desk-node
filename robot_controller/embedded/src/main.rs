#![cfg_attr(target_os = "none", no_std)]
#![cfg_attr(target_os = "none", no_main)]
#[cfg(not(target_os = "none"))]
fn main() {}
#[cfg(target_os = "none")]
mod target {
    use cortex_m_rt::entry;
    use cortex_m_semihosting::{debug, hprintln};
    use desk_control_core::*;
    #[panic_handler]
    fn panic(_: &core::panic::PanicInfo) -> ! {
        debug::exit(debug::EXIT_FAILURE);
        loop {}
    }
    #[entry]
    fn main() -> ! {
        let mut core = Hotplate::default();
        let mut adc = SimAdc(3300);
        let mut spi = SimSpi(Ok(20000));
        let mut pwm = SimPwm::default();
        let mut display = SimDisplay::default();
        assert!(core
            .step(
                &mut adc,
                &mut spi,
                &SimGpio(true),
                &mut pwm,
                &mut display,
                25000
            )
            .is_ok());
        assert!(pwm.0 > 0);
        assert_eq!(display.0 .0, 20000);
        assert!(core
            .step(
                &mut adc,
                &mut spi,
                &SimGpio(false),
                &mut pwm,
                &mut display,
                25000
            )
            .is_err());
        assert_eq!(pwm.0, 0);
        let sample = packet(0, 20000, 0, false);
        assert!(unpack(&sample, 0).is_ok());
        hprintln!("PASS: no_std ARM feedback, simulated ADC SPI GPIO PWM I2C and CRC");
        debug::exit(debug::EXIT_SUCCESS);
        loop {}
    }
}
