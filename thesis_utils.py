# thesis_utils.py
# v3.3.0 段 1：ticker 规范化工具。
#
# 设计原则：
#   - 整个 v3.3.0（含后续段 2、段 3、段 4）所有 ticker 处理走这两个函数。
#   - 后面段不要再写第二份 normalization 实现。
#   - 此模块零依赖：不 import DCF、yfinance、akshare、Flask 任何东西。
#     thesis 模块的硬边界从这里开始守住。

# 路径攻击字符黑名单（防止 ticker 被用来构造 path traversal）
_FORBIDDEN_PATH_CHARS = ("/", "\\", "..")
_MAX_TICKER_LEN       = 32


def canonical_ticker(t: str) -> str:
    """
    把用户输入的 ticker 规范化为存储/查询用的标准形式。

    规则:
        .strip().upper()

    校验（任一不满足 raise ValueError）:
        - 不能为空字符串或纯空白
        - 不能包含 / \\ .. 等路径字符
        - strip 后长度不能 > 32

    示例:
        "aapl"        → "AAPL"
        "  0700.HK  " → "0700.HK"
        "600519.SS"   → "600519.SS"
    """
    if not isinstance(t, str):
        raise ValueError(f"ticker 必须是字符串，收到 {type(t).__name__}")

    stripped = t.strip()
    if not stripped:
        raise ValueError("ticker 不能为空字符串或纯空白")

    if len(stripped) > _MAX_TICKER_LEN:
        raise ValueError(f"ticker 长度不能超过 {_MAX_TICKER_LEN}，收到 {len(stripped)}")

    for bad in _FORBIDDEN_PATH_CHARS:
        if bad in stripped:
            raise ValueError(f"ticker 不能包含路径字符 '{bad}'：{stripped!r}")

    return stripped.upper()


def filename_key(t: str) -> str:
    """
    把 ticker 转换为安全的文件名片段（用于 thesis JSON 文件命名）。

    规则:
        canonical_ticker(t).lower().replace(".", "_")

    内部先调 canonical_ticker，复用其校验逻辑——不重复实现。

    示例:
        "AAPL"       → "aapl"
        "0700.HK"    → "0700_hk"
        "600519.SS"  → "600519_ss"
        "000001.SZ"  → "000001_sz"
    """
    canonical = canonical_ticker(t)
    return canonical.lower().replace(".", "_")
