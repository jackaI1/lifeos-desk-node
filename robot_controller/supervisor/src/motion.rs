use std::collections::VecDeque;
/// Breadth-first shortest grid path. Every segment is checked against obstacles.
pub fn plan(
    width: usize,
    height: usize,
    blocked: &[(usize, usize)],
    start: (usize, usize),
    goal: (usize, usize),
) -> Option<Vec<(usize, usize)>> {
    if width == 0
        || height == 0
        || width > 100
        || height > 100
        || start.0 >= width
        || start.1 >= height
        || goal.0 >= width
        || goal.1 >= height
        || blocked.contains(&start)
        || blocked.contains(&goal)
    {
        return None;
    }
    let index = |p: (usize, usize)| p.1 * width + p.0;
    let mut previous = vec![None; width * height];
    let mut queue = VecDeque::from([start]);
    previous[index(start)] = Some(start);
    while let Some(p) = queue.pop_front() {
        if p == goal {
            let mut path = vec![p];
            while *path.last().unwrap() != start {
                path.push(previous[index(*path.last().unwrap())]?);
            }
            path.reverse();
            return Some(path);
        }
        for next in [
            (p.0.wrapping_sub(1), p.1),
            (p.0 + 1, p.1),
            (p.0, p.1.wrapping_sub(1)),
            (p.0, p.1 + 1),
        ] {
            if next.0 < width
                && next.1 < height
                && !blocked.contains(&next)
                && previous[index(next)].is_none()
            {
                previous[index(next)] = Some(p);
                queue.push_back(next);
            }
        }
    }
    None
}
#[derive(Default)]
pub struct Pid {
    integral: f64,
    previous: f64,
}
impl Pid {
    pub fn update(&mut self, target: f64, actual: f64, dt: f64) -> f64 {
        let error = target - actual;
        let candidate = (self.integral + error * dt).clamp(-2., 2.);
        let output = 12. * error + 2. * candidate + 1.5 * (error - self.previous) / dt;
        self.previous = error;
        if output.abs() < 10. {
            self.integral = candidate;
        }
        output.clamp(-10., 10.)
    }
}
/// Cubic ease-in/out rest-to-rest profile. Segment duration is lengthened until
/// its analytic velocity and acceleration limits are both satisfied.
pub fn trajectory(
    path: &[(usize, usize)],
    dt: f64,
    max_velocity: f64,
    max_acceleration: f64,
) -> Vec<[f64; 2]> {
    assert!(dt > 0. && max_velocity > 0. && max_acceleration > 0.);
    let mut out = Vec::new();
    for segment in path.windows(2) {
        let a = segment[0];
        let b = segment[1];
        let distance =
            ((b.0 as f64 - a.0 as f64).powi(2) + (b.1 as f64 - a.1 as f64).powi(2)).sqrt();
        let duration =
            (1.5 * distance / max_velocity).max((6. * distance / max_acceleration).sqrt());
        let steps = (duration / dt).ceil() as usize;
        for i in 0..steps {
            let u = i as f64 / steps as f64;
            let s = 3. * u * u - 2. * u * u * u;
            out.push([
                a.0 as f64 + (b.0 as f64 - a.0 as f64) * s,
                a.1 as f64 + (b.1 as f64 - a.1 as f64) * s,
            ]);
        }
    }
    if let Some(p) = path.last() {
        out.push([p.0 as f64, p.1 as f64]);
    }
    out
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn obstacle_path_and_unreachable() {
        let blocked = [(2, 0), (2, 1), (2, 2), (2, 3)];
        let path = plan(5, 5, &blocked, (0, 0), (4, 0)).unwrap();
        assert_eq!(path.len(), 13);
        assert!(path.iter().all(|p| !blocked.contains(p)));
        assert!(plan(2, 2, &[(0, 1), (1, 0)], (0, 0), (1, 1)).is_none());
    }
    #[test]
    fn bounded_trajectory_and_two_joint_pid() {
        let dt = 0.01;
        let trace = trajectory(&[(0, 0), (1, 0), (1, 1)], dt, 1., 2.);
        let velocities: Vec<_> = trace
            .windows(2)
            .map(|w| [(w[1][0] - w[0][0]) / dt, (w[1][1] - w[0][1]) / dt])
            .collect();
        assert!(velocities.iter().flatten().all(|v| v.abs() <= 1.001));
        for w in velocities.windows(2) {
            for j in 0..2 {
                assert!(((w[1][j] - w[0][j]) / dt).abs() < 2.01);
            }
        }
        let mut pid = [Pid::default(), Pid::default()];
        let mut q = [0., 0.];
        let mut v = [0., 0.];
        for target in trace.iter().chain(std::iter::repeat(&[1., 1.]).take(1000)) {
            for j in 0..2 {
                let torque = pid[j].update(target[j], q[j], dt);
                v[j] += (torque - 2. * v[j]) * dt;
                q[j] += v[j] * dt;
            }
        }
        assert!((q[0] - 1.).abs() < 0.01 && (q[1] - 1.).abs() < 0.01);
    }
}
