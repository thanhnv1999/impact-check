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

Chọn provider:

```bash
impact-check                        # Claude (mặc định)
impact-check -p gemini
impact-check -p gpt
impact-check -p grok
impact-check -p ollama
impact-check -p ollama -m mistral   # Chỉ định model
```

Kiểm tra dữ liệu trước khi gọi AI:

```bash
impact-check --dry-run              # Ghi log, không gọi AI
```

Cài pre-commit hook (tự động chạy khi `git commit`):

```bash
impact-check install
```
