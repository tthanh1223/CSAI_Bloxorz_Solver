# Bàn giao GUI hiện hành — 20/10/2026

## Chạy

```
python main_test.py
python main_test.py --theme blueprint
python main_test.py --theme forest
```

Dream City mặc định; bấm tên theme cạnh logo để đổi vòng. Có `run_blueprint.cmd`
và `run_forest.cmd` trên Windows. Ba theme dùng chung Pygame, không cần cài thêm.
`--forest` riêng là bản OpenGL thử nghiệm cũ, cần `requirements-forest.txt`;
không nhầm với `--theme forest` được khuyên dùng.

## Trạng thái thiết kế đã chốt

- Dream/Paper: champagne brass có vân xước nhẹ, block viền đen than theo yêu cầu.
- Forest: trả về vàng gold có texture đá từ atlas, không dùng satin champagne.
- Viền gạch mảnh: bỏ outline ở từng mặt bevel, chỉ bake đường chia ô alpha nhẹ.
- Không đổi camera/layout/logic engine, solver hoặc kích thước logic block.
- Static board/material/shadow được cache theo màn/camera/bridge; animation chỉ
  cập nhật block/bóng tiếp xúc. UI cache độc lập. Input đệm tối đa một action.
- Solver dùng process riêng; replay và save/load đi qua engine hiện có.

## File chính

| File | Vai trò |
|---|---|
| `src/gui/renderer3d.py` | Geometry/bevel/material/shadow/cache |
| `src/gui/themes.py` | Palette/material theo theme và đổi theme |
| `src/gui/dreamscape.py` | Nền tĩnh và blueprint drafting |
| `src/gui/presentation.py` | Layout, menu, UI cache |
| `src/gui/app.py` | Input, phiên chơi, solver/replay |
| `src/gui/contracts.py` | Dữ liệu chung; thống nhất trước khi thay đổi |
| `scripts/capture_themes.py` | Script chụp chính thức duy nhất |
| `scripts/benchmark_gui.py` | Đo CPU hoặc cửa sổ thật |

## Screenshot và kiểm tra

Toàn bộ ảnh hiện hành nằm **trực tiếp** trong `docs/screenshots/`, không chia folder
theo theme. Xem [index 33 ảnh](screenshots/README.md): chơi, lăn, nằm, replay,
settings, cửa sổ nhỏ, chọn màn, chọn thuật toán, hướng dẫn, searching, solution.

```
python scripts/capture_themes.py
python -m pytest -q -p no:cacheprovider
python scripts/benchmark_gui.py --theme forest --live --output docs/performance.json
```

Test lưu ảnh kiểm tra vào thư mục tạm, không sinh ảnh rác trong repo.
Ảnh concept, before/after và screenshot trùng cũ đã xóa. Tài liệu và script thử
nghiệm được bảo toàn trong `docs/archive/`, `scripts/archive/`; không dùng chúng
làm entry point hoặc kỳ vọng các link ảnh lịch sử còn tồn tại.

## Việc còn lại

1. Sound hiện chỉ có beep tùy chọn, mặc định tắt; cần SFX lăn/thắng/UI và âm lượng.
2. Theme chưa lưu trong session/config; selector hiện bấm đổi vòng.
3. Forest cần biến thể texture theo tile và rêu tự nhiên hơn; giữ cơ chế bake.
4. Icon và typography còn có thể trau chuốt; chỉ đổi layout khi người dùng yêu cầu.
5. Đo mean/p95/max trên máy demo, map lớn, pan/zoom và trong lúc solver hoạt động.
   Chưa có phép đo RAM delta toàn tiến trình, VRAM hoặc input-to-photon.

Không sửa gameplay/thuật toán để giải quyết vấn đề trình bày. Giữ các asset dùng
lúc chạy trong `assets/`; UML/biểu đồ benchmark gốc của project không phải ảnh rác.
