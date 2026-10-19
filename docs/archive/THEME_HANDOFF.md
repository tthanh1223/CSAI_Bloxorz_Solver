# Bàn giao đồ họa Bloxorz — 19/10/2026

> Cập nhật mới nhất: block dùng champagne/brushed brass. Theo yêu cầu xem thử,
> viền block và đường chia gạch của Dream City/Paper dùng đen than `(48,47,48)`.
> Bộ 9 ảnh tương tác của một theme nằm trong [CHARCOAL_REVIEW.md](CHARCOAL_REVIEW.md).
> Đừng tự đưa viền về gần màu khối khi tiếp tục chỉnh material.

## Xem ba bản đã chạy được

```
python main_test.py
python main_test.py --theme blueprint
python main_test.py --theme forest
```

Dream City mặc định. Bấm tên theme cạnh logo để đổi vòng Dream → Blueprint → Forest
mà không reset game. Windows có `run_blueprint.cmd` và `run_forest.cmd`.
Hai theme mới dùng Pygame cache, không cần ModernGL hay dependency mới.
`python main_test.py --forest` vẫn là bản OpenGL thử nghiệm cũ, khác với
`--theme forest`; không lấy bản OpenGL cũ làm baseline hoàn thiện tiếp.

## Đã làm — không cần dựng lại

- Ba theme dùng cùng renderer, engine state, replay và solver process.
- Bàn/block/goal là geometry chiếu isometric thật theo state; nền không chứa bàn.
- Bevel dùng topology 26 mặt cache; đã sửa winding để mép block không bị hở.
- Bàn, vật liệu, bóng đảo, goal và marker được bake/cache theo màn/camera/bridge.
  Khi lăn chỉ cập nhật block và vùng bóng nhỏ. UI tĩnh không vẽ lại khi idle.
- Dream: nền kiến trúc hồng, terrazzo, khối cam, panel kem.
- Blueprint: giấy navy có grain, đường dựng isometric đứt nét, sơ đồ top-view theo
  màn đang chơi, cardstock ngà, khối cam. Đường dựng được giới hạn khỏi panel.
- Forest: ảnh nền rừng, atlas đá/vàng, rêu bake ở mép lộ ra, goal trang trí,
  panel xanh tối. Ánh sáng/sương nền nằm trong ảnh tĩnh, không phải volumetrics.
- Buffer tối đa một phím trong animation thủ công. Restart/đổi màn/menu xóa buffer.
  Replay không nhận input thủ công. Không sửa luật hoặc thuật toán solver.

## File cần đọc

| File | Trách nhiệm |
|---|---|
| `src/gui/themes.py` | Palette, selector và invalidation khi đổi theme |
| `src/gui/dreamscape.py` | Background; grain/grid/top-view của Blueprint |
| `src/gui/renderer3d.py` | Geometry/bevel, material, rêu, shadow, cache |
| `src/gui/presentation.py` | Layout, panel, UI cache và nút đổi theme |
| `src/gui/app.py` | Điều phối/input/solver/replay |
| `scripts/capture_themes.py` | Chụp cửa sổ thật, dùng solver worker thật |
| `scripts/benchmark_gui.py` | Đo CPU hoặc cửa sổ thật, có `--theme`, `--live` |

Asset mới `assets/forest_ruins_background.png` và `assets/forest_materials.png`
được tạo bằng OpenAI imagegen cho project. Dream dùng asset đã tạo trước đó.
Blueprint dựng nền bằng code. Không tải asset từ website bên thứ ba; không cần
mạng khi chạy game. Attribution được ghi ở `assets/ATTRIBUTION.md`.

## Ảnh chụp thực tế

`docs/screenshots/themes/` có **15 ảnh**. Mỗi theme (`dream`, `blueprint`, `forest`):

- `{theme}_01_play.png`: chơi tại 1180 × 800.
- `{theme}_02_roll.png`: giữa animation lăn.
- `{theme}_03_replay.png`: replay đường giải do worker thật tìm ra.
- `{theme}_04_settings.png`: settings.
- `{theme}_05_compact.png`: cửa sổ 960 × 720.

Đây là framebuffer cửa sổ Pygame, không phải concept hoặc background ghép bàn giả.
54 test pass, gồm state khi đổi theme, so pixel cache/full UI, winding bevel,
bridge mask, split và buffered input. Script capture cũng đã hoàn tất cả 15 ảnh.

## Việc tiếp theo theo ưu tiên

### P1 — đối chiếu concept và sửa năm sai khác lớn của từng theme

**Forest Ruins**

1. Texture đá đang lặp giống nhau trên mọi ô: tạo 4–8 biến thể có seed ổn định
   theo tile, bake một lần khi đổi màn, không tạo texture mỗi frame.
2. Rêu còn là cụm chấm/đường đơn giản: thay bằng sprite cụm lá/rễ nhỏ; giữ ở mép
   lộ ra, không che switch, goal hoặc mặt chơi. Không thêm particle.
3. Đá còn mịn/đều hơn mẫu: thêm crack, cạnh mòn và baked AO có chủ đích. Kiểm tra
   độ tương phản mặt trên/mặt bên ở kích thước ảnh chạy thật.
4. Hướng sáng và contact shadow chưa hòa với nền như concept. Đồng bộ art direction
   bằng baked shading; không dùng hiệu ứng realtime nặng để bù.
5. Viền goal còn đơn giản: làm cảm giác khắc đá, kiểm tra bóng không lấp hố.

**Paper Blueprint**

1. Chỉnh tỷ lệ camera/bàn và khoảng trống để giống bố cục ảnh mẫu hơn.
2. Chuẩn hóa line weight/dash/độ mờ đường dựng. Thêm icon khối dây và chú thích
   isometric đúng phối cảnh; sơ đồ top-view phải tiếp tục lấy từ màn thật.
3. Cardstock cần mặt cắt và vân giấy tinh tế hơn, tránh grain quá đều. Dùng atlas
   hoặc baked detail nhẹ, không tăng polygon hàng loạt.
4. Thay nút Undo/Restart/Hint hiện còn chữ bằng bộ icon mảnh + nhãn đồng bộ mẫu.
5. Căn lại typography, tracking, header và khoảng cách panel. Không kết luận đã
   khớp chỉ vì nền navy + ô trắng + block cam.

**Dream City** giữ làm đối chứng. Nền vẫn khác cảnh mẫu; terrazzo lặp và vật liệu
block/cạnh còn đơn giản. Đừng làm mất các tối ưu cache khi trau chuốt lại.

### P2 — UI/cấu hình

- Lưu theme vào cấu hình hoặc session; hiện mới chọn qua CLI/nút đổi vòng.
- Nếu cần dễ tìm hơn, đổi selector thành menu có tên/thumbnail.
- Palette đang ở cấp module, phù hợp một cửa sổ. Nếu thêm multi-window, chuyển
  palette thành dữ liệu theo app để tránh các cửa sổ ảnh hưởng nhau.
- Đồng bộ icon settings, toast/footer và font fallback. Rà soát large text và
  960 × 720 sau khi đổi layout/icon.

### P3 — xác nhận trên máy demo

Kết quả CPU 1180 × 800 sau warm-up, chưa gồm xuất hình:

| Theme | Mean | p95 | Primitive Python/frame |
|---|---:|---:|---:|
| Blueprint | 8.024 ms | 8.951 ms | 27.0 |
| Forest Pygame | 14.965 ms | 19.752 ms | 27.0 |

Raw JSON: `docs/performance_blueprint.json`, `docs/performance_forest_pygame.json`.
Đây là SDL dummy, **không chứng minh 60 FPS ổn định**. Dream có báo cáo live riêng
trong `docs/DREAM_CITY_PERFORMANCE.md`. Renderer cache trong kịch bản mới khoảng
8.5 MiB/theme; nền và UI còn có bộ nhớ riêng. Chưa đo delta RAM toàn tiến trình,
VRAM hoặc input-to-photon. GPU draw calls không có trong pipeline Surface;
số primitive không bao gồm blit.

Đo trên máy demo cả map lớn, split, cầu, zoom/pan liên tục và lúc solver chạy.
Tách cold bake khỏi frame time animation warm; không trộn hai số. Chỉ thêm
Low/Medium/High nếu phép đo cho thấy cần; giữ camera/silhouette/art direction.

```
python scripts/benchmark_gui.py --theme blueprint --live --output docs/blueprint_demo.json
python scripts/benchmark_gui.py --theme forest --live --output docs/forest_demo.json
python -m pytest -q -p no:cacheprovider
python scripts/capture_themes.py
```

## Điều kiện nghiệm thu lượt tiếp theo

- Chụp ba theme cùng màn/camera tại 1180 × 800 và 960 × 720.
- Nêu năm sai khác lớn nhất với concept, sửa theo thứ tự rồi chụp lại.
- Không sửa engine/solver, không thêm network runtime hoặc asset ngoài repo.
- Test cache, switch theme, bridge/split và bevel phải pass.
- Báo mean/p95/max trên máy thật, không chỉ FPS trung bình.
- Đổi engine là quyết định kiến trúc riêng, không thay bản Pygame ngầm định.
