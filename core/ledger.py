"""好友台账：以会话显示名为键的本地持久化好友库（每账号独立 ledger.json）。

v1（P0）：仅 consumer 数据（显示名 + 火花天数 + 会话存在性 + 勾选状态 + 最后发送时间）。
P1 起扩展 short_id / nickname / user_id / 置信度，业务主键升级为 short_id（不可变），
display_name 变为可变字段。匹配铁律：display_name 相同即视为同一人（P0 阶段约束）。
"""

from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from .config import DEFAULT_ACCOUNT_ID, account_dir
from .avatar import fetch_and_save_avatar


def ledger_path(account_id: str | None = None) -> Path:
    return account_dir(account_id) / "ledger.json"


_lock = threading.RLock()


def _locked(func):
    """让台账的读-改-写操作在同一把锁内完成，避免并发请求互相覆盖。"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _lock:
            return func(*args, **kwargs)

    return wrapper


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _default_entry(display_name: str) -> dict:
    """P1 完整 schema：display_name 为 P0 主键，short_id 为业务主键（不可变）。"""
    return {
        "display_name": display_name,
        "contact_key": f"name:{display_name}",
        "nickname": "",
        "short_id": "",
        "user_id": "",
        "avatar": "",             # 本地缓存头像路径 /avatars/<aid>/<hash>.<ext>
        "streak_days": 0,
        "has_conversation": False,
        "selected": False,
        "selected_order": None,  # 勾选顺序（越小越靠前，仅勾选时有效；持久化保证重启后置顶顺序不丢）
        "last_sent_at": None,
        "channel": "none",        # consumer | creator | none
        "join_confidence": "low",  # high: display_name 与 nickname 已对上；low: 未确认
        "identity_ambiguous": False,  # 同名联系人无法唯一定位时，禁止自动发送
        "source": {"creator": False, "consumer": False},
    }


def _parse_streak(text) -> int:
    """从火花文本（如 '🔥 81' / '81' / '81天'）提取天数，解析失败返回 0。"""
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else 0


def _norm_ws(s) -> str:
    """空白归一化（仅用于 join 匹配，不改存储原样值）：
    consumer 页显示名可能含不间断空格（U+00A0），creator 接口返回普通空格。"""
    return str(s or "").replace("\u00a0", " ").strip()


def _consumer_contact_key(contact: dict) -> str:
    """优先使用页面会话标识；旧页面/旧数据则以昵称键兼容。"""
    conversation_id = str(contact.get("conversation_id", "")).strip()
    if conversation_id:
        return f"conversation:{conversation_id}"
    sync_key = str(contact.get("sync_key", "")).strip()
    if sync_key:
        return f"sync:{sync_key}"
    return f"name:{str(contact.get('name', '')).strip()}"


@_locked
def load_ledger(account_id: str | None = None) -> list[dict]:
    entries: list[dict] = []
    lp = ledger_path(account_id)
    if lp.exists():
        try:
            data = json.loads(lp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries = [dict(e) for e in data if isinstance(e, dict) and e.get("display_name")]
                name_counts = Counter(str(e.get("display_name", "")).strip() for e in entries)
                for e in entries:
                    e.setdefault("contact_key", f"name:{e.get('display_name', '')}")
                    e["identity_ambiguous"] = bool(e.get("identity_ambiguous")) or name_counts.get(str(e.get("display_name", "")).strip(), 0) > 1
                    # 派生标记（不持久化，读时计算保证一致）：
                    # no_consumer_conversation：consumer 私信无会话（自动识别，不限来源）
                    #   → 勾选也不会被通道 A 发送（默认 skipped 或降级），除非开启通道 B
                    # creator_only：creator 页有记录 且 consumer 无会话（creator 来源子集）
                    e["no_consumer_conversation"] = not e.get("has_conversation")
                    e["creator_only"] = e.get("channel") == "creator" and e["no_consumer_conversation"]
        except Exception:
            pass
    return entries


def _save(entries: list[dict], account_id: str | None = None) -> None:
    with _lock:
        d = account_dir(account_id)
        d.mkdir(parents=True, exist_ok=True)
        lp = ledger_path(account_id)
        tmp = lp.with_name(f"{lp.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, lp)


def _upsert(entries: list[dict], entry: dict) -> dict:
    """按 contact_key upsert：更新新字段，但保留已有条目的 selected / last_sent_at。

    新增条目补齐默认字段，保证 schema 一致。返回命中/新增的条目。
    """
    contact_key = entry.get("contact_key") or f"name:{entry['display_name']}"
    for e in entries:
        if e.get("contact_key", f"name:{e.get('display_name', '')}") == contact_key:
            selected = e.get("selected", False)
            last_sent = e.get("last_sent_at")
            identity_ambiguous = bool(e.get("identity_ambiguous"))
            e.update(entry)
            for k, v in _default_entry(entry["display_name"]).items():
                e.setdefault(k, v)
            e["selected"] = selected
            e["last_sent_at"] = last_sent
            e["identity_ambiguous"] = identity_ambiguous or bool(entry.get("identity_ambiguous"))
            return e
    base = _default_entry(entry["display_name"])
    base["contact_key"] = contact_key
    base.update(entry)
    entries.append(base)
    return base


@_locked
def merge_consumer_contacts(contacts: list[dict], account_id: str | None = None) -> dict:
    """把 consumer 会话列表（fetch_chat_contacts 的 names 字段）upsert 进台账。

    只更新火花天数与会话存在性，不覆盖用户勾选与历史发送时间。
    旧版本以 ``name:<显示名>`` 存储会话；新版本会使用会话/头像键。若一次
    扫描中该显示名唯一，则把旧记录迁移到新键，保留原来的勾选和发送历史，避免
    升级后把同一个联系人显示成两条。

    同一趟扫描出现多个相同显示名时，整组丢弃，不再创建「同名待确认」记录。
    已存在的真实同名历史记录也会在本次有有效扫描结果时清理；单个旧的
    ``name:<name>`` 兼容项与一个稳定键并存则按迁移场景处理，不误删真实联系人。

    返回 {"added", "updated", "migrated", "removed_duplicates", "duplicate_names", "total"}。
    """
    entries = load_ledger(account_id)
    added = 0
    updated = 0
    migrated = 0
    contacts = [c for c in (contacts or []) if isinstance(c, dict)]
    prepared: list[tuple[dict, str, str]] = []
    for contact in contacts:
        name = str(contact.get("name", "")).strip()
        if name:
            prepared.append((contact, name, _norm_ws(name)))

    # 空结果可能是登录失效或页面尚未加载，不要因为一次失败把已有台账清空。
    if not prepared:
        return {
            "added": 0,
            "updated": 0,
            "migrated": 0,
            "removed_duplicates": 0,
            "duplicate_names": [],
            "total": len(entries),
        }

    current_name_counts = Counter(norm for _contact, _name, norm in prepared)
    duplicate_norms = {
        norm for norm, count in current_name_counts.items() if count > 1
    }

    # 清理真正的历史同名记录。只有「旧 name 键 + 一个稳定键」的组合视为
    # 可迁移遗留数据，交给 _migrate_unique_legacy_entry 保留勾选/发送历史。
    historical_groups: dict[str, list[dict]] = {}
    for entry in entries:
        historical_groups.setdefault(_norm_ws(entry.get("display_name")), []).append(entry)
    historical_duplicate_norms: set[str] = set()
    for norm, group in historical_groups.items():
        if len(group) < 2:
            continue
        stable = [
            entry for entry in group
            if str(entry.get("contact_key") or f"name:{entry.get('display_name', '')}")
            != f"name:{entry.get('display_name', '')}"
        ]
        if len(stable) != 1 or len(group) != 2:
            historical_duplicate_norms.add(norm)

    blocked_norms = duplicate_norms | historical_duplicate_norms
    duplicate_names = sorted(blocked_norms)
    before_cleanup = len(entries)
    if blocked_norms:
        entries = [
            entry for entry in entries
            if _norm_ws(entry.get("display_name")) not in blocked_norms
        ]
    removed_duplicates = before_cleanup - len(entries)

    # 当前扫描中的同名整组不入库；不同会话键也不再制造多条同名记录。
    accepted: list[tuple[dict, str, str]] = [
        item for item in prepared if item[2] not in blocked_norms
    ]
    by_key = {e.get("contact_key", f"name:{e.get('display_name', '')}"): e for e in entries}
    contact_name_counts = Counter(norm for _contact, _name, norm in accepted)

    def _migrate_unique_legacy_entry(name: str, contact_key: str) -> bool:
        """把唯一的旧名称键收敛到当前稳定键，绝不合并同名多会话。"""
        normalized_name = _norm_ws(name)
        if contact_key == f"name:{name}" or contact_name_counts[normalized_name] != 1:
            return False
        legacy_entries = [
            entry for entry in entries
            if entry.get("contact_key", f"name:{entry.get('display_name', '')}") == f"name:{name}"
            and _norm_ws(entry.get("display_name", "")) == normalized_name
        ]
        if len(legacy_entries) != 1:
            return False

        legacy = legacy_entries[0]
        current = by_key.get(contact_key)
        if current is None:
            legacy["contact_key"] = contact_key
            by_key.pop(f"name:{name}", None)
            by_key[contact_key] = legacy
            return True

        # 已存在稳定键时，删除遗留名称项；保留任何已选状态和发送历史。
        current["selected"] = bool(current.get("selected")) or bool(legacy.get("selected"))
        if current.get("selected_order") is None:
            current["selected_order"] = legacy.get("selected_order")
        current["last_sent_at"] = current.get("last_sent_at") or legacy.get("last_sent_at")
        current.setdefault("source", {}).update(legacy.get("source") or {})
        entries.remove(legacy)
        by_key.pop(f"name:{name}", None)
        return True

    def _resolve_avatar(c: dict) -> str:
        """并发下载头像；下载失败或为空时保留旧头像。"""
        avatar_url = c.get("avatar") or ""
        if not avatar_url:
            return ""
        new_avatar = fetch_and_save_avatar(avatar_url, account_id)
        if new_avatar:
            return new_avatar
        old = by_key.get(_consumer_contact_key(c))
        return (old.get("avatar") or "") if old else ""

    accepted_contacts = [contact for contact, _name, _norm in accepted]
    with ThreadPoolExecutor(max_workers=8) as pool:
        avatar_paths = list(pool.map(_resolve_avatar, accepted_contacts))

    for c, avatar_path in zip(accepted_contacts, avatar_paths):
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        contact_key = _consumer_contact_key(c)
        if _migrate_unique_legacy_entry(name, contact_key):
            migrated += 1
        exists = contact_key in by_key
        old_avatar = (by_key.get(contact_key) or {}).get("avatar") or ""
        e = _upsert(entries, {
            "display_name": name,
            "contact_key": contact_key,
            "streak_days": _parse_streak(c.get("streak")),
            "has_conversation": True,
            "channel": "consumer",
            "avatar": avatar_path or old_avatar,
            "identity_ambiguous": False,
        })
        e.setdefault("source", {})["consumer"] = True
        by_key[contact_key] = e
        # creator 侧已确认且两侧名字一致 → 置信度升级 high
        if e.get("source", {}).get("creator") and e.get("nickname") == name:
            e["join_confidence"] = "high"
        if exists:
            updated += 1
        else:
            added += 1
    if added or updated or migrated or removed_duplicates:
        # 同名记录已在上面整组过滤；清掉旧版本遗留的 ambiguous 标记，
        # 让前端不再出现「同名待确认」状态。
        for entry in entries:
            if entry.get("source", {}).get("consumer"):
                entry["identity_ambiguous"] = False
        _save(entries, account_id)
    return {
        "added": added,
        "updated": updated,
        "migrated": migrated,
        "removed_duplicates": removed_duplicates,
        "duplicate_names": duplicate_names,
        "total": len(entries),
    }


@_locked
def import_config_friends(friends: list[str], account_id: str | None = None) -> dict:
    """兼容迁移：把 config.json 的 friends 同步进台账并默认勾选。

    - 已存在条目：置 selected=True（保持原发送目标集合不变）
    - 不存在条目：新增并 selected=True
    返回 {"added", "selected"}。
    """
    entries = load_ledger(account_id)
    by_name = {e.get("display_name"): e for e in entries}
    added = 0
    selected = 0
    for name in friends or []:
        name = str(name).strip()
        if not name:
            continue
        if name in by_name:
            if not by_name[name].get("selected"):
                by_name[name]["selected"] = True
                selected += 1
        else:
            entries.append({
                **_default_entry(name),
                "has_conversation": False,
                "selected": True,
            })
            by_name[name] = entries[-1]
            added += 1
    if added or selected:
        _save(entries, account_id)
    return {"added": added, "selected": selected}


def get_selected(account_id: str | None = None) -> list[dict]:
    return [e for e in load_ledger(account_id) if e.get("selected")]


@_locked
def merge_creator_map(mapping: dict, account_id: str | None = None) -> dict:
    """把 creator 采集的 {short_id: {nickname, user_id}} 合并进台账（预 join，乐观）。

    - display_name == nickname 或 display_name == short_id → 回填并 high（两侧确认同一人）
    - 否则新建条目：display_name=nickname（假定）、confidence=low、channel=creator
    返回 {"joined", "added", "updated", "total"}。
    """
    entries = load_ledger(account_id)
    by_display = {e.get("display_name"): e for e in entries}
    # 归一化匹配：consumer 显示名可能含 NBSP（U+00A0），creator 昵称是普通空格。
    # 用「归一化名 → 条目列表」保留同名全部候选，避免 stub 覆盖真实条目。
    by_display_norm: dict[str, list[dict]] = {}
    for e in entries:
        by_display_norm.setdefault(_norm_ws(e.get("display_name")), []).append(e)

    def _pick_target(exact, by_sid, norm_list):
        """从候选条目里择优：优先有 consumer 数据（会话/勾选/历史发送）的真实条目，避免命中孤立 stub。"""
        seen: list[dict] = []
        for c in ([exact, by_sid] + (norm_list or [])):
            if c is not None and c not in seen:
                seen.append(c)
        if not seen:
            return None
        for c in seen:
            if (
                c.get("has_conversation")
                or c.get("source", {}).get("consumer")
                or c.get("last_sent_at")
            ):
                return c
        return seen[0]

    joined = added = updated = 0
    for sid, info in (mapping or {}).items():
        sid = str(sid).strip()
        if not sid:
            continue
        nick = str(info.get("nickname", "")).strip()
        uid = str(info.get("user_id", ""))
        target = _pick_target(
            by_display.get(nick),
            by_display.get(sid),
            by_display_norm.get(nick),
        )
        if target is not None:
            changed = False
            if target.get("short_id") != sid:
                target["short_id"] = sid
                changed = True
            if target.get("nickname") != nick:
                target["nickname"] = nick
                changed = True
            if target.get("user_id") != uid:
                target["user_id"] = uid
                changed = True
            src = target.setdefault("source", {})
            # 旧 schema 数据恢复：有会话即视为 consumer 侧出现过
            if target.get("has_conversation") and not src.get("consumer"):
                src["consumer"] = True
            if not src.get("creator"):
                src["creator"] = True
                changed = True
            # high 需两侧确认：display_name 已在 consumer 页出现 且 == nickname（或 == short_id）
            if target.get("join_confidence") != "high" and src.get("consumer"):
                target["join_confidence"] = "high"
                changed = True
            if target.get("has_conversation") and target.get("channel") != "consumer":
                target["channel"] = "consumer"
                changed = True
            if changed:
                updated += 1
            joined += 1
            # 清理同 short_id 的孤立 stub（creator-only 无会话/未发送的条目，被真实 join 后删除）
            target_idx = entries.index(target)
            for i in range(len(entries) - 1, -1, -1):
                e = entries[i]
                if (
                    i != target_idx
                    and e.get("short_id") == sid
                    and not e.get("has_conversation")
                    and not e.get("last_sent_at")
                ):
                    del entries[i]
        else:
            entries.append({
                **_default_entry(nick),
                "nickname": nick,
                "short_id": sid,
                "user_id": uid,
                "source": {"creator": True, "consumer": False},
                "join_confidence": "low",
                "channel": "creator",
            })
            by_display[nick] = entries[-1]
            added += 1
    if added or updated:
        _save(entries, account_id)
    return {"joined": joined, "added": added, "updated": updated, "total": len(entries)}


@_locked
def confirm_join(display_name: str, account_id: str | None = None) -> None:
    """发送时确认（P1 关键兜底）：该 display_name 的会话已在 consumer 页成功定位+标题校验通过。

    标记 source.consumer=true、channel=consumer；若 nickname == display_name（两侧名字一致）
    → join_confidence 升级为 high。
    """
    entries = load_ledger(account_id)
    for e in entries:
        if e.get("display_name") == display_name:
            e.setdefault("source", {})["consumer"] = True
            e["channel"] = "consumer"
            if e.get("nickname") and e["nickname"] == display_name:
                e["join_confidence"] = "high"
            break
    _save(entries, account_id)


@_locked
def set_selected(entries_in: list[dict], account_id: str | None = None) -> dict:
    """批量更新勾选与勾选顺序：entries: [{display_name, selected, selected_order}]。

    已存在条目更新勾选；不存在的条目新增并置勾选（支持手动添加好友）。
    selected_order 随勾选持久化（勾选组内排序，重启后置顶顺序不丢）；
    取消勾选时清空 selected_order。
    返回 {"updated", "added"}。
    """
    entries = load_ledger(account_id)
    by_key = {e.get("contact_key", f"name:{e.get('display_name', '')}"): e for e in entries}
    updated = 0
    added = 0
    for it in entries_in:
        name = str(it.get("display_name", "")).strip()
        contact_key = str(it.get("contact_key") or f"name:{name}").strip()
        sel = bool(it.get("selected"))
        order = it.get("selected_order")
        if not name:
            continue
        if contact_key in by_key:
            e = by_key[contact_key]
            if bool(e.get("selected")) != sel:
                e["selected"] = sel
                updated += 1
            new_order = order if sel else None
            if e.get("selected_order") != new_order:
                e["selected_order"] = new_order
                updated += 1
        else:
            entries.append({
                **_default_entry(name),
                "contact_key": contact_key,
                "has_conversation": False,
                "selected": sel,
                "selected_order": order if sel else None,
            })
            by_key[contact_key] = entries[-1]
            added += 1
    if updated or added:
        _save(entries, account_id)
    return {"updated": updated, "added": added}


@_locked
def update_send_result(
    display_name: str,
    ok: bool,
    at: str | None = None,
    via_creator: bool = False,
    account_id: str | None = None,
) -> None:
    """发送后回写台账：更新 last_sent_at；成功时标记会话存在。

    via_creator=True（通道 B 首条消息）：只记时间、不置 has_conversation——
    creator 侧发过首条消息 ≠ consumer 私信页有会话；否则 run_send 会误判
    走通道 A 去 consumer 页定位，而列表里根本没有该会话导致失败。
    """
    entries = load_ledger(account_id)
    for e in entries:
        if e.get("display_name") == display_name:
            e["last_sent_at"] = at or _now()
            if ok and not via_creator:
                e["has_conversation"] = True
            break
    _save(entries, account_id)


@_locked
def mark_no_consumer_conversation(display_name: str, account_id: str | None = None) -> None:
    """自愈：通道 A 在 consumer 页定位失败时调用（仅对 creator-only 条目）。

    把误标的 has_conversation 修正回 false，避免每轮都误走通道 A 失败；
    channel 保持 creator，之后走通道 B 或 skipped。
    """
    entries = load_ledger(account_id)
    changed = False
    for e in entries:
        if e.get("display_name") == display_name and e.get("channel") == "creator":
            if e.get("has_conversation"):
                e["has_conversation"] = False
                changed = True
            break
    if changed:
        _save(entries, account_id)


@_locked
def remove_contacts(
    names: list[str], account_id: str | None = None, contact_keys: list[str] | None = None
) -> dict:
    """从台账删除指定联系人（优先按 contact_key，兼容 display_name）。

    仅清理台账条目；调用方负责同步清理 config.friends，避免选择状态残留。
    返回 {"removed", "total"}。
    """
    remove = {str(n).strip() for n in (names or []) if str(n).strip()}
    remove_keys = {str(key).strip() for key in (contact_keys or []) if str(key).strip()}
    if not remove and not remove_keys:
        return {"removed": 0, "total": len(load_ledger(account_id))}
    entries = load_ledger(account_id)
    before = len(entries)
    entries = [
        e for e in entries
        if (
            str(e.get("display_name", "")).strip() not in remove
            and str(e.get("contact_key", f"name:{e.get('display_name', '')}")).strip() not in remove_keys
        )
    ]
    removed = before - len(entries)
    if removed:
        _save(entries, account_id)
    return {"removed": removed, "total": len(entries)}


@_locked
def remove_all_contacts(account_id: str | None = None) -> dict:
    """清空该账号全部联系人台账，返回删除数量。"""
    entries = load_ledger(account_id)
    removed = len(entries)
    if removed:
        _save([], account_id)
    return {"removed": removed, "total": 0}


def stats(account_id: str | None = None) -> dict:
    """台账自愈报表：分布统计、连续成功 Top、low 待确认、近 7 天发送。"""
    entries = load_ledger(account_id)
    now = datetime.now().astimezone()
    week_ago = (now - timedelta(days=7)).isoformat()
    high = sum(1 for e in entries if e.get("join_confidence") == "high")
    no_conv = [
        {"display_name": e["display_name"], "channel": e.get("channel")}
        for e in entries
        if not e.get("has_conversation")
    ]
    low_pending = [
        e["display_name"]
        for e in entries
        if e.get("join_confidence") == "low" and e.get("has_conversation")
    ]
    recent_sent = [
        e["display_name"]
        for e in entries
        if str(e.get("last_sent_at") or "") >= week_ago
    ]
    top_streak = sorted(entries, key=lambda e: -(e.get("streak_days") or 0))[:10]
    return {
        "total": len(entries),
        "selected": sum(1 for e in entries if e.get("selected")),
        "confidence": {"high": high, "low": len(entries) - high},
        "with_short_id": sum(1 for e in entries if e.get("short_id")),
        "no_conversation": no_conv,
        "low_pending": low_pending,
        "recent_sent_7d": recent_sent,
        "top_streak": [
            {"display_name": e["display_name"], "streak_days": e.get("streak_days")}
            for e in top_streak
        ],
    }


# 别名兼容
update_from_sync = merge_consumer_contacts
