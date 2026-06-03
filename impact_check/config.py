# ── Giới hạn scan file ────────────────────────────────────────────────────────
MAX_FILES_TO_SCAN = 1000        # số file tối đa quét trong 1 lần chạy
MAX_FILE_SIZE     = 200 * 1024  # bỏ qua file > 200 KB

# ── Giới hạn nội dung gửi lên AI ─────────────────────────────────────────────
MAX_CHANGED_CONTENT  = 25000   # chars tối đa của 1 file đang thay đổi
MAX_DIFF_CONTENT     = 20000   # chars tối đa của git diff 1 file (~570 dòng diff)
MAX_RELATED_FILES    = 12      # số file liên quan tối đa per changed file
MAX_RELATED_CONTENT  = 25000   # chars tối đa nội dung 1 file liên quan
MAX_TEST_FILES       = 5       # số test file tối đa
MAX_TEST_CONTENT     = 25000   # chars tối đa nội dung 1 test file

# ── Giới hạn theo provider ────────────────────────────────────────────────────
# Mỗi provider có context window và tốc độ khác nhau, nên giới hạn riêng.
#
# Các key trong mỗi entry:
#   max_files   — số related file tối đa được đưa vào prompt (ưu tiên direct trước indirect)
#   max_content — chars tối đa của nội dung MỖI related file (cắt nếu vượt)
#   safe_chars  — tổng chars toàn bộ context an toàn để gửi lên (≈ safe_chars / 4 tokens)
#                 vượt ngưỡng này thì cảnh báo nhưng vẫn gửi; mô hình có thể bỏ sót phần cuối
#
# Tại sao các con số này?
#   gemini  — context window 1M token, nhanh, rẻ → cho phép nhiều file và nội dung dài nhất
#   claude  — context window ~200K token, cân bằng chất lượng/tốc độ → mức trung bình
#   gpt     — context window ~128K token (gpt-4o) → giới hạn nhỏ hơn claude một chút
#   grok    — tương đương gpt về context → dùng cùng giá trị với gpt
#   ollama  — chạy local, RAM hạn chế, model nhỏ (llama3 ~8B) → giới hạn thấp nhất
PROVIDER_LIMITS = {
    #                max_files  max_content  safe_chars  max_tokens
    #                (related)  (per file)   (total ctx) (AI output)
    "gemini": {"max_files": 20, "max_content": 40000, "safe_chars": 800000, "max_tokens": 8192},
    "claude": {"max_files": 12, "max_content": 25000, "safe_chars": 150000, "max_tokens": 8192},
    "gpt":    {"max_files": 10, "max_content": 20000, "safe_chars": 100000, "max_tokens": 8192},
    "grok":   {"max_files": 10, "max_content": 20000, "safe_chars": 100000, "max_tokens": 8192},
    # Ollama chạy local: context window mặc định 4,096 token (input + output).
    # Trừ system prompt (~800) + template (~150) + output buffer (1,000) → còn ~2,100 token cho content.
    # safe_chars = 2,100 × 4 = 8,400 → làm tròn xuống 8,000 cho an toàn.
    "ollama": {"max_files":  3, "max_content":  3000, "safe_chars":  8000, "max_tokens":  500},
}
# Dùng khi provider không có trong PROVIDER_LIMITS (provider mới thêm chưa có profile)
DEFAULT_PROVIDER_LIMITS = {"max_files": 12, "max_content": 25000, "safe_chars": 150000, "max_tokens": 8192}
