import json
import os

# --- DÁN TOÀN BỘ JSON CỦA ÔNG VÀO ĐÂY ---
with open('all_level.json', 'r') as f:
    RAW_DATA = json.load(f)

def convert():
    os.makedirs('levels', exist_ok=True)
    
    for i, stage in enumerate(RAW_DATA):
        rows = len(stage["grid"])
        cols = max(len(r) for r in stage["grid"])
        
        new_stage = {
            "name": stage["name"],
            "passcode": stage.get("passcode", ""),
            "rows": rows,
            "cols": cols,
            "start_pos": None,
            "goal_pos": None,
            "grid": [],
            "bridges": {},
            "initial_bridges_status": [],
            "switches": {}
        }
        
        # 1. Xử lý Cầu (Bridges) & Lấy trạng thái khởi tạo
        for b_idx, b_coords in enumerate(stage.get("bridges", [])):
            new_stage["bridges"][str(b_idx)] = b_coords
            # Check xem ô cầu đầu tiên là chữ hoa 'B' (Mở) hay chữ thường 'b' (Đóng)
            r, c = b_coords[0]
            is_open = (stage["grid"][r][c] == 'B')
            new_stage["initial_bridges_status"].append(is_open)
            
        # 2. Xử lý Nút Tách / Dịch chuyển (Teleports)
        teleport_map = {}
        for t in stage.get("teleports", []):
            # t format: [r, c, target1_r, target1_c, target2_r, target2_c, ???]
            r, c, tr1, tc1, tr2, tc2, _ = t
            teleport_map[(r, c)] = {
                "type": "SPLIT",
                "target_pos1": [tr1, tc1],
                "target_pos2": [tr2, tc2]
            }

        # 3. Quét mảng lưới (Grid) để parse TileType
        for r, row_str in enumerate(stage["grid"]):
            new_row = []
            for c in range(cols):
                char = row_str[c] if c < len(row_str) else ' '
                
                if char == ' ':   new_row.append("0") # VOID
                elif char == '.': new_row.append("1") # FLOOR
                elif char == '-': new_row.append("F") # FRAGILE
                elif char == 'S': 
                    new_row.append("S") # START
                    new_stage["start_pos"] = [r, c]
                elif char == 'H': 
                    new_row.append("G") # GOAL (Lỗ đích)
                    new_stage["goal_pos"] = [r, c]
                elif char in ['B', 'b']: 
                    new_row.append("B") # BRIDGE
                elif char == 'X':
                    new_row.append("1") # FLOOR (Bên dưới nút X vẫn là sàn)
                    new_stage["switches"][f"{r},{c}"] = {"type": "HEAVY", "actions": []}
                elif char == 'O':
                    new_row.append("1")
                    new_stage["switches"][f"{r},{c}"] = {"type": "SOFT", "actions": []}
                elif char == 'T':
                    new_row.append("1")
                    new_stage["switches"][f"{r},{c}"] = teleport_map.get((r, c))
                else:
                    new_row.append("1") # Fallback
            new_stage["grid"].append(new_row)
            
        # 4. Gắn Action (Hành động) cho các nút X và O
        for sw in stage.get("switches", []):
            r, c, actions = sw
            key = f"{r},{c}"
            if key in new_stage["switches"]:
                new_stage["switches"][key]["actions"] = actions

        # 5. Lưu thành file
        # 5. Lưu thành file (Dùng Custom Formatter để mảng grid nằm trên 1 dòng)
        filename = f"stage_{i+1:02d}.json"
        
        # 5.1 Convert dictionary sang chuỗi JSON có format chuẩn
        json_str = json.dumps(new_stage, indent=4)
        
        # 5.2 Tìm và nén các dòng mảng con bên trong "grid" lại thành 1 dòng
        # Kỹ thuật: Tìm dấu ngoặc vuông mở [, bỏ hết \n và dấu cách cho đến dấu ngoặc đóng ]
        import re
        
        # Biểu thức chính quy (Regex) tìm mảng 1 chiều chứa string (như ["0", "1", "0"])
        # và nén nó lại trên cùng 1 dòng
        compressed_json = re.sub(
            r'\[\s+("[^"]+")((?:,\s*"[^"]+")*)\s+\]',
            lambda m: '[' + m.group(1) + re.sub(r'\s+', ' ', m.group(2)) + ']',
            json_str
        )
        
        # Ghi ra file
        with open(os.path.join('levels', filename), 'w') as f:
            f.write(compressed_json)
            
        print(f"Đã tạo thành công {filename}")

if __name__ == "__main__":
    convert()