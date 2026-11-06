"""Local Flask form. Run: flask --app reactor.web run --host 127.0.0.1."""

from flask import Flask, render_template, request

from .analysis import analyze
from .circuit import fault_current
from .coils import Coil

DEFAULTS = dict(
    mean_radius_mm="100",
    length_mm="400",
    turns_per_layer="400",
    layers="1",
    wire_diameter_mm="0.5",
    radial_pitch_mm="1",
    voltage_kv="11",
    base_mva="10",
    frequency_hz="60",
    source_r_pu="0.01",
    source_x_pu="0.1",
)


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16384

    @app.route("/", methods=["GET", "POST"])
    def index():
        values = (
            dict(DEFAULTS)
            if request.method == "GET"
            else {key: request.form.get(key, "") for key in DEFAULTS}
        )
        report, circuit, error = None, None, None
        try:
            # int('1.5') rejects partial turns rather than silently rounding them.
            coil = Coil(
                mean_radius_m=float(values["mean_radius_mm"]) / 1000,
                length_m=float(values["length_mm"]) / 1000,
                turns_per_layer=int(values["turns_per_layer"]),
                layers=int(values["layers"]),
                wire_diameter_m=float(values["wire_diameter_mm"]) / 1000,
                radial_pitch_m=float(values["radial_pitch_mm"]) / 1000,
            )
            circuit_inputs = {
                key: float(values[key])
                for key in ("voltage_kv", "base_mva", "frequency_hz", "source_r_pu", "source_x_pu")
            }
            # Validate circuit before spending time on sheet integrations.
            fault_current(0.0, **circuit_inputs)
            report = analyze(coil)
            circuit = fault_current(report["inductance_h"]["filament"], **circuit_inputs)
        except (ValueError, OverflowError) as exc:
            report, circuit = None, None
            error = str(exc)
        return render_template(
            "index.html", values=values, report=report, circuit=circuit, error=error
        ), 400 if error else 200

    return app
