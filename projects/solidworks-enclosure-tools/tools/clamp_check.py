"""Bounded clearance screen, not clamp strength or hardware qualification."""
import argparse,json,pathlib

def check(p):
    arm_z=p['base_thickness_mm']+p['coupon_height_mm']+p['nose_depth_mm']
    head_z=arm_z+p['arm_thickness_mm']
    clearances=dict(
        pin_diametral_worst=p['locator_hole_mm']-p['hole_tolerance_mm']-p['locator_pin_mm']-p['pin_upper_tolerance_mm'],
        shoulder_diametral_worst=p['locator_counterbore_mm']-p['hole_tolerance_mm']-p['locator_shoulder_mm'],
        pivot_diametral_worst=p['pivot_hole_mm']-p['hole_tolerance_mm']-p['bolt_diameter_mm'],
        arm_to_pin_vertical=arm_z-p['locator_pin_length_mm'],
        bolt_below_nut=p['bolt_length_mm']-head_z-p['washer_thickness_mm']-p['nut_thickness_mm'],
        pivot_to_coupon=abs(p['pivot_x_mm'])-p['pivot_outer_mm']/2-p['coupon_length_mm']/2)
    return dict(clearances_mm=clearances,passes=all(x>0 for x in clearances.values()),
                intended_contacts=['pin to coupon tangent faces','nose to coupon top','pivot shoulder to arm','bolt head to arm','washer to base and nut'],
                note='Simplified clearance hardware without threads. Intended contacts are zero-gap, excluded from positive-clearance requirement. No force, deflection, thread engagement or physical test.')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('spec');a.add_argument('output');args=a.parse_args()
    p=json.loads(pathlib.Path(args.spec).read_text())
    out=pathlib.Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(baseline=check(p),cases={c['name']:check(dict(p,**c['overrides'])) for c in p['parameter_cases']}),indent=2)+'\n')
