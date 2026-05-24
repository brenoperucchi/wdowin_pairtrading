from gex.engine.b3_parser import get_b3_options_data
from gex.engine.walls_calculator import calculate_gex_profile

df = get_b3_options_data(181897.0)

print("\n--- NEW WALLS (IV = 5.79%) ---")
new_walls = calculate_gex_profile(df, 184290.0, 181897.0, 0.05794402510568584, 27, 0.145)
for w in new_walls:
    print(f"{w['type']} @ {w['price']:.1f} | Width {w['width']}")

print("\n--- OLD WALLS (IV = 20.00%) ---")
old_walls = calculate_gex_profile(df, 184290.0, 181897.0, 0.20, 27, 0.145)
for w in old_walls:
    print(f"{w['type']} @ {w['price']:.1f} | Width {w['width']}")
