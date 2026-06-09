# thesis_store.py
# v3.3.0 段 1：thesis JSON 文件读写工具（仅工具，不暴露 API）。
# API 层封装留给段 2。
#
# 硬边界（v3.3.0 整个期间不破）：
#   - 不 import DCF 任何东西
#   - 不读 DCF cache / 输出
#   - 不调 yfinance / sina / akshare
#   - 不做 NLP / auto-suggest / smart default
#
# 假设：
#   - 本地单用户，不做并发锁
#   - 整个文件覆写，不做 merge
#   - 文件不存在时 read 返回 None（不在这里填充模板，留给段 2）

import json
from datetime import datetime, timezone
from pathlib import Path

from thesis_utils import canonical_ticker, filename_key


# 用 __file__ 定位项目根目录，避免不同启动方式（cwd 不同）导致目录乱跑。
# 与 cache_layer.py 风格一致。
_PROJECT_ROOT = Path(__file__).parent.resolve()
_THESIS_DIR   = _PROJECT_ROOT / "data" / "thesis"


def _thesis_path(ticker: str) -> Path:
    """
    根据 ticker 计算 thesis 文件的完整路径。
    内部调 filename_key（其内部又调 canonical_ticker，所以 ticker 校验在这里完成）。
    """
    key = filename_key(ticker)
    return _THESIS_DIR / f"{key}_thesis.json"


def read_thesis(canonical_ticker_input: str) -> dict | None:
    """
    读取指定 ticker 的 thesis 文件。

    参数:
        canonical_ticker_input : ticker 字符串（任意大小写/空白，内部会规范化）

    返回:
        文件存在 → dict（JSON 解析结果）
        文件不存在 → None（不在这里填充模板，由段 2 API 层处理）

    异常:
        ticker 不合法（路径字符、超长等）→ ValueError
        文件存在但 JSON 解析失败 → 透传 json.JSONDecodeError
    """
    path = _thesis_path(canonical_ticker_input)
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_thesis(canonical_ticker_input: str, payload: dict) -> None:
    """
    将 payload 写入指定 ticker 的 thesis 文件。

    行为:
        - 整个文件覆写（不做 merge）
        - data/thesis/ 不存在则创建
        - 写入前覆盖 payload["last_modified"] = 当前 UTC ISO 8601
          （前端传入的 last_modified 字段会被忽略——服务端是唯一权威时间源）

    参数:
        canonical_ticker_input : ticker 字符串
        payload                : 要写入的 dict（可序列化为 JSON）

    异常:
        ticker 不合法 → ValueError
        IO 失败 → 透传给上层（段 2 API 决定如何处理）
    """
    path = _thesis_path(canonical_ticker_input)

    # 确保 data/thesis/ 目录存在
    _THESIS_DIR.mkdir(parents=True, exist_ok=True)

    # 服务端权威时间戳 —— 覆盖前端传值
    # ISO 8601 UTC，例 "2026-05-11T14:23:45.123456+00:00"
    payload["last_modified"] = datetime.now(timezone.utc).isoformat()

    # 与现有项目风格一致：utf-8 + ensure_ascii=False（中文字段直接可读）
    # indent=2 让 thesis 文件人类可读，方便手动编辑/排查
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
