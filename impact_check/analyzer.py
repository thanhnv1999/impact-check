import json

from .providers.base import BaseProvider
from . import debug
from .config import (
    MAX_CHANGED_CONTENT,
    MAX_DIFF_CONTENT,
    MAX_RELATED_CONTENT,
    MAX_RELATED_FILES,
    PROVIDER_LIMITS,
    DEFAULT_PROVIDER_LIMITS,
)


def trim_to_provider_limits(related_files: dict, provider_name: str) -> tuple:
    """
    Trim related_files theo giới hạn của provider.
    Ưu tiên giữ direct files, cắt indirect trước khi đạt max_files.
    Trả về (trimmed_dict, warnings_list).
    """
    limits = PROVIDER_LIMITS.get(provider_name.lower(), DEFAULT_PROVIDER_LIMITS)
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
            was_cut = len(content) > max_content
            if was_cut:
                content = content[:max_content]
            trimmed_refs.append({
                **ref,
                "content": content,
                "content_truncated": ref.get("content_truncated", False) or was_cut,
            })

        result[changed_path] = trimmed_refs

    total_chars = sum(len(r.get("content", "")) for refs in result.values() for r in refs)
    safe_chars  = limits["safe_chars"]
    safe_exceeded = total_chars > safe_chars

    return result, warnings, safe_exceeded


def trim_to_safe_chars(related_files: dict, provider_name: str) -> dict:
    """
    Cắt tỉ lệ nội dung tất cả related files để tổng chars ≤ safe_chars.
    Giữ nguyên số file, chỉ giảm độ dài content của từng file theo cùng tỉ lệ.
    """
    limits = PROVIDER_LIMITS.get(provider_name.lower(), DEFAULT_PROVIDER_LIMITS)
    safe_chars = limits["safe_chars"]

    total = sum(len(r.get("content", "")) for refs in related_files.values() for r in refs)
    if total <= safe_chars:
        return related_files

    ratio = safe_chars / total
    result = {}
    for changed_path, refs in related_files.items():
        trimmed = []
        for ref in refs:
            content = ref.get("content", "")
            new_len = max(0, int(len(content) * ratio))
            was_cut = new_len < len(content)
            trimmed.append({
                **ref,
                "content": content[:new_len],
                "content_truncated": ref.get("content_truncated", False) or was_cut,
            })
        result[changed_path] = trimmed
    return result

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
"affected_modules" CHỈ chứa các file KHÔNG nằm trong danh sách "Changed Files" phía trên — tức là các file hiện có trong codebase đang import hoặc gọi code bị thay đổi (downstream consumers).
KHÔNG bao giờ list chính file đang thay đổi vào affected_modules.
Với file có status ADDED: nó chưa tồn tại trước đó nên không file nào bị "ảnh hưởng" bởi nó — thay vào đó, nếu một file trong Changed Files đã import nó, ghi nhận file đó.
Nếu không tìm thấy downstream consumer nào thực sự → để affected_modules là mảng rỗng, không bịa.

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
Trước khi tạo risk entry, hãy kiểm tra code thực tế trong context được cung cấp:
- Nếu risk liên quan đến một hàm cụ thể (escaping, validation, auth...) → đọc code hàm đó và xác nhận risk có thực sự tồn tại không.
- Code đã xử lý đúng → KHÔNG tạo risk entry.
- Code chưa xử lý → tạo entry với level phù hợp.
- Không có code trong context để kiểm tra → tạo entry với level LOW, ghi rõ "chưa xác minh được".

Đánh giá severity theo threat model thực tế của project, không áp dụng threat model web app cho CLI tool:
- CLI tool local: người dùng duy nhất là developer chạy lệnh trên máy mình.
  XSS trong file HTML local = LOW (không có attacker, không có web server).
  File path traversal trong --output flag = MED (có thể ghi đè file ngoài ý muốn).
  Lộ API key ra stdout/log = HIGH (có thể bị capture bởi CI log, shell history).
- Backend/API: injection, auth bypass, data leak = HIGH.
- Nếu không rõ threat model → để LOW và giải thích điều kiện để nó trở thành HIGH.

Mỗi risk phải nêu: điều gì xảy ra sai, xảy ra khi nào (điều kiện cụ thể), hậu quả người dùng thấy gì.
  SAI: "Validation có thể bị hỏng hoặc hoạt động sai"
  ĐÚNG: "onVerify() gọi validateField('gameIdx') nhưng form schema chỉ có field 'gameId' → validateField silently no-op → user submit được game ID rỗng, API nhận data sai"

"location" ghi đúng: "path/to/file → functionName()"

== SUMMARY ==
2-3 câu brief cho tech lead. Nêu: thay đổi gì (dùng tên hàm thật), ảnh hưởng file nào (dùng tên file thật), rủi ro tổng thể mức nào và tại sao.

Chỉ trả về JSON theo đúng cấu trúc dưới đây. Không kèm markdown, không có text ngoài JSON.
Các string value trong JSON không được chứa ký tự xuống dòng — dùng dấu cách thay thế.

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

# Phiên bản rút gọn cho Ollama local — bỏ ví dụ SAI/ĐÚNG để tiết kiệm ~600 token prefill time
SYSTEM_PROMPT_OLLAMA = """\
You are a senior developer reviewing code changes. Analyze the diff and related files, then return ONLY a JSON object — no markdown, no text outside JSON.

Rules:
- Write analysis in Vietnamese. Keep all file names, function names, variables in English as-is.
- affected_modules.reason: name the specific file and function that calls the changed code, explain why it breaks.
- tests_needed.description: include (1) function/component, (2) specific input/scenario, (3) expected behavior.
- risks.description: what goes wrong, under what condition, what the user sees.
- risks.location format: "path/to/file → functionName()"
- summary: 2-3 sentences for tech lead, use real file/function names.

Return this exact JSON structure:
{"affected_modules":[{"name":"","reason":"","severity":"HIGH|MED|LOW"}],"tests_needed":[{"type":"unit|integration|e2e|regression","description":"","priority":"HIGH|MED|LOW"}],"risks":[{"level":"HIGH|MED|LOW","description":"","location":""}],"summary":""}\
"""


def build_prompt(git_changes, related_files: dict, project_structure: str, test_files: list = None) -> str:
    return _build_prompt(git_changes, related_files, project_structure, test_files or [])


def analyze(
    git_changes,
    related_files: dict,
    project_structure: str,
    provider: BaseProvider,
    test_files: list = None,
    provider_name: str = "",
) -> dict:
    system = SYSTEM_PROMPT_OLLAMA if provider_name.lower() == "ollama" else SYSTEM_PROMPT
    prompt = _build_prompt(git_changes, related_files, project_structure, test_files or [])
    debug.section("System prompt gửi đi", system)
    debug.section("User prompt gửi đi", prompt)
    raw = provider.complete(system, prompt)
    return _parse_response(raw)


def _parse_response(raw: str) -> dict:
    text = raw.strip()

    # Extract from markdown code block if present
    if "```" in text:
        for part in text.split("```"):
            candidate = part.lstrip("json").strip()
            if candidate.startswith("{"):
                text = candidate
                break

    # Try 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try 2: slice from first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # Try 3: repair literal newlines inside JSON string values
        try:
            return json.loads(_repair_json_strings(candidate))
        except json.JSONDecodeError:
            pass

    return {
        "affected_modules": [],
        "tests_needed": [],
        "risks": [],
        "summary": text[:500] if text else "Could not parse AI response.",
    }


def _repair_json_strings(text: str) -> str:
    """Replace literal newlines/tabs inside JSON string values with a space."""
    result = []
    in_string = False
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string
            result.append(c)
        elif in_string and c in ("\n", "\r"):
            result.append(" ")
        elif in_string and c == "\t":
            result.append(" ")
        else:
            result.append(c)
        i += 1
    return "".join(result)


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
                if len(f.diff) <= MAX_DIFF_CONTENT
                else f.diff[:MAX_DIFF_CONTENT] + "\n... (truncated)"
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
                    if ref.get("content_truncated"):
                        content += "\n... (truncated)"
                    parts.append(f"```\n{content}\n```")

    if test_files:
        parts.append("\n## Existing Test Files:")
        for tf in test_files:
            parts.append(f"\n#### {tf['path']}")
            if tf.get("content"):
                parts.append(f"```\n{tf['content']}\n```")

    parts.append("\n\nAnalyze the impact and return the JSON response.")
    return "\n".join(parts)
