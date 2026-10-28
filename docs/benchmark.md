# Benchmark các Solver Bloxorz

Tài liệu này mô tả cách chạy thực nghiệm (benchmark) để so sánh 4 thuật toán tìm kiếm **BFS**, **DFS (IDS)**, **UCS** và **A\***, phục vụ phần **Experiments** trong report.

Code nằm ở `src/solvers/benchmark.py`.

---

## 1. Cách chạy

Chạy từ **thư mục gốc của project** (thư mục chứa `src/` và `levels/`), sau khi đã kích hoạt môi trường ảo:

```bash
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\Activate.ps1       # Windows PowerShell

python -m src.solvers.benchmark
```

Các tùy chọn:

| Lệnh | Ý nghĩa |
|---|---|
| `python -m src.solvers.benchmark` | Chạy toàn bộ bộ test, ghi CSV và vẽ biểu đồ |
| `python -m src.solvers.benchmark --time-limit 30` | Giới hạn mỗi lần chạy 30 giây (mặc định 60 giây) |
| `python -m src.solvers.benchmark --plot-only` | Không chạy lại, chỉ vẽ lại biểu đồ từ CSV có sẵn |

Thời gian chạy toàn bộ: khoảng **3–5 phút**, phần lớn do IDS.

Thư viện cần có: `matplotlib` (đã có trong `requirements.txt`).

---

## 2. Bộ test cố định

Đề yêu cầu dùng **một bộ test cố định cho mọi thuật toán** để so sánh công bằng, và chia nhóm theo độ khó. Bộ test gồm **15 màn, chia 5 nhóm**:

| Nhóm | Màn | Đặc điểm |
|---|---|---|
| **G1 – Basic** | 01, 03, 06 | Chỉ có floor, void, goal |
| **G2 – Fragile** | 04, 13 | Có ô fragile (không được đứng lên) |
| **G3 – Switches & Bridges** | 02, 07, 05, 11 | Soft switch, heavy switch, bridge |
| **G4 – Split block** | 08, 09, 16 | Có split switch: tách khối, teleport, nhập khối |
| **G5 – Combined** | 27, 30, 28 | Kết hợp fragile + switch (+ split) |

Muốn thay đổi bộ test, sửa dict `TEST_SUITE` ở đầu file `benchmark.py`.

---

## 3. Các chỉ số đo

Mỗi cặp (màn, thuật toán) được đo 4 chỉ số theo yêu cầu của đề, cộng thêm tổng chi phí:

| Chỉ số | Cột trong CSV | Cách đo |
|---|---|---|
| **Search time** | `time_sec` | `time.perf_counter()` trước và sau khi tìm kiếm (giây) |
| **Peak memory** | `peak_memory_mb` | Bộ nhớ đỉnh đo bằng `tracemalloc` (MB) |
| **Expanded nodes** | `expanded_nodes` | Số node được lấy ra khỏi frontier và mở rộng |
| **Solution length** | `solution_length` | Số action trong lời giải (kể cả `SPACE`) |
| Total cost | `total_cost` | Tổng chi phí của lời giải theo cost function của thuật toán |

Cột `status` cho biết kết quả: `solved` (tìm thấy), `no_solution` (không có lời giải), `timeout` (quá thời gian), `error` (lỗi khi chạy).

---

## 4. Cách hoạt động

1. Với mỗi màn trong `TEST_SUITE` và mỗi thuật toán, benchmark load màn từ `levels/stage_XX.json`, tạo `BloxorzProblem` với trạng thái đầu là khối **đứng** ở ô start.
2. Mỗi lần chạy được thực hiện trong **một process riêng** (dùng `multiprocessing` với chế độ `spawn`), vì hai lý do:
   - **Giới hạn thời gian:** nếu chạy quá `--time-limit` giây, process bị dừng và kết quả ghi là `timeout`. Không có cơ chế này, IDS có thể làm treo cả benchmark.
   - **Đo bộ nhớ độc lập:** `tracemalloc` đo trong một process sạch, không bị ảnh hưởng bởi bộ nhớ của lần chạy trước.
3. Kết quả từng lần chạy được in ra terminal và ghi vào CSV.
4. Cuối cùng vẽ 4 biểu đồ cột nhóm từ CSV.

---

## 5. Kết quả đầu ra

Tất cả nằm trong thư mục `data/` (tự tạo nếu chưa có):

| File | Nội dung |
|---|---|
| `benchmark_results.csv` | Bảng số liệu đầy đủ, mỗi dòng là một (màn, thuật toán) |
| `chart_time.png` | Search time, thang log |
| `chart_memory.png` | Peak memory, thang log |
| `chart_expanded.png` | Expanded nodes, thang log |
| `chart_length.png` | Solution length, thang thường |

Trong biểu đồ, mỗi màn là một nhóm cột, mỗi thuật toán một màu cố định: **BFS** xanh dương, **DFS (IDS)** cam, **UCS** xanh lá, **A\*** vàng. Lần chạy bị timeout được ghi chữ `timeout` thay cho cột.

Time, memory và expanded nodes dùng **thang log** vì IDS lớn hơn các thuật toán khác hàng trăm lần; dùng thang thường thì các cột còn lại sẽ quá thấp, không so sánh được.

---

## 6. Lưu ý khi đọc kết quả

- **Cost function khác nhau giữa các thuật toán.** BFS, DFS (IDS) và A\* dùng **unit cost** (mỗi action tốn 1). UCS dùng cost riêng: lăn thường = 1, lăn lên ô fragile = 3, lăn làm đổi trạng thái cầu = 2, `SPACE` = 0. Vì vậy **không so sánh trực tiếp cột `total_cost` của UCS với các thuật toán khác**.
- **UCS có thể cho lời giải dài hơn BFS nhưng rẻ hơn** (ví dụ né ô fragile). Đây là hành vi đúng: UCS tối ưu theo **cost**, không theo **số bước**.
- **Thời gian phụ thuộc phần cứng**, còn expanded nodes và solution length thì không. Khi đưa vào report, cần ghi rõ cấu hình máy chạy thực nghiệm (CPU, RAM, phiên bản Python).
- **IDS dễ bị timeout** ở màn có lời giải dài, vì mỗi vòng lặp phải duyệt lại từ đầu. Nếu muốn có số liệu IDS cho các màn này, tăng `--time-limit`.