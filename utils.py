"""
Shared utility functions for the Discord Ticket Bot.
This module has NO dependencies on bot.py or spawner.py to avoid circular imports.
"""

import os


def is_admin(user_id: int) -> bool:
    """Check if a user is in the ADMIN_USER_IDS list from .env."""
    admin_ids_str = os.getenv('ADMIN_USER_IDS', '')
    if not admin_ids_str.strip():
        return False
    admin_ids = [uid.strip() for uid in admin_ids_str.split(',') if uid.strip()]
    return str(user_id) in admin_ids


def get_support_role_ids() -> list:
    """Get the list of support role IDs from .env."""
    role_ids_str = os.getenv('SUPPORT_ROLE_IDS', '')
    if not role_ids_str.strip():
        return []
    return [rid.strip() for rid in role_ids_str.split(',') if rid.strip()]


def has_support_role(member) -> bool:
    """Check if a member has any of the SUPPORT_ROLE_IDS from .env."""
    role_ids = get_support_role_ids()
    if not role_ids:
        return False
    member_role_ids = [str(r.id) for r in member.roles]
    return any(rid in member_role_ids for rid in role_ids)
