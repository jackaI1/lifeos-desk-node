#![no_std]
/// The firmware depends on small interfaces so the simulator exercises the
/// same feedback logic as the embedded target, without claiming real wiring.
pub trait Adc { fn supply_mv(&mut self) -> u16; }
pub trait Spi { fn temperature_mc(&mut self) -> Result<i32, Fault>; }
pub trait Gpio { fn interlock_ok(&self) -> bool; }
pub trait Pwm { fn heater(&mut self, percent: u8); }
pub trait I2c { fn display(&mut self, temperature_mc: i32, duty: u8); }
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Fault { Sensor, Supply, Interlock, Frame }
pub struct Hotplate { integral: i32, pub duty: u8 }
impl Default for Hotplate { fn default()->Self {Self{integral:0,duty:0}} }
impl Hotplate {
    pub fn step<A:Adc,S:Spi,G:Gpio,P:Pwm,I:I2c>(&mut self, adc:&mut A,spi:&mut S,gpio:&G,pwm:&mut P,display:&mut I,setpoint:i32)->Result<i32,Fault>{
        let result=if !gpio.interlock_ok(){Err(Fault::Interlock)}else if adc.supply_mv()<3100{Err(Fault::Supply)}else{spi.temperature_mc()};
        match result {
            Ok(t) if (-45000..=125000).contains(&t) && (10000..=60000).contains(&setpoint) => {
                let error=(setpoint-t)/100;
                let candidate=(self.integral+error).clamp(-10000,10000);
                let output=error/10+candidate/100;
                if (0..=100).contains(&output) {self.integral=candidate;}
                self.duty=output.clamp(0,100) as u8;pwm.heater(self.duty);display.display(t,self.duty);Ok(t)
            }
            other=>{self.duty=0;self.integral=0;pwm.heater(0);Err(other.err().unwrap_or(Fault::Sensor))}
        }
    }
}
/// One frame: sync(2), sequence(2), signed temperature(4), duty(1), fault(1), CRC(2).
pub fn crc(bytes:&[u8])->u16 {let mut crc=0xffffu16;for byte in bytes{crc^=u16::from(*byte)<<8;for _ in 0..8{crc=(crc<<1)^if crc&0x8000!=0{0x1021}else{0};}}crc}
pub fn packet(sequence:u16,temperature:i32,duty:u8,fault:bool)->[u8;12]{
    let mut out=[0u8;12];out[0..2].copy_from_slice(b"DS");out[2..4].copy_from_slice(&sequence.to_le_bytes());out[4..8].copy_from_slice(&temperature.to_le_bytes());out[8]=duty;out[9]=u8::from(fault);let sum=crc(&out[..10]);out[10..].copy_from_slice(&sum.to_le_bytes());out
}
pub fn unpack(data:&[u8],expected:u16)->Result<(i32,u8,bool),Fault>{
    if data.len()!=12||&data[..2]!=b"DS"||u16::from_le_bytes([data[2],data[3]])!=expected||crc(&data[..10])!=u16::from_le_bytes([data[10],data[11]])||data[8]>100||data[9]>1{return Err(Fault::Frame);}
    let t=i32::from_le_bytes([data[4],data[5],data[6],data[7]]);if !(-45000..=125000).contains(&t){return Err(Fault::Sensor);}Ok((t,data[8],data[9]==1))
}
pub struct SimAdc(pub u16);impl Adc for SimAdc {fn supply_mv(&mut self)->u16{self.0}}
pub struct SimSpi(pub Result<i32,Fault>);impl Spi for SimSpi {fn temperature_mc(&mut self)->Result<i32,Fault>{self.0}}
pub struct SimGpio(pub bool);impl Gpio for SimGpio {fn interlock_ok(&self)->bool{self.0}}
#[derive(Default)]pub struct SimPwm(pub u8);impl Pwm for SimPwm{fn heater(&mut self,p:u8){self.0=p;}}
#[derive(Default)]pub struct SimDisplay(pub (i32,u8));impl I2c for SimDisplay{fn display(&mut self,t:i32,p:u8){self.0=(t,p);}}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn feedback_uses_all_peripherals_and_fails_safe(){let mut h=Hotplate::default();let mut a=SimAdc(3300);let mut s=SimSpi(Ok(20000));let mut p=SimPwm::default();let mut d=SimDisplay::default();assert_eq!(h.step(&mut a,&mut s,&SimGpio(true),&mut p,&mut d,25000),Ok(20000));assert!(p.0>0);assert_eq!(d.0.0,20000);assert_eq!(h.step(&mut a,&mut s,&SimGpio(false),&mut p,&mut d,25000),Err(Fault::Interlock));assert_eq!(p.0,0);a.0=3000;assert_eq!(h.step(&mut a,&mut s,&SimGpio(true),&mut p,&mut d,25000),Err(Fault::Supply));a.0=3300;s.0=Err(Fault::Sensor);assert_eq!(h.step(&mut a,&mut s,&SimGpio(true),&mut p,&mut d,25000),Err(Fault::Sensor));}
 #[test]fn checked_serial_rejects_corruption_counter_and_size(){let mut bytes=packet(65535,-1000,30,false);assert_eq!(unpack(&bytes,65535),Ok((-1000,30,false)));assert_eq!(unpack(&bytes,0),Err(Fault::Frame));bytes[5]^=1;assert_eq!(unpack(&bytes,65535),Err(Fault::Frame));assert_eq!(unpack(&bytes[..11],0),Err(Fault::Frame));assert_eq!(crc(b"123456789"),0x29b1);}
}
