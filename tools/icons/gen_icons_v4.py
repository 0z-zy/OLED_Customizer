from PIL import Image
import os

assets_dir = "content/assets/"
os.makedirs(assets_dir, exist_ok=True)

def create_icon(name, grid):
    # 0=Black, 1=White
    img = Image.new("1", (12, 12), 0)
    pixels = img.load()
    for y, row in enumerate(grid):
        for x, char in enumerate(row):
            if char == "1":
                pixels[x, y] = 1
    img.save(os.path.join(assets_dir, name))
    print(f"Saved {name}")

# Canvas 12x12
# Layout:
# x=0,1,2,3,4: Body
# x=5: Gap
# x=6: Wave 1 (Low)
# x=7: Gap
# x=8: Wave 2 (Mid)
# x=9: Gap
# x=10: Wave 3 (High)
# x=11: Gap/Padding

# Body (5px wide)
# .....
# ..11.
# .111.
# 11111
# ...
body_rows = [
    "00110",
    "01110",
    "11111",
    "11111",
    "11111",
    "11111",
    "11111",
    "11111",
    "01110",
    "00110", 
] # This is 10 rows? centered vertically in 12px
# Let's do full 12 rows definition

# Full Grid Builder
def make_grid(has_w1, has_w2, has_w3, is_mute):
    grid = []
    for y in range(12):
        row = ""
        # 0-4: Body
        if 1 <= y <= 10: # Vertically centered body
            if y in [1, 10]: row += "00110"
            elif y in [2, 9]: row += "01110"
            else: row += "11111"
        else:
            row += "00000"
            
        row += "0" # x=5 Gap
        
        # x=6: Wave 1
        if has_w1 and 3 <= y <= 8:
            if y in [3, 8]: row += "1"
            else: row += "1" # Straight line or curve? 
            # Let's make it curved:
            # y3: 0 (gap)
            # y4-y7: 1
            # y8: 0
        elif has_w1 and (y==3 or y==8):
             row += "0" # Curve ends ??
             # Simplest 12px pixel art: vertical line segments
        
        # Let's stick to simple patterns
        # Wave 1 (x=6): 
        w1_val = "0"
        if has_w1 and 4 <= y <= 7: w1_val = "1"
        row += w1_val
        
        row += "0" # x=7 Gap
        
        # Wave 2 (x=8)
        w2_val = "0"
        if has_w2:
            if 3 <= y <= 8:
                if y in [3, 8]: w2_val = "1" # Corner
                elif y in [4, 7]: w2_val = "0" # Gap? No standard arc
                # Standard arc:
                # ..1..
                # .1.1.
                # 1...1
                
                # Vertical strip style:
                # x=6:  ...1111...
                # x=8:  ..111111..
                if y >= 2 and y <= 9: w2_val = "1"
                
        # Let's try specific verified pixel art
        # Re-doing row building logic is error prone.
        # Using fixed arrays.
        pass
    return []

# Better Approach: Fixed Arrays for V4
# 012345678901
# ...11.......
# ..111.......
# .1111.1.....
# 11111.1.1...
# 11111.1.1.1.
# 11111.1.1.1.
# 11111.1.1.1.
# 11111.1.1...
# .1111.1.....
# ..111.......
# ...11.......
# ............

# Body part
# x=0-4
b = [
    "00011",
    "00111",
    "01111",
    "11111",
    "11111",
    "11111",
    "11111",
    "01111",
    "00111",
    "00011",
    "00000",
    "00000"
]
# Shift body down by 1 to enter
b = ["00000"] + b[:11]

# Wave 1 (Low) at x=6
# Pattern:
# ...
# .1.
# .1.
# .1.
# .1.
# ...
w1 = [
    "0", "0", "0", "0",
    "1", "1", "1", "1",
    "0", "0", "0", "0"
]

# Wave 2 (Mid) at x=8
# Taller
w2 = [
    "0", "0", "0",
    "1", "1", "1", "1", "1", "1",
    "0", "0", "0"
]

# Wave 3 (High) at x=10
# Tallest
w3 = [
    "0", "0",
    "1", "1", "1", "1", "1", "1", "1", "1",
    "0", "0"
]

# Mute X at x=6,7,8
# Start y=4
# 101
# 010
# 101
mx = [
    "000", "000", "000", "000",
    "101", "010", "101",
    "000", "000", "000", "000", "000" # Length mismatch, fix below
]

def build_row(y, mode):
    # Base Body (0-4) + Gap(5)
    row = b[y] + "0"
    
    if mode == "mute":
        # x=6,7,8
        # Center the X vertically? y=4,5,6
        is_x = False
        if 4 <= y <= 6:
            r_idx = y - 4
            # 4->0 (101), 5->1 (010), 6->2 (101)
            pat = ["101", "010", "101"][r_idx]
            row += pat
        else:
            row += "000"
        row += "000" # Fill rest
        return row

    # Wave 1 (x=6)
    has_w1 = mode in ["low", "mid", "high"]
    row += w1[y] if has_w1 else "0"
    
    row += "0" # Gap x=7
    
    # Wave 2 (x=8)
    has_w2 = mode in ["mid", "high"]
    row += w2[y] if has_w2 else "0"
    
    row += "0" # Gap x=9
    
    # Wave 3 (x=10)
    has_w3 = mode in ["high"]
    row += w3[y] if has_w3 else "0"
    
    row += "0" # Gap x=11
    
    return row

def generate(name, mode):
    grid = [build_row(y, mode) for y in range(12)]
    create_icon(name, grid)

generate("speaker_mute_v4.png", "mute")
generate("speaker_low_v4.png", "low")
generate("speaker_mid_v4.png", "mid")
generate("speaker_high_v4.png", "high")
