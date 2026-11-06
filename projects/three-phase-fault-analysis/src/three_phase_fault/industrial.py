"""Synthetic industrial feeder: balanced load flow and IEC 60909 faults."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandapower as pp
import pandapower.shortcircuit as sc


def build_network():
    net = pp.create_empty_network(sn_mva=10)
    source = pp.create_bus(net, vn_kv=11, name="Utility 11 kV")
    main = pp.create_bus(net, vn_kv=0.4, name="Main switchboard")
    motors = pp.create_bus(net, vn_kv=0.4, name="Motor control centre")
    workshop = pp.create_bus(net, vn_kv=0.4, name="Workshop")
    pp.create_ext_grid(net, source, s_sc_max_mva=250, rx_max=0.1, s_sc_min_mva=200, rx_min=0.1)
    pp.create_transformer_from_parameters(
        net,
        source,
        main,
        sn_mva=1.0,
        vn_hv_kv=11,
        vn_lv_kv=0.4,
        vk_percent=6,
        vkr_percent=1,
        pfe_kw=1.5,
        i0_percent=0.2,
        name="1 MVA transformer",
    )
    for end, length, name in [(motors, 0.12, "MCC cable"), (workshop, 0.18, "Workshop cable")]:
        pp.create_line_from_parameters(
            net,
            main,
            end,
            length_km=length,
            r_ohm_per_km=0.124,
            x_ohm_per_km=0.08,
            c_nf_per_km=0,
            max_i_ka=0.35,
            name=name,
        )
    pp.create_load(net, motors, p_mw=0.45, q_mvar=0.25, name="Motor group")
    pp.create_load(net, workshop, p_mw=0.18, q_mvar=0.09, name="Workshop motors")
    pp.create_sgen(
        net,
        main,
        p_mw=0.4,
        q_mvar=0,
        sn_mva=0.5,
        name="Standby generator (isolated)",
        in_service=False,
    )
    return net


def run_study(net):
    pp.runpp(net, numba=False)
    sc.calc_sc(net, fault="3ph", case="max")
    buses = []
    violations = []
    for idx, bus in net.bus.iterrows():
        voltage = float(net.res_bus.at[idx, "vm_pu"])
        buses.append(
            {
                "name": bus["name"],
                "voltage_pu": voltage,
                "fault_ka": float(net.res_bus_sc.at[idx, "ikss_ka"]),
            }
        )
        if not 0.95 <= voltage <= 1.05:
            violations.append(f"Voltage at {bus['name']}: {voltage:.3f} pu (limit 0.95–1.05)")
    for idx, line in net.line.iterrows():
        loading = float(net.res_line.at[idx, "loading_percent"])
        if loading > 100:
            violations.append(f"Cable {line['name']}: {loading:.1f}% of current rating")
    for idx, trafo in net.trafo.iterrows():
        loading = float(net.res_trafo.at[idx, "loading_percent"])
        if loading > 100:
            violations.append(f"Transformer {trafo['name']}: {loading:.1f}% of rating")
    # Illustrative breaker interrupting ratings, kA RMS at each bus.
    for bus, rating in zip(buses, (16, 20, 10, 10)):
        bus["breaker_rating_ka"] = rating
        if bus["fault_ka"] > rating:
            violations.append(
                f"Breaker at {bus['name']}: {bus['fault_ka']:.2f} kA exceeds {rating} kA"
            )
    return {
        "buses": buses,
        "cables": [
            {"name": row["name"], "loading_percent": float(net.res_line.at[i, "loading_percent"])}
            for i, row in net.line.iterrows()
        ],
        "transformer_loading_percent": float(net.res_trafo.loading_percent.iloc[0]),
        "violations": violations,
    }


def plot_one_line(net, path):
    fig, ax = plt.subplots(figsize=(9, 4))
    positions = [(0, 2), (3, 2), (6, 3), (6, 1)]
    for a, b in [(0, 1), (1, 2), (1, 3)]:
        ax.plot([positions[a][0], positions[b][0]], [positions[a][1], positions[b][1]], "k-")
    for i, (x, y) in enumerate(positions):
        ax.plot(x, y, "s", markersize=10, color="navy")
        ax.annotate(
            net.bus.at[i, "name"], (x, y), xytext=(0, 12), textcoords="offset points", ha="center"
        )
    ax.text(3, 1.4, "Standby generator\n(isolated)", ha="center")
    ax.text(1.5, 1.7, "1 MVA transformer", ha="center")
    ax.set(xlim=(-1, 7), ylim=(0, 4), title="Synthetic industrial distribution system")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/industrial"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    net = build_network()
    result = run_study(net)
    (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    plot_one_line(net, args.output / "one-line.png")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
