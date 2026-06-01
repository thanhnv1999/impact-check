import json

from .providers.base import BaseProvider
from . import debug

MAX_CHANGED_CONTENT = 25000
MAX_RELATED_CONTENT_IN_PROMPT = 25000
MAX_RELATED_FILES = 12

PROVIDER_LIMITS = {
    "gemini": {"max_files": 20, "max_content": 40000, "safe_chars": 800000},
    "claude": {"max_files": 12, "max_content": 25000, "safe_chars": 150000},
    "gpt":    {"max_files": 10, "max_content": 20000, "safe_chars": 100000},
    "grok":   {"max_files": 10, "max_content": 20000, "safe_chars": 100000},
    "ollama": {"max_files":  5, "max_content":  8000, "safe_chars":  20000},
}
_DEFAULT_LIMITS = {"max_files": 12, "max_content": 25000, "safe_chars": 150000}


def trim_to_provider_limits(related_files: dict, provider_name: str) -> tuple:
    """
    Trim related_files theo giới hạn của provider.
    Ưu tiên giữ direct files, cắt indirect trước khi đạt max_files.
    Trả về (trimmed_dict, warnings_list).
    """
    limits = PROVIDER_LIMITS.get(provider_name.lower(), _DEFAULT_LIMITS)
    max_files = limits["max_files"]
    max_content = limits["max_content"]
    warnings = []
    result = {}

    for changed_path, refs in related_files.items():
        direct   = [r for r in refs if not r.get("transitive")]
        indirect = [r for r in refs if r.get("transitive")]

        kept_direct   = direct[:max_files]
        kept_indirect = indirect[:max(0, max_files - len(kept_direct))]

        dropped = (len(direct) - len(kept_direct)) + (len(indirect) - len(kept_indirect))
        if dropped > 0:
            warnings.append(
                f"Đã bỏ {dropped} file liên quan"
                f" (giới hạn {provider_name.upper()}: tối đa {max_files} file)"
            )

        trimmed_refs = []
        for ref in kept_direct + kept_indirect:
            content = ref.get("content", "")
            if len(content) > max_content:
                content = content[:max_content]
            trimmed_refs.append({**ref, "content": content})

        result[changed_path] = trimmed_refs

    # Cảnh báo nếu tổng content vẫn vượt ngưỡng an toàn
    total_chars = sum(len(r.get("content", "")) for refs in result.values() for r in refs)
    safe_chars  = limits["safe_chars"]
    if total_chars > safe_chars:
        est_tokens  = total_chars // 4
        safe_tokens = safe_chars  // 4
        warnings.append(
            f"Ước tính ~{est_tokens:,} token vượt ngưỡng an toàn"
            f" {safe_tokens:,} token — kết quả có thể bị ảnh hưởng"
        )

    return result, warnings

SYSTEM_PROMPT = """\
Bạn là senior developer đang review code cho đồng nghiệp. Nhiệm vụ: đọc diff + các file liên quan, rồi trả lời thẳng vào vấn đề — chỗ nào bị ảnh hưởng, cần test gì, rủi ro ở đâu.

== NGÔN NGỮ ==
Viết tiếng Việt tự nhiên như dev nói chuyện, không dịch máy. 

Tên hàm, class, file, biến, feature, trang — LUÔN giữ nguyên tiếng Anh, KHÔNG dịch sang tiếng Việt.
  SAI: "trang giỏ hàng thường", "luồng thanh toán", "giỏ hàng quà tặng miễn phí"
  ĐÚNG: "CartComp.vue", "checkout flow", "CartFreeComp.vue"

Khi phân biệt nhiều variant của cùng một feature, dùng tên file hoặc route thật, KHÔNG dùng "thường/thông thường/bình thường" để chỉ loại "mặc định".
  SAI: "cart thường, free-gift, mulpay"
  ĐÚNG: "CartComp.vue, CartFreeComp.vue, pages/[group]/mulpay/CartComp.vue"

== AFFECTED_MODULES ==
"reason" phải nêu: file cụ thể nào, hàm nào trong file đó gọi đến phần bị thay đổi, tại sao bị ảnh hưởng.
  SAI: "Component này sử dụng useCart.ts nên bị ảnh hưởng"
  ĐÚNG: "useCart.ts gọi useUseGameUserForm() ở line ~465, truyền validateField vào — nếu field name sai thì validation trong onVerify() không trigger"

== TESTS_NEEDED ==
Mỗi test phải nêu đủ 3 phần: (1) function/component cần test, (2) input hoặc scenario cụ thể, (3) expected behavior.
  SAI: "Viết unit test cho onVerify() để đảm bảo validate hoạt động đúng"
  SAI: "Chạy lại tất cả integration test liên quan đến checkout flow"
  ĐÚNG: "unit — onVerify() trong useGameUserForm.js: gọi với form field tên 'gameIdx' không tồn tại → expect validateField throw/return error, isVerifying reset về false, gameUserErrorMessage được set"
  ĐÚNG: "regression — CartComp.vue: user nhập game ID hợp lệ rồi bấm 検証 → expect nút 購入確認へ enable, không bị stuck ở trạng thái verifying"

== RISKS ==
Mỗi risk phải nêu: điều gì xảy ra sai, xảy ra khi nào (điều kiện cụ thể), hậu quả người dùng thấy gì.
  SAI: "Validation có thể bị hỏng hoặc hoạt động sai"
  ĐÚNG: "onVerify() gọi validateField('gameIdx') nhưng form schema chỉ có field 'gameId' → validateField silently no-op → user submit được game ID rỗng, API nhận data sai"

"location" ghi đúng: "path/to/file → functionName()"

== SUMMARY ==
2-3 câu brief cho tech lead. Nêu: thay đổi gì (dùng tên hàm thật), ảnh hưởng file nào (dùng tên file thật), rủi ro tổng thể mức nào và tại sao.

Chỉ trả về JSON theo đúng cấu trúc dưới đây. Không kèm markdown, không có text ngoài JSON.

{
  "affected_modules": [
    {"name": "Tên file cụ thể", "reason": "Hàm nào trong file đó gọi đến phần thay đổi, ảnh hưởng như thế nào", "severity": "HIGH|MED|LOW"}
  ],
  "tests_needed": [
    {"type": "unit|integration|e2e|regression", "description": "function/component + input scenario + expected behavior — không nói chung chung", "priority": "HIGH|MED|LOW"}
  ],
  "risks": [
    {"level": "HIGH|MED|LOW", "description": "Điều gì xảy ra sai, khi nào, hậu quả cụ thể người dùng hoặc hệ thống thấy gì", "location": "path/to/file → functionName()"}
  ],
  "summary": "2-3 câu brief cho tech lead dùng tên file/hàm thật, không dùng từ dịch máy"
}\
"""


def build_prompt(git_changes, related_files: dict, project_structure: str, test_files: list = None) -> str:
    return _build_prompt(git_changes, related_files, project_structure, test_files or [])


def analyze(
    git_changes,
    related_files: dict,
    project_structure: str,
    provider: BaseProvider,
    test_files: list = None,
) -> dict:
    prompt = _build_prompt(git_changes, related_files, project_structure, test_files or [])
    debug.section("System prompt gửi đi", SYSTEM_PROMPT)
    debug.section("User prompt gửi đi", prompt)
    raw = provider.complete(SYSTEM_PROMPT, prompt)
    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    text = raw.strip()

    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part.lstrip("json").strip()
            if candidate.startswith("{"):
                text = candidate
                break

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return {
        "affected_modules": [],
        "tests_needed": [],
        "risks": [],
        "summary": text[:500] if text else "Could not parse AI response.",
    }


def _build_prompt(
    git_changes,
    related_files: dict,
    project_structure: str,
    test_files: list,
) -> str:
    STATUS_LABEL = {"A": "ADDED", "M": "MODIFIED", "D": "DELETED", "R": "RENAMED"}

    parts = [
        f"## Branch: {git_changes.branch}",
        f"\n## Project Structure:\n```\n{project_structure}\n```",
        f"\n## Changed Files ({len(git_changes.files)}):",
    ]

    for f in git_changes.files:
        label = STATUS_LABEL.get(f.status, f.status)
        parts.append(f"\n### [{label}] {f.path}")

        if f.content:
            content = (
                f.content
                if len(f.content) <= MAX_CHANGED_CONTENT
                else f.content[:MAX_CHANGED_CONTENT] + "\n... (truncated)"
            )
            parts.append(f"**Full content:**\n```\n{content}\n```")

        if f.diff:
            diff = (
                f.diff
                if len(f.diff) <= 3000
                else f.diff[:3000] + "\n... (truncated)"
            )
            parts.append(f"**Diff:**\n```diff\n{diff}\n```")

    has_related = any(v for v in related_files.values())
    if has_related:
        parts.append("\n## Files That Depend On Changed Files:")
        for changed_path, refs in related_files.items():
            if not refs:
                continue
            parts.append(f"\n**{changed_path}** is used by:")
            for ref in refs[:MAX_RELATED_FILES]:
                label = " (indirect)" if ref.get("transitive") else ""
                parts.append(f"\n#### {ref['path']}{label}")
                if ref.get("content"):
                    content = ref["content"]
                    if len(content) > MAX_RELATED_CONTENT_IN_PROMPT:
                        content = content[:MAX_RELATED_CONTENT_IN_PROMPT] + "\n... (truncated)"
                    parts.append(f"```\n{content}\n```")

    if test_files:
        parts.append("\n## Existing Test Files:")
        for tf in test_files:
            parts.append(f"\n#### {tf['path']}")
            if tf.get("content"):
                parts.append(f"```\n{tf['content']}\n```")

    parts.append("\n\nAnalyze the impact and return the JSON response.")
    return "\n".join(parts)
