# Kiến trúc và luồng hoạt động — impact-check

## Cấu trúc thư mục

```
d:\tool\
│
├── impact_check\               # Package chính
│   │
│   ├── cli.py                  # Điểm vào của tool (entry point)
│   ├── git_collector.py        # Thu thập dữ liệu thay đổi từ git
│   ├── context_finder.py       # Quét project tìm file liên quan
│   ├── analyzer.py             # Xây dựng prompt và gọi AI
│   ├── reporter.py             # Hiển thị kết quả ra terminal
│   ├── html_reporter.py        # Xuất báo cáo HTML dark-theme
│   ├── guard.py                # Secret scanner cho pre-commit hook
│   ├── debug.py                # Ghi log ra file impact_check.log
│   │
│   └── providers\              # Các AI provider
│       ├── base.py             # Interface chung (abstract class)
│       ├── factory.py          # Khởi tạo provider theo tên
│       ├── claude.py           # Anthropic Claude
│       ├── openai_compat.py    # GPT / Grok / Ollama (cùng API format)
│       └── gemini.py           # Google Gemini
│
├── pyproject.toml              # Cấu hình package, dependencies
├── README.md                   # Hướng dẫn cài đặt và sử dụng
├── ARCHITECTURE.md             # File này
└── .env                        # API keys (không commit lên git)
```

---

## Mục đích từng file

### `cli.py` — Điểm vào

Nơi người dùng tương tác. Đọc tham số từ lệnh, điều phối toàn bộ luồng từ bước 1 đến bước 4. Không chứa business logic, chỉ gọi các module khác theo thứ tự.

Lệnh hỗ trợ:
- `impact-check` — chạy phân tích AI
- `impact-check -p gemini` — chọn provider (claude/gemini/gpt/grok/ollama)
- `impact-check -o tree` — hiển thị Risk Heatmap dạng cây + bảng
- `impact-check -o json` — output JSON thô
- `impact-check --save-html report.html` — lưu báo cáo HTML
- `impact-check --save-json result.json` — lưu kết quả JSON
- `impact-check --dry-run` — thu thập dữ liệu + ghi log, không gọi AI
- `impact-check install` — cài pre-commit hook chạy AI analysis
- `impact-check install --guard` — cài pre-commit hook quét secret
- `impact-check guard` — chạy secret scanner thủ công

---

### `git_collector.py` — Thu thập thay đổi

Gọi lệnh `git` qua `subprocess` để lấy:
- Danh sách file đã `git add` (staged)
- Nội dung diff của từng file
- Toàn bộ nội dung hiện tại của từng file
- Tên branch đang làm việc

Trả về object `GitChanges` chứa danh sách `ChangedFile`.

---

### `context_finder.py` — Tìm file liên quan

Quét toàn bộ project (tối đa 1000 file) một lần duy nhất, kết quả được cache theo `project_root`. Trả về direct importers + 1 cấp transitive.

**Layer 1 — Import graph:**
- Regex theo extension tìm `import`, `require`, `from ... import`, `templateUrl`, `<script src>`, Jinja/EJS include
- Hỗ trợ: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.vue`, `.java`, `.cs`, `.go`, `.php`, `.html`, `.htm`
- Barrel file (`index.ts`, `__init__.py`) được resolve qua tên thư mục cha
- Python multi-level relative import (`from ..utils import X`) được resolve đúng path
- Java/C# dotted import (`com.app.UserService`) được bắt qua fallback `split(".")[-1]`

**Layer 2 — Symbol grep:**
- Trích xuất tên exported symbol từ file thay đổi (`export const/function/class`, `export { }`, `export default as`)
- Grep symbol đó trong toàn project (chỉ cùng nhóm ngôn ngữ để tránh false positive)
- Bắt được Nuxt auto-import, re-export qua barrel file, usage không có explicit import statement

**Layer 3 — Framework scanners:**
- **Vue**: tìm file `.vue` nào dùng `<ComponentName>` hoặc `<component-name>` trong template
- **React**: tìm file `.jsx/.tsx` nào render `<ComponentName>` trong JSX
- **Angular**: khi `.html/.scss/.css` thay đổi, tìm `@Component` `.ts` nào khai báo `templateUrl` hoặc `styleUrls` trỏ đến file đó

**Deleted file support:**
- File bị xóa: nội dung được lấy từ `git show HEAD:{path}` → inject vào local graph copy để Layer 2 vẫn tìm được importer

**File test liên quan:**
- Tìm file có tên chứa `test_`, `_test`, `.spec.`, `.test.`
- Hoặc nằm trong thư mục `tests/`, `test/`, `__tests__/`
- Khớp theo stem với file thay đổi

Thư mục bỏ qua: `.git`, `node_modules`, `__pycache__`, `.nuxt`, `.next`, `dist`, `build`...

---

### `analyzer.py` — Xây dựng prompt và gọi AI

Nhận toàn bộ dữ liệu đã thu thập, đóng gói thành prompt gửi AI:

**Nội dung prompt bao gồm:**
1. Cây thư mục project (3 cấp)
2. Nội dung đầy đủ của từng file thay đổi + git diff
3. Nội dung của các file liên quan (direct và indirect), tối đa 12 file
4. Nội dung của các file test tìm được, tối đa 5 file
5. Marker `... (truncated)` khi file bị cắt — AI biết nội dung còn tiếp

**Yêu cầu AI trả về JSON với 4 trường:**
- `affected_modules` — chỉ downstream consumers (không phải file đang thay đổi), mức độ HIGH/MED/LOW
- `tests_needed` — test cần chạy lại hoặc bổ sung
- `risks` — rủi ro tiềm ẩn, chỉ rõ file và tên hàm cụ thể, đánh giá theo threat model thực tế
- `summary` — tóm tắt 2-3 câu

**Parse response:**
- Try 1: `json.loads()` thẳng
- Try 2: strip markdown fence ``` rồi thử lại
- Try 3: tìm `{...}` trong text rồi thử lại
- Try 4: `_repair_json_strings()` — sửa literal newline trong string value (Gemini hay trả về)
- Fallback: dict rỗng + raw text làm summary

**Trim context theo provider:**
- Ưu tiên giữ direct files, cắt indirect trước
- Cắt tỉ lệ đều khi tổng vượt `safe_chars`

---

### `reporter.py` — Hiển thị kết quả

Dùng thư viện `rich` để in ra terminal:
- Spinner có đồng hồ đếm thời gian cho từng bước
- `print_risk_tree()` — Risk Heatmap dạng cây với màu 🔴🟡🟢 theo severity
- Bảng **Module bị ảnh hưởng**, **Cần test**, **Rủi ro** — màu theo severity
- HIGH = đỏ, MED = vàng, LOW = xanh lá
- Các mục được sắp xếp từ HIGH xuống LOW
- `collect_diff_warnings()` — thu thập cảnh báo truncation dùng chung cho terminal và HTML

---

### `html_reporter.py` — Báo cáo HTML

Sinh file HTML self-contained (không cần internet) khi dùng `--save-html`:
- Dark-theme, stat cards (HIGH/MED/risks/tests)
- Alert bar đỏ khi có HIGH risk, liệt kê location cụ thể
- Section ẩn khi rỗng (không chiếm chỗ vô ích)
- Row highlight theo severity, badge màu
- Section cảnh báo màu amber khi context bị cắt (scan cap, truncation)

---

### `guard.py` — Secret Scanner

Quét staged files tìm API key, password, token bị hardcode. Chạy hoàn toàn local, không cần network, không cần AI. Được dùng bởi `impact-check guard` và pre-commit hook `install --guard`.

**9 HIGH patterns** (block commit): Anthropic, OpenAI, Gemini, Grok, AWS, Private Key, GitHub, Stripe, Slack

**5 MED patterns** (warn, commit vẫn qua): password/PASS, secret/api_key, token, private_key variable, YAML credential không quotes

**Xử lý thông minh:**
- Comment lines → skip MED, giữ HIGH (key thật trong comment vẫn nguy hiểm)
- `# noguard` trên dòng → bỏ qua dòng đó hoàn toàn
- YAML template `{{ }}`, `${}` → không flag
- `.env` và variants (`.env.local`, `.env.production`) → HIGH khi stage nhầm
- Lock files, binary → bỏ qua tự động

---

### `debug.py` — Ghi log

Mỗi lần chạy, ghi file `impact_check.log` tại thư mục project gồm:
- Files thay đổi và trạng thái (Added/Modified/Deleted)
- Files liên quan tìm được (direct và indirect)
- Files test tìm được
- System prompt gửi cho AI
- User prompt đầy đủ gửi cho AI (toàn bộ nội dung file)

Dùng để kiểm tra tool đang đọc đúng file chưa và prompt có đủ context chưa.

---

### `providers/` — Kết nối AI

Theo pattern **Strategy**: mỗi provider implement interface `BaseProvider` với 1 method duy nhất `complete(system, prompt) -> str`.

| File | Provider | Model mặc định | API key |
|---|---|---|---|
| `claude.py` | Anthropic | claude-sonnet-4-6 | `ANTHROPIC_API_KEY` |
| `openai_compat.py` | GPT | gpt-4o | `OPENAI_API_KEY` |
| `openai_compat.py` | Grok | grok-3 | `GROK_API_KEY` |
| `openai_compat.py` | Ollama | llama3 | không cần |
| `gemini.py` | Google | gemini-2.5-flash | `GEMINI_API_KEY` |

`factory.py` dùng `importlib` để lazy load — chỉ import SDK khi provider đó thực sự được chọn, tránh lỗi nếu chưa cài thư viện.

---

## Luồng hoạt động

```
Người dùng chạy: impact-check -p gemini -o tree --save-html report.html
                        │
                        ▼
              ┌─────────────────┐
              │     cli.py      │  Đọc tham số, khởi tạo provider
              └────────┬────────┘
                       │
          ┌────────────▼────────────┐
          │    git_collector.py     │  git diff --staged
          │                         │  → danh sách file + diff + content
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │   context_finder.py     │  Quét project 1 lần (cached)
          │                         │  → file liên quan (3 layer)
          │                         │  → file test
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │      debug.py           │  Ghi impact_check.log
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │      analyzer.py        │  Ghép content vào prompt
          │                         │  → trim theo provider limits
          │                         │  → gọi AI provider
          │                         │  → parse + repair JSON response
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────────────────────┐
          │             Output                       │
          ├──────────────────────────────────────────┤
          │  reporter.py        → terminal (table)   │
          │  reporter.py        → terminal (tree)    │  -o tree
          │  html_reporter.py   → report.html        │  --save-html
          │  json               → stdout / file      │  -o json / --save-json
          └──────────────────────────────────────────┘
```

**Luồng guard (tách biệt hoàn toàn):**

```
git commit
    ↓
.git/hooks/pre-commit  →  impact-check guard
                                ↓
                          guard.py
                            ├── _staged_files()       git diff --staged --name-only
                            ├── detect .env staged    → HIGH
                            └── scan content          → regex patterns
                                    ↓
                          HIGH found → exit 1 (block)
                          MED only   → exit 0 (warn)
                          Clean      → exit 0
```

---

## Dữ liệu chảy qua hệ thống

```
git staged files
    │
    ├─ path, status (A/M/D/R)
    ├─ diff (phần thay đổi, tối đa 20.000 chars)
    └─ content (toàn bộ nội dung file, tối đa 25.000 chars)
                │
                ▼
        context_finder
                │
                ├─ related_files: { path → [{ path, content, transitive, content_truncated }] }
                └─ test_files:    [{ path, content }]
                            │
                            ▼
                  analyzer.trim_to_provider_limits()
                            │  ưu tiên direct > indirect
                            │  cắt theo max_files + max_content per provider
                            ▼
                      analyzer._build_prompt()
                            │  thêm "... (truncated)" khi content_truncated = True
                            ▼
                      provider.complete()  →  AI API
                            │
                            ▼
                  analyzer._parse_response()
                            │
                            └─ AI response → JSON:
                               {
                                 affected_modules: [...]  ← downstream consumers only
                                 tests_needed:     [...]
                                 risks:            [...]  ← threat model aware
                                 summary:          "..."
                               }
```
