# impact-check

CLI tool phân tích ảnh hưởng của code change bằng AI trước khi commit.

---

## Yêu cầu

- Python 3.9+
- Git đã cài đặt
- API key của ít nhất một AI provider (xem bên dưới)

---

## Cài đặt

```bash
cd d:\tool
pip install -e .[claude]    # Claude (mặc định)
pip install -e .[all]       # Tất cả provider
```

Nếu dùng virtual environment thì activate trước.

---

## Cấu hình API key

Tạo file `.env` trong thư mục project hoặc tại `d:\tool\.env` để dùng chung:

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AI...
GROK_API_KEY=xai-...
```

Ollama không cần API key — chỉ cần cài và khởi động service: https://ollama.com

---

## Sử dụng

```bash
cd <thư-mục-project>
git add <file>
impact-check
```

### Các flag

```bash
impact-check -p gemini               # chọn provider: claude (mặc định), gemini, gpt, grok, ollama
impact-check -p ollama -m mistral    # chỉ định model cụ thể
impact-check -o tree                 # heatmap rủi ro dạng cây + bảng chi tiết
impact-check -o json                 # output JSON thô
impact-check --save-html report.html # lưu báo cáo HTML
impact-check --save-json result.json # lưu kết quả JSON
impact-check --dry-run               # thu thập dữ liệu, ghi log, không gọi AI
impact-check install                 # cài pre-commit hook chạy AI analysis
impact-check install --guard         # cài pre-commit hook quét API key/secret — local, < 1 giây, không cần AI
impact-check guard                   # chạy secret scanner thủ công (không cần hook)
```

Các flag có thể kết hợp tự do:

```bash
impact-check -p gemini -o tree --save-html report.html
```

---

## Secret Guard

`impact-check install --guard` cài hook quét staged files trước mỗi `git commit` — không cần network, không cần AI.

**Phát hiện:** Anthropic / OpenAI / Gemini / Grok / AWS / GitHub / Stripe / Slack key, private key, hardcoded password/secret.

**Hành vi:**
- `HIGH` (key thật) → block commit
- `MED` (password/token generic) → cảnh báo, commit vẫn tiếp tục

Để bỏ qua một dòng cụ thể:

```python
EXAMPLE_KEY = "sk-ant-EXAMPLE..."  # noguard
```

Chạy thủ công (không cần hook):

```bash
impact-check guard
```
