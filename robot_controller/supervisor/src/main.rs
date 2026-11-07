mod motion;
use desk_control_core::*;
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    os::fd::FromRawFd,
    thread,
    time::{Duration, Instant},
};
fn serial_pair() -> std::io::Result<(File, File)> {
    unsafe {
        let (mut master, mut slave) = (0, 0);
        if libc::openpty(
            &mut master,
            &mut slave,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        ) != 0
        {
            return Err(std::io::Error::last_os_error());
        }
        let mut attrs = std::mem::zeroed();
        libc::tcgetattr(slave, &mut attrs);
        libc::cfmakeraw(&mut attrs);
        libc::tcsetattr(slave, libc::TCSANOW, &attrs);
        Ok((File::from_raw_fd(master), File::from_raw_fd(slave)))
    }
}
#[cfg(target_os = "linux")]
fn set_fifo() -> bool {
    unsafe {
        let p = libc::sched_param { sched_priority: 10 };
        libc::sched_setscheduler(0, libc::SCHED_FIFO, &p) == 0
    }
}
#[cfg(not(target_os = "linux"))]
fn set_fifo() -> bool {
    false
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let path = args
        .next()
        .unwrap_or_else(|| "/tmp/desk-control.csv".into());
    let realtime = args.any(|a| a == "--fifo");
    let fifo = realtime && set_fifo();
    let (mut host, mut firmware) = serial_pair()?;
    let worker = thread::spawn(move || -> std::io::Result<()> {
        let mut core = Hotplate::default();
        let mut adc = SimAdc(3300);
        let mut sensor = SimSpi(Ok(20000));
        let mut pwm = SimPwm::default();
        let mut display = SimDisplay::default();
        let mut temperature = 20000.;
        for sequence in 0..100u16 {
            let mut request = [0u8; 12];
            firmware.read_exact(&mut request)?;
            let target = unpack(&request, sequence)
                .map_err(|_| std::io::Error::other("bad host frame"))?
                .0;
            sensor.0 = Ok(temperature as i32);
            let result = core.step(
                &mut adc,
                &mut sensor,
                &SimGpio(true),
                &mut pwm,
                &mut display,
                target,
            );
            temperature += (f64::from(pwm.0) * 25. - (temperature - 20000.) * 0.08) * 0.01;
            firmware.write_all(&packet(
                sequence,
                result.unwrap_or(20000),
                pwm.0,
                result.is_err(),
            ))?;
        }
        Ok(())
    });
    let mut output = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&path)?;
    writeln!(
        output,
        "sequence,jitter_us,temperature_mc,heater_percent,joint0,joint1,target0,target1,fifo"
    )?;
    let grid =
        motion::plan(5, 5, &[(2, 0), (2, 1), (2, 2), (2, 3)], (0, 0), (4, 0)).ok_or("no path")?;
    let trajectory = motion::trajectory(&grid, 0.01, 20., 200.);
    let mut pid = [motion::Pid::default(), motion::Pid::default()];
    let mut q = [0., 0.];
    let mut velocity = [0., 0.];
    let start = Instant::now();
    let mut max_jitter = 0u128;
    for sequence in 0..100u16 {
        let deadline = start + Duration::from_millis(u64::from(sequence) * 10);
        if let Some(wait) = deadline.checked_duration_since(Instant::now()) {
            thread::sleep(wait);
        }
        let jitter = Instant::now()
            .saturating_duration_since(deadline)
            .as_micros();
        max_jitter = max_jitter.max(jitter);
        host.write_all(&packet(sequence, 25000, 0, false))?;
        let mut response = [0u8; 12];
        host.read_exact(&mut response)?;
        let (t, duty, fault) =
            unpack(&response, sequence).map_err(|_| "serial CRC/counter failure")?;
        if fault {
            return Err("controller fault".into());
        }
        let target = trajectory[usize::from(sequence).min(trajectory.len() - 1)];
        for joint in 0..2 {
            let torque = pid[joint].update(target[joint], q[joint], 0.01);
            velocity[joint] += (torque - 2. * velocity[joint]) * 0.01;
            q[joint] += velocity[joint] * 0.01;
        }
        writeln!(
            output,
            "{sequence},{jitter},{t},{duty},{},{},{},{},{fifo}",
            q[0], q[1], target[0], target[1]
        )?;
    }
    worker.join().map_err(|_| "firmware thread panicked")??;
    output.sync_all()?;
    println!("100 checked serial transactions; max jitter {max_jitter} us; SCHED_FIFO={fifo}; process data {path}");
    Ok(())
}
