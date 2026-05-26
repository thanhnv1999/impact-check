# Q&A — impact-check

Tập hợp các câu hỏi và câu trả lời trong quá trình tìm hiểu source code.

---

<!-- Các Q&A sẽ được thêm vào đây theo thứ tự thời gian -->

---

## Q1 — Tổng quan source code

**Q:** Đọc qua source và cho biết tổng quan về project.

**A:**

### impact-check

**Mục đích:** CLI tool phân tích tác động của code changes trước khi commit, dùng AI để đưa ra cảnh báo về các module bị ảnh hưởng, tests cần chạy, và rủi ro tiềm ẩn.

**Luồng hoạt động (4 bước):**
1. **Collect** — đọc staged changes từ `git diff --staged`
2. **Scan** — tìm file liên quan (imports, dependencies, test files)
3. **Analyze** — xây dựng prompt + gọi AI + parse JSON response
4. **Report** — hiển thị bảng kết quả bằng Rich

**AI Providers được hỗ trợ:** Claude (mặc định), GPT-4o, Gemini, Grok, Ollama

**Tech stack:** Python, Click (CLI), Rich (UI), python-dotenv, các AI SDK

**Cấu trúc chính:**
- `impact_check/cli.py` — entry point, điều phối 4 bước
- `impact_check/git_collector.py` — đọc git data (staged files, diffs, content)
- `impact_check/context_finder.py` — phân tích imports/dependencies, tìm test files
- `impact_check/analyzer.py` — xây dựng prompt, gọi AI, parse JSON response
- `impact_check/reporter.py` — hiển thị bảng kết quả (Rich)
- `impact_check/providers/` — các AI provider (claude, openai_compat, gemini)

**Dependency Detection:** 3 layer — (1) import graph regex cho 10+ ngôn ngữ (Python, JS, TS, JSX, TSX, Vue, Java, C#, Go, PHP, HTML), (2) symbol grep cho auto-import và barrel file, (3) framework scanner cho Vue template / React JSX / Angular templateUrl. Hỗ trợ transitive dependencies 2 cấp.

**Giới hạn hiệu năng:**
- Tối đa 1000 files quét per project
- Tối đa 12 related files per changed file
- File size limit: 200 KB
- Content truncation: 25 KB per file trong prompt

---

## Q2 — Cấu trúc thư mục hiện tại

**Q:** Cấu trúc thư mục hiện tại thế nào?

**A:**

```
d:\tool\
├── impact_check\                   # Main package
│   ├── __init__.py
│   ├── cli.py                      # Entry point & orchestrator
│   ├── git_collector.py            # Đọc staged changes từ git
│   ├── context_finder.py           # Quét dependencies & test files
│   ├── analyzer.py                 # Build prompt + gọi AI + parse JSON
│   ├── reporter.py                 # Hiển thị kết quả (Rich)
│   ├── debug.py                    # Ghi log file
│   └── providers\                  # AI provider implementations
│       ├── __init__.py
│       ├── base.py                 # Abstract interface
│       ├── factory.py              # Lazy-load provider theo tên
│       ├── claude.py               # Anthropic Claude
│       ├── openai_compat.py        # GPT / Grok / Ollama
│       └── gemini.py               # Google Gemini
│
├── pyproject.toml                  # Package config & dependencies
├── ARCHITECTURE.md                 # Tài liệu kiến trúc
├── README.md                       # Hướng dẫn cài đặt & sử dụng
├── QA.md                           # File Q&A
│
├── impact_check.log                # Log file (sinh ra khi chạy)
└── impact_check.egg-info\          # Package metadata (sinh ra khi pip install)
```

Tổng cộng **11 file Python** chính, chia làm 2 tầng: package gốc (`impact_check/`) và sub-package providers (`providers/`).

---

## Q3 — `__pycache__`, `impact_check.egg-info` và `pyproject.toml`

**Q:** Các folder `__pycache__` và `impact_check.egg-info` tự sinh ra? `pyproject.toml` để làm gì? Vòng đời của chúng?

**A:**

### `__pycache__/`
Sinh ra bởi Python interpreter lần đầu chạy code. Chứa file `.pyc` (bytecode đã compile) để lần sau import nhanh hơn. Xóa đi Python tự tạo lại, không ảnh hưởng gì.

### `impact_check.egg-info/`
Sinh ra khi chạy `pip install -e .`. Chứa metadata của package (tên, version, dependencies, entry points). Cờ `-e` là **editable** — pip không copy code đi chỗ khác mà trỏ thẳng vào thư mục `d:\tool`, nên sửa code có hiệu lực ngay, không cần cài lại.

### `pyproject.toml`
File khai báo package — tờ hướng dẫn cho `pip`. Định nghĩa 3 thứ:

1. **Metadata:** tên, version, yêu cầu Python version
2. **Dependencies:** bắt buộc (`click`, `rich`, `python-dotenv`) + tùy chọn theo provider
3. **CLI entry point:** `impact-check = "impact_check.cli:main"` → pip tạo executable để gõ lệnh trên terminal

```bash
pip install -e .[claude]   # chỉ cài anthropic SDK
pip install -e .[gemini]   # chỉ cài google-genai SDK
pip install -e .[all]      # cài tất cả
```

### Vòng đời:

```
pyproject.toml          ← bạn viết, commit vào git
     ↓ pip install -e .
impact_check.egg-info/  ← tự sinh, KHÔNG commit git
     ↓
impact-check (command)  ← dùng được trên terminal bất kỳ đâu
```

---

## Q4 — Cách cài đặt cho người mới

**Q:** Người mới cài đặt thì chạy `pip install -e "d:\tool"` trước rồi mới chạy `pip install -e .[gemini]` à?

**A:**

Không cần 2 bước, gộp lại 1 lệnh luôn:

```bash
# Nếu đang đứng trong thư mục d:\tool
pip install -e .[gemini]

# Hoặc từ bất kỳ đâu
pip install -e "d:\tool[gemini]"
```

Dấu `[gemini]` chỉ là thêm optional dependencies vào cùng lúc cài, không phải bước riêng.

**Tóm tắt cho người mới:**

```bash
# Bước 1: cd vào thư mục source
cd d:\tool

# Bước 2: cài tool + provider mình muốn dùng (1 lệnh)
pip install -e .[claude]    # nếu dùng Claude
pip install -e .[gemini]    # nếu dùng Gemini
pip install -e .[all]       # nếu muốn dùng tất cả

# Bước 3: dùng ngay
impact-check -p gemini
```

---

## Q5 — Luồng hoạt động chi tiết

**Q:** Luồng hoạt động chi tiết của tool thế nào — mới đầu vào gọi class nào, method nào, mục đích gì, gọi tiếp đến đâu?

**A:**

### Bước 0 — Setup (trước khi làm gì)
```
main()
  ├─ _load_dotenv()         → tìm .env từ cwd lên git root, fallback d:\tool\.env
  └─ get_provider("gemini") → factory.py lazy-load GeminiProvider
        GeminiProvider.__init__()
          → đọc GEMINI_API_KEY từ os.environ
          → khởi tạo google.genai client
```

### Bước 1 — Collect (thu thập git data)
```
git_collector.get_staged_changes(root)
  ├─ _run("git rev-parse --abbrev-ref HEAD")   → branch name
  ├─ _run("git diff --staged --name-status")   → danh sách file thay đổi
  └─ _parse_files()
        for mỗi file:
          ├─ _run("git diff --staged -- file")  → lấy diff
          ├─ _run("git show :file")             → lấy full content
          └─ ChangedFile(path, status, diff, content)
  → return GitChanges(files=[...], branch="main")
```

### Bước 2 — Scan (tìm dependencies)
```
context_finder.find_related_files(changed_paths, root, deleted_contents)
  ├─ _get_graph()              → trả về cached graph (scan 1 lần per root)
  │    └─ _build_import_graph() → scan tối đa 1000 files, regex theo extension
  │
  │   [inject deleted file content vào local graph nếu có]
  │
  ├─ Layer 1: _find_importers()       → direct + transitive (1 cấp)
  ├─ Layer 2: _find_symbol_users()    → symbol grep (auto-import, barrel file)
  └─ Layer 3: _FRAMEWORK_SCANNERS
       ├─ _find_vue_template_users()       → nếu .vue, tìm <ComponentName> trong .vue khác
       ├─ _find_jsx_template_users()       → nếu .jsx/.tsx, tìm <ComponentName> trong .jsx/.tsx
       └─ _find_angular_template_owners()  → nếu .html/.scss/.css, tìm @Component .ts khai báo templateUrl/styleUrls

context_finder.find_test_files()   → tìm file trong TEST_DIRS hoặc tên "test_", ".spec."
context_finder.get_project_structure()  → chuỗi tree max depth 3
```

### Bước 3 — Analyze (gọi AI)
```
analyzer.analyze(changes, related, structure, provider, test_files)
  ├─ _build_prompt()      → ghép thành 1 prompt lớn (branch + tree + diffs + related + tests)
  ├─ provider.complete()  → gọi Gemini/Claude/GPT API → nhận JSON raw
  └─ _parse_response()
        thử json.loads() thẳng
        → strip markdown fence ``` rồi thử lại
        → tìm {...} trong text rồi thử lại
        → fallback: dict rỗng + raw text làm summary
```

### Bước 4 — Report (hiển thị kết quả)
```
reporter.print_report(analysis, changes)
  ├─ Panel "IMPACT ANALYSIS REPORT"
  ├─ in summary
  ├─ _print_affected_modules()  → bảng Mức độ | Module bị ảnh hưởng | Lý do
  ├─ _print_tests()             → bảng Ưu tiên | Loại | Mô tả
  └─ _print_risks()             → bảng Mức độ | Vị trí | Mô tả
       _sort_by_severity()      → HIGH trước, MED sau, LOW cuối
```

### Toàn bộ luồng gọn lại
```
impact-check -p gemini
      ↓
main() ──→ _load_dotenv() + GeminiProvider.__init__()
      ↓
[step 1]  git_collector.get_staged_changes()   → GitChanges
      ↓
[step 2]  context_finder.find_related_files()  → related dict
          context_finder.find_test_files()     → test list
          context_finder.get_project_structure() → tree string
      ↓
[step 3]  analyzer._build_prompt()  → prompt text
          provider.complete()       → gọi AI API
          analyzer._parse_response() → dict JSON
      ↓
[step 4]  reporter.print_report()   → Rich tables ra terminal
```

---

## Q6 — Giải thích chi tiết các config giới hạn

**Q1: `MAX_RELATED_CONTENT` và `MAX_RELATED_CONTENT_IN_PROMPT` khác nhau thế nào?**

Hai biến kiểm soát 2 điểm cắt khác nhau:

- `context_finder.py`: `MAX_RELATED_CONTENT = 25000` — giới hạn content lưu trong graph (dùng khi đưa vào result dict)
- `analyzer.py`: `MAX_RELATED_CONTENT_IN_PROMPT = 25000` — giới hạn content khi ghép vào prompt gửi AI

Hiện tại cả hai đều là 25000 nên hiệu quả bằng nhau — không bị cắt thêm ở bước nào. Nếu muốn lưu graph đầy đủ hơn nhưng gửi AI ít hơn thì có thể tăng `MAX_RELATED_CONTENT` và giảm `MAX_RELATED_CONTENT_IN_PROMPT`.

---

**Q2: `MAX_FILE_SIZE` tính theo KB từ text? Nếu file đang sửa nặng 300KB thì bị bỏ qua?**

`MAX_FILE_SIZE` tính theo **byte thực của file trên ổ đĩa** (dùng `os.path.getsize()`), không đếm chữ.

Quan trọng: `MAX_FILE_SIZE` chỉ ảnh hưởng đến bước tìm **related files**, không ảnh hưởng file đang sửa vì file đang sửa đi qua `git_collector` (đường riêng).

```
File A (300KB) — bạn đang sửa   → VẪN được đọc, vẫn vào prompt
File B (300KB) — import file A  → BỊ BỎ QUA, không xuất hiện là related file
```

---

**Q3: `MAX_FILES_TO_SCAN = 1000` đủ chưa cho một project thực tế?**

Tùy loại project:

| Loại project | Số file thực tế | 1000 có đủ? |
|---|---|---|
| Tool nhỏ, script | < 100 file | Dư thừa |
| Web app trung bình | 500–2000 file | Có thể thiếu |
| Monorepo lớn | 10,000+ file | Thiếu nhiều |

Thực tế `node_modules`, `__pycache__`, `dist`... đã bị skip bởi `SKIP_DIRS` nên số file quét thực tế ít hơn. Với project thông thường 1000 tạm đủ, nhưng không đảm bảo file quan trọng không nằm ở cuối danh sách bị cắt.

---

**Q4: `diff = 3000` là ký tự hay từ khóa?**

**Ký tự** — Python `len(string)` đếm từng ký tự một, kể cả dấu cách và xuống dòng.

```python
f.diff[:3000]  # lấy 3000 ký tự đầu tiên của chuỗi diff
```

Diff là phần ghi lại những dòng thay đổi trong git:
```diff
- old_function(a, b):     ← dòng bị xóa
+ new_function(a, b, c):  ← dòng được thêm
```

3000 ký tự ≈ 60–80 dòng code. Commit nhỏ thì đủ, commit lớn (refactor, thêm feature) thì bị cắt giữa chừng — AI không thấy hết phần thay đổi.
