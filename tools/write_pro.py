"""write a minimal KiCad project file carrying the design rules.  usage: write_pro.py out.kicad_pro clearance edge_clearance"""
import json, sys, os
out, clr, edge = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
vd, vh = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (0.6, 0.3)
name = os.path.basename(out)
json.dump({
 "board": {"design_settings": {
   "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2},
   "rules": {"min_clearance": clr, "min_track_width": 0.15, "min_via_diameter": 0.45, "min_through_hole_diameter": 0.2,
             "min_via_annular_width": 0.1, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25, "min_copper_edge_clearance": edge,
             "min_connection": 0.0, "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "min_silk_clearance": 0.0,
             "min_text_height": 0.6, "min_text_thickness": 0.08, "solder_mask_to_copper_clearance": 0.0},
   "rule_severities": {k: "ignore" for k in ("lib_footprint_issues", "lib_footprint_mismatch", "npth_inside_courtyard", "silk_over_copper",
                       "silk_overlap", "silk_edge_clearance", "text_height", "text_thickness", "footprint_type_mismatch", "missing_courtyard",
                       "isolated_copper")} | {k: "warning" for k in ("courtyards_overlap", "solder_mask_bridge", "starved_thermal",
                       "via_dangling", "track_dangling")},
   "track_widths": [0.0, 0.2, 0.3, 0.4, 0.5], "via_dimensions": [{"diameter": 0.6, "drill": 0.3}, {"diameter": 0.45, "drill": 0.2}]}},
 "net_settings": {"classes": [{"name": "Default", "clearance": clr, "track_width": 0.2, "via_diameter": vd, "via_drill": vh,
                  "diff_pair_gap": 0.2, "diff_pair_width": 0.2, "microvia_diameter": 0.3, "microvia_drill": 0.1, "wire_width": 6,
                  "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}],
                  "meta": {"version": 3}},
 "meta": {"filename": name, "version": 3}}, open(out, 'w'), indent=1)
