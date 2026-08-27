from core import accounts
from services.state import acquire_lock, lock_for


def test_create_update_remove_archives():
    acc = accounts.create_account(name="测试账号", device="")
    aid = acc["id"]
    assert accounts.account_exists(aid)
    assert any(a["id"] == aid for a in accounts.list_accounts())
    assert accounts.update_account(aid, name="改名", enabled=False)["name"] == "改名"
    assert accounts.remove_account(aid) is True
    assert not accounts.account_exists(aid)


def test_default_cannot_be_removed():
    assert accounts.remove_account("default") is False


def test_same_account_single_lock():
    # 用非默认账号试锁，避免污染 default
    acc = accounts.create_account(name="lock-test", device="")
    aid = acc["id"]
    try:
        assert acquire_lock(aid) is True
        assert acquire_lock(aid) is False  # 非阻塞，重复获取失败
    finally:
        lock = lock_for(aid)
        if lock.locked():
            lock.release()
        accounts.remove_account(aid)
