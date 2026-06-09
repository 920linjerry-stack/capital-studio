# cache_layer.py
# 职责：
#   通用磁盘缓存基础设施。所有数据源（yfinance、AKShare）共用同一套缓存。
#
# 设计原则：
#   1. 文件系统 + JSON 即可，零额外依赖（不引入 Redis 等）
#   2. 每个 cache_key 对应一个独立 JSON 文件，便于人工查看/清理
#   3. 缓存失败时降级——读取异常不让上层崩溃，直接走原 fetch_func
#   4. 不同数据类型用不同 TTL，由调用方决定
#
# 缓存目录：项目根目录下 data/cache/（首次调用自动创建）
# 文件命名：{cache_key}.json
#   例如 quote_AAPL.json、history_0700.HK_1y.json、financials_600519.SS.json
#
# 缓存文件结构：
#   { "cached_at": "2025-04-15T10:23:45.123456", "data": <实际数据> }

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

# ── 缓存目录定位 ─────────────────────────────────────────────────────────────
# 用 __file__ 定位项目根目录，避免不同启动方式（cwd 不同）导致目录乱跑。
_PROJECT_ROOT = Path(__file__).parent.resolve()
_CACHE_DIR    = _PROJECT_ROOT / "data" / "cache"


def _ensure_cache_dir():
    """确保缓存目录存在；不存在则递归创建。多进程并发时 mkdir 也是安全的。"""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # 极端情况（磁盘满、权限不足）忽略——上层会降级到直接 fetch
        pass


def _safe_filename(cache_key: str) -> str:
    """
    把 cache_key 转换为安全的文件名。
    替换路径分隔符和其他可能引起问题的字符。
    例如 'history_0700.HK_1y' 是安全的，'history_/etc/passwd' 会被清洗。
    """
    # 只保留字母数字、下划线、连字符、点
    safe = re.sub(r"[^A-Za-z0-9_.\-]", "_", cache_key)
    return f"{safe}.json"


def _cache_path(cache_key: str) -> Path:
    return _CACHE_DIR / _safe_filename(cache_key)


def _read_cache(cache_key: str, ttl_seconds: int):
    """
    读取缓存。命中且未过期则返回 data，否则返回 None。
    任何 IO/JSON 异常都吞掉返回 None（让上层降级到 fetch）。
    """
    path = _cache_path(cache_key)
    if not path.exists():
        return None

    try:
        # mtime 比 cached_at 字段更可靠（不会因时区/格式问题出错）
        age = time.time() - path.stat().st_mtime
        if age > ttl_seconds:
            return None

        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("data")
    except Exception:
        # 文件损坏 / JSON 解析失败 / 编码异常 → 当作缓存未命中
        return None


def _read_stale_cache(cache_key: str):
    """
    读取已过期缓存。作为 quote/history/financials 实时抓取失败时的兜底，避免
    远端瞬时失败让 PT、详情页或 DCF defaults 退化成全空数据。
    """
    path = _cache_path(cache_key)
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("data")
    except Exception:
        return None


def _is_meaningful(value) -> bool:
    """
    判断一个 fetcher 返回值是否值得写入缓存。
    防止"空 dict / 全 0 / 全 None"这种抓取失败的结果污染缓存。

    v3.2.4 修复：financials dict 里 currency/tax_rate/shares 等字段永远有
    默认值（0.21、1000.0），导致空财报被误判为"有意义"写盘。
    现在忽略这些"默认值兜底"字段，只看真正的业务数据字段。

    规则：
        None              → 无效
        dict              → 至少有一个【非默认 key】的 value 是有意义的
                            （非 None、非 0、非空串、非空集合）
        list              → 必须非空
        其他类型          → 视为有效
    """
    if value is None:
        return False
    if isinstance(value, dict):
        if not value:
            return False
        for k, v in value.items():
            # 跳过"默认值兜底"字段——这些 key 即使有值也不代表抓取成功
            if k in _IGNORED_DEFAULT_KEYS:
                continue
            if v is None:
                continue
            if isinstance(v, (int, float)) and v == 0:
                continue
            if isinstance(v, str) and v == "":
                continue
            if isinstance(v, (list, dict)) and not v:
                continue
            return True   # 找到一个真有意义的字段
        return False      # 全是默认值或空，拒绝写盘
    if isinstance(value, list):
        return len(value) > 0
    return True


# 这些 key 即使有值也不算"有意义的数据"——它们是默认兜底或元信息，
# 不能仅凭这些字段就判定 fetcher 抓取成功。
_IGNORED_DEFAULT_KEYS = {
    "currency", "tax_rate", "shares", "beta", "data_source",
    "symbol", "name", "company", "market", "_error",
}


def _write_cache(cache_key: str, data) -> None:
    """
    写入缓存。任何 IO 异常都吞掉，不让缓存失败影响主流程。
    用 utf-8 + ensure_ascii=False 保留中文（港股/A 股公司名等）。

    护栏：_is_meaningful() 失败的值不写盘——避免空抓取结果污染缓存。
    """
    if not _is_meaningful(data):
        # 不写盘，让下次访问重新尝试 fetch（数据源可能从故障中恢复）
        print(f"[cache_layer] 跳过写入：{cache_key} 数据为空/无意义")
        return

    _ensure_cache_dir()
    path = _cache_path(cache_key)
    payload = {
        "cached_at": datetime.now().isoformat(),
        "data"     : data,
    }
    try:
        # 先写到临时文件再 rename，避免半写入文件被下次读取
        tmp_path = path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, path)   # 原子操作，跨平台
    except Exception:
        pass


# ── 对外 API ─────────────────────────────────────────────────────────────────

def cached_call(cache_key: str, ttl_seconds: int, fetch_func):
    """
    通用缓存包装。

    参数:
        cache_key   (str)     : 唯一缓存标识，建议形如 "quote_AAPL"
        ttl_seconds (int)     : 缓存有效期（秒）
        fetch_func  (callable): 缓存未命中时调用的函数，无参数，返回 JSON 可序列化数据

    返回:
        缓存命中：直接返回缓存的 data
        缓存未命中或过期：调用 fetch_func()，将结果写入缓存后返回
        fetch_func 抛错：直接抛出（上层应有 try/except）

    使用示例:
        data = cached_call(
            f"quote_{symbol}",
            300,
            lambda: _get_quote_internal(symbol),
        )
    """
    # 1. 尝试读缓存
    cached = _read_cache(cache_key, ttl_seconds)
    if cached is not None:
        return cached

    # 2. 缓存未命中 → 调 fetch_func
    data = fetch_func()

    # financials fetcher 可能返回带 _error 的 quote-implied fallback。
    # 如果磁盘里有旧的真实财务缓存，优先用旧缓存，避免用估算值覆盖更可靠的报表值。
    if cache_key.startswith("financials_") and isinstance(data, dict) and data.get("_error"):
        stale = _read_stale_cache(cache_key)
        if _is_meaningful(stale):
            print(f"[cache_layer] 使用过期财务缓存兜底：{cache_key}")
            return stale

    # quote/history/financials 远端偶发失败时，fetcher 会返回全空 dict 或空 list。
    # 这种结果不应打穿 PT/详情页/DCF；若磁盘里有旧的有效缓存，优先返回旧值。
    if (
        cache_key.startswith("quote_")
        or cache_key.startswith("history_")
        or cache_key.startswith("financials_")
    ) and not _is_meaningful(data):
        stale = _read_stale_cache(cache_key)
        if _is_meaningful(stale):
            print(f"[cache_layer] 使用过期缓存兜底：{cache_key}")
            return stale

    # 3. 写缓存（即使 fetch 返回 None / 空也写，避免反复打远端）
    if data is not None:
        _write_cache(cache_key, data)

    return data


def clear_cache(prefix: str = None) -> int:
    """
    清空缓存。

    参数:
        prefix : 仅清空文件名以该前缀开头的缓存。
                 None 表示全部清空。
                 例如 prefix="quote_" 只清股价缓存。

    返回:
        删除的文件数量（用于日志/调试）
    """
    if not _CACHE_DIR.exists():
        return 0

    deleted = 0
    try:
        for f in _CACHE_DIR.iterdir():
            if not f.is_file() or f.suffix != ".json":
                continue
            if prefix is None or f.stem.startswith(prefix):
                try:
                    f.unlink()
                    deleted += 1
                except Exception:
                    pass
    except Exception:
        pass
    return deleted


def get_cache_info() -> dict:
    """
    返回缓存目录概况，供调试用。
    """
    if not _CACHE_DIR.exists():
        return {"dir": str(_CACHE_DIR), "exists": False, "files": 0, "size_kb": 0}

    files    = list(_CACHE_DIR.glob("*.json"))
    total_kb = sum(f.stat().st_size for f in files) / 1024
    return {
        "dir"     : str(_CACHE_DIR),
        "exists"  : True,
        "files"   : len(files),
        "size_kb" : round(total_kb, 1),
    }
