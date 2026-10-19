> Latest graphics handoff (19 October 2026): [THEME_HANDOFF.md](THEME_HANDOFF.md). Includes three runnable themes, 15 actual screenshots, measurements and prioritized remaining work.

# Bàn giao GUI 3D

Phase 0–3 đã được nối vào app; danh sách phân công cũ được thay bằng bản này để tránh triển khai trùng.

## Chạy và kiểm tra

1. Chạy `python main_test.py` từ thư mục gốc.
2. Chạy `python -m pytest -q -p no:cacheprovider` để kiểm tra.
3. Xem `docs/gui_preview.png` và phần Editing the GUI trong README.

## Nếu hai người tiếp tục chỉnh sửa

1. Người A: renderer3d.py, animation.py và test geometry/hiển thị.
2. Người B: app.py, ui.py, replay.py, solver_gateway.py và test tích hợp.
3. Cùng thống nhất trước khi sửa contracts.py; dùng branch/worktree riêng.

## Giao tiếp đã triển khai

1. Renderer: set_stage, resize, draw trên surface riêng; nhận MotionFrame khi chuyển động.
2. Animation: start/update/reset; dt theo giây; không sửa trạng thái engine.
3. Gateway: submit/poll/cancel/close; request ID kiểm soát kết quả cũ, worker process dùng spawn.
4. Replay: load/play/pause/step/reset; app áp dụng Action qua GameSession và quản lý tốc độ, seek.
5. App cung cấp load_replay(start, path), save/load và chọn màn. Path được kiểm tra trước khi nạp; file save lỗi không thay phiên đang chơi.

## Quy tắc giữ nguyên

1. Chỉ main thread gọi Pygame; solver không gọi UI.
2. Không sửa luật hoặc thuật toán từ GUI. Undo đếm action để SPACE không bị trừ thành một lượt di chuyển.
3. Khi animation chạy không nhận bước mới; pause replay để animation hiện tại kết thúc. Stop cho phép chơi tiếp từ state đã nhận.
4. Restart/đổi màn vô hiệu hóa request cũ và reset animation/replay; thoát dọn worker.
5. Phase 4 chưa làm. Không có nhiệm vụ viết báo cáo đồ án hoặc quay demo trong phạm vi GUI này.
