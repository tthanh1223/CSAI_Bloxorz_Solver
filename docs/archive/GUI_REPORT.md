> Latest graphics handoff (19 October 2026): [THEME_HANDOFF.md](THEME_HANDOFF.md). Includes three runnable themes, 15 actual screenshots, measurements and prioritized remaining work.

# GUI 3D — Trạng thái triển khai

Đã triển khai phase 0–3 theo phạm vi GUI đã chốt, dùng lại engine và solver hiện có.

## Phase 0: GUI 3D

1. Renderer isometric, camera tự căn, khối và ký hiệu ô đặc biệt.
2. Nút New Game/Stage, Restart, chọn tất cả màn trong levels.
3. Nối chơi tay, undo và đếm bước vào giao diện mới.

## Phase 1: Solver

1. Gọi BFS/IDS/UCS/A* bằng process riêng, không chặn vòng lặp GUI.
2. Hiển thị kết quả, path, thời gian, bộ nhớ, node, số bước và chi phí.
3. Hủy/timeout 30 giây, bỏ kết quả cũ khi restart/đổi màn, dọn worker khi thoát.

## Phase 2: Kiểm tra GUI

1. Kiểm tra geometry xoay khối, split, input, resize, replay, save/load và kết quả cũ.
2. Kiểm tra cả bốn solver bằng worker thật và replay tới đích.
3. Render toàn bộ màn; ảnh giao diện: `gui_preview.png`. Test hiện tại: 40 passed.

## Phase 3: Tính năng thêm

1. Animation; replay Play/Pause/Step/Back, tốc độ và tua bằng timeline.
2. Hint, giải từ hiện trạng/đầu màn; lưu/nạp phiên chơi và replay tại một slot local.
3. Zoom/kéo/reset camera, âm thanh tùy chọn, contrast và cỡ chữ.

Cách chạy/chỉnh code xem README. Đây là 3D isometric bằng polygon Pygame, không phải camera 3D xoay tự do. Engine vẫn chặn bước không hợp lệ; không thêm luật thua/rơi. Phase 4 (so sánh thuật toán trong GUI, trực quan tìm kiếm, sửa map) chưa triển khai.
