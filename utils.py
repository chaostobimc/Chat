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
