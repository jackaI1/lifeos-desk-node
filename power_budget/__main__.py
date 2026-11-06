"""Estimate Rev A USB input current, given an observed wake duration.

This is a first-order, datasheet-based estimate, not a measurement.
"""
import argparse
import math


def estimate(active_s, sleep_s, active_ma, display_ma, led_forward_v):
    values = (active_s, sleep_s, active_ma, display_ma, led_forward_v)
    if not all(math.isfinite(x) for x in values):
        raise ValueError("inputs must be finite")
    if active_s < 0 or sleep_s <= 0 or active_ma < 0 or display_ma < 0 or not 0 <= led_forward_v <= 3.3:
        raise ValueError("invalid time, current, or LED voltage")
    duty = active_s / (active_s + sleep_s)
    return {
        "ESP32": active_ma * duty + 0.010 * (1 - duty),
        "SHT31 idle": 0.0002,
        "AZ1117C quiescent": 4.0,
        "power LED (assumed Vf)": (3.3 - led_forward_v),
        "display (user supplied)": display_ma,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-seconds", type=float, required=True, help="observed or assumed awake duration")
    parser.add_argument("--sleep-seconds", type=float, default=300, help="firmware deep-sleep interval (default: 300)")
    parser.add_argument("--active-ma", type=float, default=112, help="awake current assumption (default: Wi-Fi RX datasheet current)")
    parser.add_argument("--display-ma", type=float, required=True, help="measured or assumed OLED module current")
    parser.add_argument("--led-forward-v", type=float, required=True, help="measured or assumed red LED forward voltage")
    args = parser.parse_args()
    try:
        parts = estimate(args.active_seconds, args.sleep_seconds, args.active_ma, args.display_ma, args.led_forward_v)
    except ValueError as exc:
        parser.error(str(exc))
    print("Rev A USB input estimate (mA; not a measurement)")
    for label, current in parts.items():
        print(f"{label}: {current:.4f}")
    print(f"Total: {sum(parts.values()):.4f}")


if __name__ == "__main__":
    main()
