from app.permissions import PermissionBroker


def test_permission_grant_and_pending():
    broker = PermissionBroker()
    pending = broker.request("s1", "files_read", "choose a file", "choose_file")
    assert broker.pending("s1").id == pending.id
    assert not broker.has("s1", "files_read")
    broker.consume("s1")
    broker.grant("s1", "files_read")
    assert broker.has("s1", "files_read")


def test_deny_clears_pending():
    broker = PermissionBroker()
    broker.request("s1", "gmail_read", "read mail", "gmail_read")
    broker.deny("s1")
    assert broker.pending("s1") is None
