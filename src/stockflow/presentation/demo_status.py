"""Ephemeral status overrides for users in the offline demo."""

_ACTIVE_BY_USER_ID = {}


def is_demo_user_active(user_id, default=True):
    return _ACTIVE_BY_USER_ID.get(str(user_id), default)


def set_demo_user_active(user_id, active):
    if not user_id:
        raise ValueError("O usuário demonstrativo precisa de um identificador.")
    _ACTIVE_BY_USER_ID[str(user_id)] = bool(active)


def reset_demo_user_statuses():
    _ACTIVE_BY_USER_ID.clear()
