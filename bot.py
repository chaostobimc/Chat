"""
Discord Ticket Bot - Premium Edition
A professional ticket management system with web dashboard.
"""

import os
import io
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

import discord
from discord import (
    app_commands, 
    Interaction,
    ChannelType,
    PermissionOverwrite
)
from discord.ui import View, button, Button, Modal, TextInput
from discord.ext import tasks
from dotenv import load_dotenv
from fpdf import FPDF

load_dotenv()

# ==================== DATABASE ====================

class Database:
    def __init__(self, db_path: str = "database/tickets.db"):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_panels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT,
                    channel_id TEXT,
                    guild_id TEXT,
                    title TEXT DEFAULT 'Support Tickets',
                    description TEXT DEFAULT 'Wähle eine Kategorie für dein Anliegen',
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    panel_id INTEGER,
                    custom_id TEXT UNIQUE,
                    label TEXT NOT NULL,
                    emoji TEXT,
                    color TEXT DEFAULT 'blurple',
                    category_id TEXT,
                    support_role_id TEXT,
                    description TEXT,
                    question_title TEXT,
                    question_placeholder TEXT,
                    require_question BOOLEAN DEFAULT 0,
                    max_tickets INTEGER DEFAULT 3,
                    image_url TEXT,
                    image_local TEXT,
                    use_modal BOOLEAN DEFAULT 0,
                    modal_title TEXT,
                    modal_fields TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (panel_id) REFERENCES ticket_panels(id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT UNIQUE,
                    user_id TEXT,
                    guild_id TEXT,
                    channel_id TEXT,
                    button_id INTEGER,
                    subject TEXT,
                    status TEXT DEFAULT 'open',
                    priority TEXT DEFAULT 'normal',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    closed_by TEXT,
                    FOREIGN KEY (button_id) REFERENCES ticket_buttons(id)
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ticket_counter (
                    guild_id TEXT PRIMARY KEY,
                    counter INTEGER DEFAULT 0
                )
            """)

            # NEW: Panel send queue for dashboard -> bot communication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS panel_send_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    panel_id INTEGER,
                    channel_id TEXT,
                    guild_id TEXT,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)

            # NEW: Cached guild channels for dashboard channel selector
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT,
                    channel_id TEXT,
                    channel_name TEXT,
                    channel_type TEXT,
                    category_name TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # NEW: Cached guild roles for dashboard role selector
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT,
                    role_id TEXT,
                    role_name TEXT,
                    role_color TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration: Add support_role_ids column if it doesn't exist
            cursor.execute("PRAGMA table_info(ticket_buttons)")
            columns = [col['name'] for col in cursor.fetchall()]
            if 'support_role_ids' not in columns:
                cursor.execute("ALTER TABLE ticket_buttons ADD COLUMN support_role_ids TEXT")
                # Migrate existing support_role_id data
                cursor.execute("""
                    UPDATE ticket_buttons 
                    SET support_role_ids = support_role_id 
                    WHERE support_role_id IS NOT NULL AND support_role_id != ''
                """)

            conn.commit()
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
    
    def get_guild_settings(self, guild_id: str) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings WHERE key LIKE ?", 
                         (f"guild_{guild_id}_%",))
            return {row['key']: row['value'] for row in cursor.fetchall()}
    
    def set_guild_setting(self, guild_id: str, key: str, value: str):
        self.set_setting(f"guild_{guild_id}_{key}", value)
    
    def get_panels(self, guild_id: str = None) -> list:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if guild_id:
                cursor.execute(
                    "SELECT * FROM ticket_panels WHERE guild_id = ? ORDER BY created_at DESC",
                    (guild_id,)
                )
            else:
                cursor.execute("SELECT * FROM ticket_panels ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_panel_buttons(self, panel_id: int) -> list:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM ticket_buttons WHERE panel_id = ? ORDER BY id",
                (panel_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def create_panel(self, guild_id: str, title: str, description: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO ticket_panels (guild_id, title, description) VALUES (?, ?, ?)",
                (guild_id, title, description)
            )
            return cursor.lastrowid
    
    def update_panel(self, panel_id: int, **kwargs):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for key, value in kwargs.items():
                cursor.execute(
                    f"UPDATE ticket_panels SET {key} = ? WHERE id = ?",
                    (value, panel_id)
                )
    
    def delete_panel(self, panel_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ticket_buttons WHERE panel_id = ?", (panel_id,))
            cursor.execute("DELETE FROM ticket_panels WHERE id = ?", (panel_id,))
    
    def create_button(self, panel_id: int, label: str, custom_id: str, 
                      emoji: str = None, color: str = "blurple",
                      category_id: str = None, support_role_id: str = None,
                      description: str = None, question_title: str = None,
                      question_placeholder: str = None, require_question: int = 0,
                      max_tickets: int = 3, image_url: str = None, 
                      image_local: str = None, use_modal: int = 0,
                      modal_title: str = None, modal_fields: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticket_buttons 
                (panel_id, custom_id, label, emoji, color, category_id, 
                 support_role_id, description, question_title, question_placeholder,
                 require_question, max_tickets, image_url, image_local,
                 use_modal, modal_title, modal_fields)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (panel_id, custom_id, label, emoji, color, category_id,
                  support_role_id, description, question_title, question_placeholder,
                  require_question, max_tickets, image_url, image_local,
                  use_modal, modal_title, modal_fields))
            return cursor.lastrowid
    
    def update_button(self, button_id: int, **kwargs):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for key, value in kwargs.items():
                cursor.execute(
                    f"UPDATE ticket_buttons SET {key} = ? WHERE id = ?",
                    (value, button_id)
                )
    
    def delete_button(self, button_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ticket_buttons WHERE id = ?", (button_id,))
    
    def get_button(self, custom_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ticket_buttons WHERE custom_id = ?", (custom_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_button_by_id(self, button_id: int) -> Optional[Dict]:
        """Get a button by its database ID."""
        if not button_id:
            return None
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ticket_buttons WHERE id = ?", (button_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_ticket_count(self, guild_id: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT counter FROM ticket_counter WHERE guild_id = ?",
                (guild_id,)
            )
            row = cursor.fetchone()
            return row['counter'] if row else 0
    
    def increment_ticket_count(self, guild_id: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ticket_counter (guild_id, counter) VALUES (?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET counter = counter + 1
            """, (guild_id,))
            return self.get_ticket_count(guild_id)
    
    def create_ticket(self, ticket_id: str, user_id: str, guild_id: str,
                     channel_id: str, button_id: int, subject: str = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tickets 
                (ticket_id, user_id, guild_id, channel_id, button_id, subject)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ticket_id, user_id, guild_id, channel_id, button_id, subject))
            return cursor.lastrowid
    
    def get_open_ticket(self, user_id: str, guild_id: str, button_id: int) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tickets 
                WHERE user_id = ? AND guild_id = ? AND button_id = ? AND status = 'open'
            """, (user_id, guild_id, button_id))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def count_user_tickets(self, user_id: str, guild_id: str, button_id: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM tickets 
                WHERE user_id = ? AND guild_id = ? AND button_id = ? AND status = 'open'
            """, (user_id, guild_id, button_id))
            return cursor.fetchone()['count']
    
    def get_ticket_by_channel(self, channel_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'",
                (channel_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def close_ticket(self, channel_id: str, closed_by: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tickets 
                SET status = 'closed', closed_at = CURRENT_TIMESTAMP, closed_by = ?
                WHERE channel_id = ? AND status = 'open'
            """, (closed_by, channel_id))
    
    def get_all_tickets(self, guild_id: str = None) -> list:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if guild_id:
                cursor.execute(
                    "SELECT * FROM tickets WHERE guild_id = ? ORDER BY created_at DESC",
                    (guild_id,)
                )
            else:
                cursor.execute("SELECT * FROM tickets ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def save_transcript(self, ticket_id: str, content: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO transcripts (ticket_id, content) VALUES (?, ?)",
                (ticket_id, content)
            )

    # ==================== NEW: GUILD DATA CACHE ====================

    def sync_guild_channels(self, guild_id: str, channels: List[Dict]):
        """Sync guild channels to database for dashboard channel selector."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM guild_channels WHERE guild_id = ?", (guild_id,))
            for ch in channels:
                cursor.execute("""
                    INSERT INTO guild_channels (guild_id, channel_id, channel_name, channel_type, category_name)
                    VALUES (?, ?, ?, ?, ?)
                """, (guild_id, ch['id'], ch['name'], ch['type'], ch.get('category', '')))

    def sync_guild_roles(self, guild_id: str, roles: List[Dict]):
        """Sync guild roles to database for dashboard role selector."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM guild_roles WHERE guild_id = ?", (guild_id,))
            for role in roles:
                cursor.execute("""
                    INSERT INTO guild_roles (guild_id, role_id, role_name, role_color)
                    VALUES (?, ?, ?, ?)
                """, (guild_id, role['id'], role['name'], role.get('color', '#99AAB5')))

    def get_guild_channels(self, guild_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if guild_id:
                cursor.execute(
                    "SELECT * FROM guild_channels WHERE guild_id = ? ORDER BY channel_name",
                    (guild_id,)
                )
            else:
                cursor.execute("SELECT * FROM guild_channels ORDER BY channel_name")
            return [dict(row) for row in cursor.fetchall()]

    def get_guild_roles(self, guild_id: str = None) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if guild_id:
                cursor.execute(
                    "SELECT * FROM guild_roles WHERE guild_id = ? ORDER BY role_name",
                    (guild_id,)
                )
            else:
                cursor.execute("SELECT * FROM guild_roles ORDER BY role_name")
            return [dict(row) for row in cursor.fetchall()]

    # ==================== NEW: PANEL SEND QUEUE ====================

    def queue_panel_send(self, panel_id: int, channel_id: str, guild_id: str) -> int:
        """Add a panel send request to the queue."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO panel_send_queue (panel_id, channel_id, guild_id, status)
                VALUES (?, ?, ?, 'pending')
            """, (panel_id, channel_id, guild_id))
            return cursor.lastrowid

    def get_pending_sends(self) -> List[Dict]:
        """Get all pending panel send requests."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT q.*, p.title, p.description, p.image_url
                FROM panel_send_queue q
                JOIN ticket_panels p ON q.panel_id = p.id
                WHERE q.status = 'pending'
                ORDER BY q.created_at ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def mark_send_processed(self, queue_id: int, status: str = 'done', error_message: str = None):
        """Mark a queue entry as processed."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE panel_send_queue 
                SET status = ?, error_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, error_message, queue_id))

    # ==================== NEW: DEFAULT SUPPORT ROLES ====================

    def get_default_support_roles(self) -> Optional[str]:
        """Get the default support roles setting (comma-separated role IDs/names)."""
        return self.get_setting('default_support_roles', '')

    def set_default_support_roles(self, value: str):
        """Set the default support roles."""
        self.set_setting('default_support_roles', value)

    def get_effective_support_roles(self, button_data: Dict) -> str:
        """Get the effective support roles for a button, falling back to defaults."""
        # First try button-specific support_role_ids
        role_ids = button_data.get('support_role_ids', '')
        if role_ids and role_ids.strip():
            return role_ids
        # Fallback to legacy support_role_id
        legacy = button_data.get('support_role_id', '')
        if legacy and legacy.strip():
            return legacy
        # Fallback to global default
        return self.get_default_support_roles() or ''


def create_text_input(label: str, style=None, placeholder: str = None, 
                      required: bool = True, max_length: int = None, 
                      custom_id: str = None) -> TextInput:
    """Create a TextInput compatible with discord.ui.TextInput (discord.py 2.7+)."""
    if style is None:
        style = discord.TextStyle.short
    
    # discord.py 2.7+: All parameters are keyword-only
    kwargs = {
        'label': label,
        'style': style,
        'required': required,
    }
    
    if placeholder is not None:
        kwargs['placeholder'] = placeholder
    if max_length is not None:
        kwargs['max_length'] = max_length
    if custom_id is not None:
        kwargs['custom_id'] = custom_id
    
    return TextInput(**kwargs)


# ==================== TICKET PANEL VIEW ====================

def get_button_style(color_name: str) -> discord.ButtonStyle:
    """Convert color name to discord.ButtonStyle."""
    styles = {
        'blurple': discord.ButtonStyle.blurple,
        'grey': discord.ButtonStyle.grey,
        'gray': discord.ButtonStyle.grey,
        'green': discord.ButtonStyle.green,
        'red': discord.ButtonStyle.red,
    }
    return styles.get(color_name.lower(), discord.ButtonStyle.blurple)


def parse_role_mentions(roles_string: str, guild: discord.Guild) -> List[discord.Role]:
    """
    Parse a comma-separated string of role mentions / IDs / names into Role objects.
    Supports:
      - @Rollenname (Discord-style mentions)
      - <@&123456789> (raw Discord role mentions)
      - 123456789 (raw role IDs)
      - Rollenname (plain role names)
    """
    if not roles_string or not roles_string.strip():
        return []

    resolved = []
    parts = [p.strip() for p in roles_string.split(',') if p.strip()]

    for part in parts:
        # Strip @ prefix if present
        cleaned = part.lstrip('@').strip()

        # Try raw Discord mention: <@&ID>
        if part.startswith('<@&') and part.endswith('>'):
            try:
                role_id = int(part[3:-1])
                role = guild.get_role(role_id)
                if role:
                    resolved.append(role)
                    continue
            except ValueError:
                pass

        # Try raw ID (just numbers)
        try:
            role_id = int(cleaned)
            role = guild.get_role(role_id)
            if role:
                resolved.append(role)
                continue
        except ValueError:
            pass

        # Try name match (case-insensitive)
        if cleaned:
            for role in guild.roles:
                if role.name.lower() == cleaned.lower():
                    resolved.append(role)
                    break

    return resolved


async def generate_ticket_pdf(channel: discord.TextChannel, ticket_data: Dict, closed_by: discord.Member, reason: str) -> io.BytesIO:
    """Generate a beautiful PDF transcript of a ticket channel."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Colors
    primary_color = (88, 101, 242)  # Discord Blurple
    dark_bg = (47, 49, 54)          # Discord Dark
    light_text = (255, 255, 255)
    gray_text = (153, 170, 181)
    
    # Header background
    pdf.set_fill_color(*primary_color)
    pdf.rect(0, 0, 210, 50, 'F')
    
    # Header text
    pdf.set_font('Helvetica', 'B', 24)
    pdf.set_text_color(*light_text)
    pdf.set_xy(10, 10)
    pdf.cell(0, 10, f'Ticket Transcript', ln=True)
    
    pdf.set_font('Helvetica', '', 12)
    pdf.set_x(10)
    pdf.cell(0, 8, f'{ticket_data.get("ticket_id", "Unknown")}', ln=True)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_x(10)
    pdf.cell(0, 6, f'Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ln=True)
    
    # Ticket info box
    pdf.set_y(60)
    pdf.set_fill_color(*dark_bg)
    pdf.rect(10, pdf.get_y(), 190, 40, 'F')
    
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(*light_text)
    pdf.set_xy(15, pdf.get_y() + 5)
    pdf.cell(90, 6, f'User ID: {ticket_data.get("user_id", "Unknown")}', ln=False)
    pdf.cell(90, 6, f'Channel: #{channel.name}', ln=True)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(*gray_text)
    pdf.set_x(15)
    pdf.cell(90, 6, f'Created: {ticket_data.get("created_at", "Unknown")}', ln=False)
    pdf.cell(90, 6, f'Status: {ticket_data.get("status", "Unknown")}', ln=True)
    
    pdf.set_x(15)
    pdf.cell(90, 6, f'Closed by: {closed_by.name}', ln=False)
    pdf.cell(90, 6, f'Closed at: {datetime.now().strftime("%Y-%m-%d %H:%M")}', ln=True)
    
    pdf.set_x(15)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.cell(0, 6, f'Reason: {reason}', ln=True)
    
    # Messages section
    pdf.set_y(110)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 10, 'Chat History', ln=True)
    pdf.ln(2)
    
    # Fetch messages
    messages = []
    async for msg in channel.history(limit=1000, oldest_first=True):
        messages.append(msg)
    
    # Render messages
    pdf.set_font('Helvetica', '', 10)
    for msg in messages:
        # Check if we need a new page
        if pdf.get_y() > 260:
            pdf.add_page()
        
        # Timestamp
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(*gray_text)
        timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
        pdf.cell(0, 4, timestamp, ln=True)
        
        # Username
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*primary_color)
        username = msg.author.display_name if hasattr(msg.author, 'display_name') else str(msg.author)
        pdf.cell(0, 5, username, ln=True)
        
        # Message content
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(50, 50, 50)
        
        if msg.content:
            # Word wrap long messages
            content = msg.content
            pdf.multi_cell(0, 5, content)
        elif msg.attachments:
            pdf.set_font('Helvetica', 'I', 9)
            pdf.set_text_color(*gray_text)
            for att in msg.attachments:
                pdf.cell(0, 5, f'[Attachment: {att.filename}]', ln=True)
        else:
            pdf.set_font('Helvetica', 'I', 9)
            pdf.set_text_color(*gray_text)
            pdf.cell(0, 5, '[No text content]', ln=True)
        
        pdf.ln(3)
    
    # Footer
    pdf.set_y(-20)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.set_text_color(*gray_text)
    pdf.cell(0, 10, f'Total messages: {len(messages)} | Page {pdf.page_no()}', align='C')
    
    # Save to bytes
    pdf_bytes = io.BytesIO()
    pdf.output(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes


class TicketPanelView(View):
    def __init__(self, db: Database, guild_id: str, panel_id: int = None):
        super().__init__(timeout=None)
        self.db = db
        self.guild_id = guild_id
        self.panels = db.get_panels(guild_id)
        self.panel_id = panel_id
        
    async def setup(self):
        if self.panel_id:
            # Load buttons only for specific panel
            buttons = self.db.get_panel_buttons(self.panel_id)
            for btn in buttons:
                self.add_item(TicketButton(self.db, btn))
        else:
            # Load buttons for all panels
            for panel in self.panels:
                buttons = self.db.get_panel_buttons(panel['id'])
                for btn in buttons:
                    self.add_item(TicketButton(self.db, btn))


class TicketButton(Button):
    def __init__(self, db: Database, button_data: Dict):
        super().__init__(
            style=get_button_style(button_data['color']),
            label=button_data['label'],
            emoji=button_data['emoji'] if button_data['emoji'] else None,
            custom_id=button_data['custom_id']
        )
        self.db = db
        self.button_data = button_data
    
    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        button_id = self.button_data['id']
        
        max_tickets = self.button_data['max_tickets'] or 3
        current_tickets = self.db.count_user_tickets(user_id, guild_id, button_id)
        
        if current_tickets >= max_tickets:
            await interaction.response.send_message(
                f"❌ Du hast bereits {max_tickets} offene Tickets für diese Kategorie.",
                ephemeral=True
            )
            return
        
        # Check if button uses custom modal (must send modal BEFORE defer)
        if self.button_data.get('use_modal') and self.button_data.get('modal_fields'):
            modal = CustomTicketModal(self.db, self.button_data)
            await interaction.response.send_modal(modal)
            return
        
        # Check if button uses simple question (must send modal BEFORE defer)
        if self.button_data.get('require_question') and self.button_data.get('question_title'):
            modal = TicketSubjectModal(self.db, self.button_data)
            await interaction.response.send_modal(modal)
            return
        
        # No modal needed - defer and create ticket directly
        await interaction.response.defer(ephemeral=True)
        await self.create_ticket(interaction)
    
    async def create_ticket(self, interaction: Interaction, modal_data: Dict = None):
        guild = interaction.guild
        user = interaction.user
        button_data = self.button_data
        
        category = None
        if button_data['category_id']:
            category = guild.get_channel(int(button_data['category_id']))
        
        ticket_count = self.db.increment_ticket_count(str(guild.id))
        ticket_id = f"ticket-{ticket_count:04d}"
        
        overwrites = {
            guild.default_role: PermissionOverwrite(read_messages=False),
            user: PermissionOverwrite(read_messages=True, send_messages=True),
        }
        
        # Support multiple roles with @mention syntax and fallback to defaults
        effective_roles = self.db.get_effective_support_roles(button_data)
        support_roles = parse_role_mentions(effective_roles, guild)
        for support_role in support_roles:
            overwrites[support_role] = PermissionOverwrite(
                read_messages=True, send_messages=True
            )
        
        channel_name = f"{button_data['label'].lower().replace(' ', '-')}-{ticket_count:04d}"
        
        try:
            if category and category.type == ChannelType.forum:
                thread = await category.create_thread(
                    name=channel_name,
                    content=f"🎫 Ticket von {user.mention}\n**Kategorie:** {button_data['label']}"
                )
                channel = thread.thread
            else:
                channel = await guild.create_text_channel(
                    channel_name,
                    overwrites=overwrites,
                    category=category,
                    topic=f"Ticket ID: {ticket_id} | Benutzer: {user.id} | Kategorie: {button_data['label']}"
                )
            
            # Get subject from modal_data or button subject
            subject = None
            if modal_data:
                subject = modal_data.get('subject', '')
            
            self.db.create_ticket(
                ticket_id, str(user.id), str(guild.id),
                str(channel.id), button_data['id'], subject
            )
            
            # Create main embed
            embed = discord.Embed(
                title=f"🎫 {button_data['label']} - {ticket_id}",
                description=f"**Benutzer:** {user.mention}\n**Erstellt:** {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                color=discord.Color.green()
            )
            
            # Add fields from modal data
            if modal_data and modal_data.get('fields'):
                for field in modal_data['fields']:
                    if field['value']:
                        field_name = f"📝 {field['label']}"
                        # Truncate long values for embed
                        field_value = field['value'][:1024] if len(field['value']) > 1024 else field['value']
                        embed.add_field(name=field_name, value=field_value, inline=False)
            
            # Add subject as separate field if it exists
            if subject and not modal_data:
                embed.add_field(name="📝 Betreff", value=subject, inline=False)
            
            if button_data['description']:
                embed.add_field(name="📋 Beschreibung", value=button_data['description'], inline=False)
            
            embed.set_footer(text="Ein Teammitglied wird sich so schnell wie möglich melden.")
            
            view = TicketActionView(str(channel.id), str(user.id))
            
            # Build initial message
            initial_content = f"{user.mention} Willkommen! Dein Ticket wurde erstellt."
            
            # Send ticket info to channel
            await channel.send(
                content=initial_content,
                embed=embed,
                view=view
            )
            
            # Send confirmation to user
            # Check if interaction was already responded to (e.g., from modal submit)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"✅ Dein Ticket wurde erstellt: {channel.mention}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"✅ Dein Ticket wurde erstellt: {channel.mention}",
                    ephemeral=True
                )
            
        except Exception as e:
            error_msg = f"❌ Fehler beim Erstellen des Tickets: {str(e)}"
            if not interaction.response.is_done():
                await interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await interaction.followup.send(error_msg, ephemeral=True)


class TicketSubjectModal(Modal, title="Ticket erstellen"):
    def __init__(self, db: Database, button_data: Dict):
        super().__init__(timeout=300)
        self.db = db
        self.button_data = button_data
        
        self.subject_input = create_text_input(
            label=button_data['question_title'] or "Betreff",
            style=discord.TextStyle.short,
            placeholder=button_data['question_placeholder'] or "Beschreibe kurz dein Anliegen...",
            required=True,
            max_length=200
        )
        self.add_item(self.subject_input)
    
    async def on_submit(self, interaction: Interaction):
        subject = self.subject_input.value
        button = TicketButton(self.db, self.button_data)
        await button.create_ticket(interaction, {'subject': subject, 'fields': []})


class CustomTicketModal(Modal):
    """Custom modal with configurable fields."""
    
    def __init__(self, db: Database, button_data: Dict):
        self.db = db
        self.button_data = button_data
        
        # Parse modal fields from JSON
        modal_fields = []
        if button_data.get('modal_fields'):
            try:
                modal_fields = json.loads(button_data['modal_fields'])
            except json.JSONDecodeError:
                modal_fields = []
        
        # Set modal title
        title = button_data.get('modal_title') or button_data['label']
        super().__init__(title=title, timeout=300)
        
        # Add TextInput fields
        for i, field in enumerate(modal_fields):
            style = discord.TextStyle.paragraph if field.get('style') == 'paragraph' else discord.TextStyle.short
            max_length = 4000 if style == discord.TextStyle.paragraph else 200
            
            text_input = create_text_input(
                label=field.get('label', f'Feld {i+1}'),
                style=style,
                placeholder=field.get('placeholder', ''),
                required=field.get('required', True),
                max_length=max_length,
                custom_id=f"modal_field_{i}"
            )
            self.add_item(text_input)
        
        # Store parsed fields for later use
        self.modal_fields = modal_fields
    
    async def on_submit(self, interaction: Interaction):
        button = TicketButton(self.db, self.button_data)
        
        # Collect all field values
        fields_data = []
        for i, child in enumerate(self.children):
            if i < len(self.modal_fields):
                field = self.modal_fields[i]
                fields_data.append({
                    'label': field.get('label', f'Feld {i+1}'),
                    'value': child.value,
                    'style': field.get('style', 'short')
                })
        
        modal_data = {
            'subject': fields_data[0]['value'] if fields_data else None,
            'fields': fields_data
        }
        
        await button.create_ticket(interaction, modal_data)


class TicketActionView(View):
    def __init__(self, channel_id: str = None, user_id: str = None, claimed_by: str = None):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id
        self.claimed_by = claimed_by
        
        # Update claim button label if already claimed
        if claimed_by:
            for child in self.children:
                if hasattr(child, 'custom_id') and child.custom_id == 'ticket_claim':
                    child.label = f'Claimed by {claimed_by}'
                    child.disabled = True
                    child.style = discord.ButtonStyle.grey
    
    @button(style=discord.ButtonStyle.green, label="Claim", emoji="🎯", custom_id="ticket_claim")
    async def claim_ticket(self, interaction: Interaction, btn: Button):
        await interaction.response.defer(ephemeral=True)
        
        # Check if user has permission (manage_guild or has support role)
        if not interaction.user.guild_permissions.manage_guild:
            ticket = client.db.get_ticket_by_channel(str(interaction.channel.id))
            if ticket:
                button_data = client.db.get_button_by_id(ticket.get('button_id'))
                if button_data:
                    effective_roles = client.db.get_effective_support_roles(button_data)
                    support_roles = parse_role_mentions(effective_roles, interaction.guild)
                    user_role_ids = [r.id for r in interaction.user.roles]
                    has_support_role = any(r.id in user_role_ids for r in support_roles)
                    if not has_support_role:
                        await interaction.followup.send(
                            "❌ Du hast keine Berechtigung dieses Ticket zu claimen.",
                            ephemeral=True
                        )
                        return
        
        # Update the button
        btn.label = f'Claimed by {interaction.user.display_name}'
        btn.disabled = True
        btn.style = discord.ButtonStyle.grey
        
        # Update the message
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        
        # Send notification
        embed = discord.Embed(
            title="🎯 Ticket Claimed",
            description=f"**{interaction.user.mention}** hat dieses Ticket übernommen.",
            color=discord.Color.green()
        )
        embed.timestamp = datetime.now()
        await interaction.channel.send(embed=embed)
        
        await interaction.followup.send(
            "✅ Du hast das Ticket erfolgreich übernommen!",
            ephemeral=True
        )
    
    @button(style=discord.ButtonStyle.red, label="Schließen", emoji="🔒", custom_id="ticket_close")
    async def close_ticket(self, interaction: Interaction, btn: Button):
        # Use interaction data if available (persistent view after restart)
        channel_id = self.channel_id or str(interaction.channel.id)
        user_id = self.user_id or str(interaction.user.id)
        
        modal = CloseTicketModal(channel_id, user_id)
        await interaction.response.send_modal(modal)
    
    @button(style=discord.ButtonStyle.grey, label="Transkript", emoji="📄", custom_id="ticket_transcript")
    async def transcript_ticket(self, interaction: Interaction, btn: Button):
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        ticket = client.db.get_ticket_by_channel(str(channel.id))
        
        if not ticket:
            await interaction.followup.send("❌ Kein Ticket gefunden.", ephemeral=True)
            return
        
        transcript_content = []
        async for msg in channel.history(limit=500, oldest_first=True):
            timestamp = msg.created_at.strftime('%d.%m.%Y %H:%M')
            content = msg.content or '[Kein Text]'
            transcript_content.append(f"[{timestamp}] {msg.author}: {content}")
        
        transcript = "\n".join(transcript_content)
        client.db.save_transcript(ticket['ticket_id'], transcript)
        
        # Send as file
        file = discord.File(
            io.BytesIO(transcript.encode('utf-8')),
            filename=f"transcript_{ticket['ticket_id']}.txt"
        )
        
        await interaction.followup.send(
            "📄 Transkript erstellt:",
            file=file,
            ephemeral=True
        )


class CloseTicketModal(Modal, title="Ticket schließen"):
    def __init__(self, channel_id: str, user_id: str):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.user_id = user_id
        
        self.reason_input = create_text_input(
            label="Grund für das Schließen",
            style=discord.TextStyle.paragraph,
            placeholder="Optional: Gib einen Grund an...",
            required=False,
            max_length=500
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        channel = interaction.channel
        reason = self.reason_input.value or "Kein Grund angegeben"
        
        # Get ticket data from database
        ticket = client.db.get_ticket_by_channel(str(channel.id))
        if not ticket:
            # Fallback: try to get ticket data from DB even if status isn't 'open'
            with client.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(channel.id),))
                row = cursor.fetchone()
                ticket = dict(row) if row else {
                    'ticket_id': f'unknown-{channel.id}',
                    'user_id': self.user_id,
                    'status': 'open',
                    'created_at': 'Unknown'
                }
        
        # Close ticket in database
        client.db.close_ticket(str(channel.id), str(interaction.user.id))
        
        # Generate transcript text for DB
        transcript_content = []
        async for msg in channel.history(limit=500, oldest_first=True):
            timestamp = msg.created_at.strftime('%d.%m.%Y %H:%M')
            content = msg.content or '[Kein Text]'
            transcript_content.append(f"[{timestamp}] {msg.author}: {content}")
        transcript_text = "\n".join(transcript_content)
        client.db.save_transcript(ticket.get('ticket_id', 'unknown'), transcript_text)
        
        # Send closing embed to channel before deletion
        close_embed = discord.Embed(
            title="🔒 Ticket wird geschlossen",
            description=(
                f"**Ticket:** `{ticket.get('ticket_id', 'Unknown')}`\n"
                f"**Geschlossen von:** {interaction.user.mention}\n"
                f"**Grund:** {reason}\n\n"
                "⏳ Transkript wird erstellt und der Kanal wird in 5 Sekunden gelöscht..."
            ),
            color=discord.Color.orange()
        )
        close_embed.timestamp = datetime.now()
        
        try:
            await channel.send(embed=close_embed)
        except Exception:
            pass
        
        # Generate PDF transcript
        try:
            pdf_bytes = await generate_ticket_pdf(channel, ticket, interaction.user, reason)
            pdf_filename = f"transcript_{ticket.get('ticket_id', 'unknown')}.pdf"
            pdf_file = discord.File(pdf_bytes, filename=pdf_filename)
            
            # Send PDF to log channel
            log_channel_id = client.db.get_setting('log_channel_id', '')
            if log_channel_id:
                try:
                    log_channel = interaction.guild.get_channel(int(log_channel_id))
                    if log_channel:
                        log_embed = discord.Embed(
                            title="📋 Ticket Transkript",
                            description=(
                                f"**Ticket:** `{ticket.get('ticket_id', 'Unknown')}`\n"
                                f"**Benutzer:** <@{ticket.get('user_id', 'Unknown')}>\n"
                                f"**Kanal:** #{channel.name}\n"
                                f"**Geschlossen von:** {interaction.user.mention}\n"
                                f"**Grund:** {reason}"
                            ),
                            color=discord.Color.blue()
                        )
                        log_embed.timestamp = datetime.now()
                        log_embed.set_footer(text=f"Geschlossen am {datetime.now().strftime('%d.%m.%Y um %H:%M')}")
                        
                        await log_channel.send(embed=log_embed, file=pdf_file)
                        print(f"📄 PDF transcript sent to log channel for {ticket.get('ticket_id')}")
                except Exception as e:
                    print(f"❌ Error sending PDF to log channel: {e}")
            else:
                print("⚠️ No log channel configured. Set 'log_channel_id' in dashboard settings.")
        except Exception as e:
            print(f"❌ Error generating PDF transcript: {e}")
        
        # Confirm to user
        await interaction.followup.send(
            "✅ Ticket wurde geschlossen. Transkript wurde erstellt und der Kanal wird gleich gelöscht.",
            ephemeral=True
        )
        
        # Wait 5 seconds then delete the channel
        import asyncio
        await asyncio.sleep(5)
        
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}: {reason}")
        except Exception as e:
            print(f"❌ Error deleting ticket channel: {e}")


# ==================== BOT CLASS ====================

class TicketBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.db = Database()
        self.ready_guilds = set()
    
    async def setup_hook(self):
        await self.tree.sync()
        
        for guild in self.guilds:
            self.ready_guilds.add(guild.id)
            panels = self.db.get_panels(str(guild.id))
            for panel in panels:
                view = TicketPanelView(self.db, str(guild.id))
                await view.setup()
                self.add_view(view)
            # NEW: Sync guild channels and roles to DB for dashboard
            await self.sync_guild_data(guild)

    async def sync_guild_data(self, guild: discord.Guild):
        """Sync guild channels and roles to the database for the dashboard."""
        try:
            channels = []
            for ch in guild.channels:
                ch_type = 'text'
                if isinstance(ch, discord.CategoryChannel):
                    ch_type = 'category'
                elif isinstance(ch, discord.ForumChannel):
                    ch_type = 'forum'
                elif isinstance(ch, discord.VoiceChannel):
                    ch_type = 'voice'
                
                category_name = ''
                if hasattr(ch, 'category') and ch.category:
                    category_name = ch.category.name
                
                channels.append({
                    'id': str(ch.id),
                    'name': ch.name,
                    'type': ch_type,
                    'category': category_name
                })
            
            self.db.sync_guild_channels(str(guild.id), channels)
            
            roles = []
            for role in guild.roles:
                if role.name == '@everyone':
                    continue
                roles.append({
                    'id': str(role.id),
                    'name': role.name,
                    'color': f'#{role.color.value:06x}' if role.color else '#99AAB5'
                })
            
            self.db.sync_guild_roles(str(guild.id), roles)
            print(f"📋 Synced {len(channels)} channels & {len(roles)} roles for {guild.name}")
        except Exception as e:
            print(f"❌ Error syncing guild data for {guild.name}: {e}")

    @tasks.loop(seconds=5)
    async def process_send_queue(self):
        """Process pending panel send requests from the dashboard."""
        try:
            pending = self.db.get_pending_sends()
            for item in pending:
                try:
                    guild = self.get_guild(int(item['guild_id']))
                    if not guild:
                        self.db.mark_send_processed(item['id'], 'error', 'Guild nicht gefunden')
                        continue

                    channel = guild.get_channel(int(item['channel_id']))
                    if not channel:
                        self.db.mark_send_processed(item['id'], 'error', 'Kanal nicht gefunden')
                        continue

                    # Build panel embed
                    embed = discord.Embed(
                        title=f"🎫 {item['title']}",
                        description=item['description'],
                        color=discord.Color.blue()
                    )

                    buttons = self.db.get_panel_buttons(item['panel_id'])
                    if buttons:
                        button_text = "\n".join([
                            f"• **{b['label']}**" + (f" - {b['description']}" if b['description'] else "")
                            for b in buttons
                        ])
                        embed.description = f"{item['description']}\n\n{button_text}"

                    if item.get('image_url'):
                        embed.set_image(url=item['image_url'])

                    embed.set_footer(text="Klicke auf einen Button um ein Ticket zu erstellen.")

                    # Create view with buttons
                    view = TicketPanelView(self.db, str(guild.id), item['panel_id'])
                    await view.setup()

                    msg = await channel.send(embed=embed, view=view)

                    # Update panel with message info
                    self.db.update_panel(item['panel_id'], message_id=str(msg.id), channel_id=str(channel.id))
                    self.db.mark_send_processed(item['id'], 'done')
                    print(f"✅ Panel '{item['title']}' sent to #{channel.name} in {guild.name}")

                except Exception as e:
                    self.db.mark_send_processed(item['id'], 'error', str(e))
                    print(f"❌ Error sending panel {item['id']}: {e}")

        except Exception as e:
            print(f"❌ Error in send queue loop: {e}")

    @process_send_queue.before_loop
    async def before_send_queue(self):
        await self.wait_until_ready()


client = TicketBot()


@client.event
async def on_ready():
    print(f"🤖 Bot ist online als {client.user}")
    print(f"📊 Geladen: {len(client.guilds)} Server")
    
    for guild in client.guilds:
        # Register ticket panel views (persistent for sent panels)
        panels = client.db.get_panels(str(guild.id))
        for panel in panels:
            view = TicketPanelView(client.db, str(guild.id))
            await view.setup()
            if panel['message_id']:
                try:
                    client.add_view(view, message_id=int(panel['message_id']))
                except Exception:
                    client.add_view(view)
            else:
                client.add_view(view)
        
        # Sync guild channels and roles to DB for dashboard
        await client.sync_guild_data(guild)

    # Register persistent TicketActionView for ticket close/transcript buttons
    # This single registration covers ALL open tickets because the buttons use fixed custom_ids
    persistent_ticket_view = TicketActionView("0", "0")
    client.add_view(persistent_ticket_view)

    # Start the panel send queue processor
    if not client.process_send_queue.is_running():
        client.process_send_queue.start()


# ==================== SLASH COMMANDS ====================

@client.tree.command(name="ticket-send", description="Sendet ein Ticket-Panel aus dem Dashboard")
@app_commands.describe(channel="Der Kanal für das Panel")
async def send_panel(interaction: Interaction, channel: discord.TextChannel):
    """Send a ticket panel from database to Discord."""
    
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung dafür.",
            ephemeral=True
        )
        return
    
    # Get latest panel from database
    panels = client.db.get_panels(str(interaction.guild.id))
    if not panels:
        await interaction.response.send_message(
            "❌ Kein Panel im Dashboard gefunden. Erstelle zuerst ein Panel im Dashboard.",
            ephemeral=True
        )
        return
    
    panel = panels[0]
    buttons = client.db.get_panel_buttons(panel['id'])
    
    # Create view with buttons for this panel
    view = TicketPanelView(client.db, str(interaction.guild.id), panel['id'])
    await view.setup()
    
    # Create embed
    embed = discord.Embed(
        title=f"🎫 {panel['title']}",
        description=panel['description'],
        color=discord.Color.blue()
    )
    
    # Add button list to description
    if buttons:
        button_text = "\n".join([f"• **{b['label']}**" + (f" - {b['description']}" if b['description'] else "") for b in buttons])
        embed.description = f"{panel['description']}\n\n{button_text}"
    
    if panel.get('image_url'):
        embed.set_image(url=panel['image_url'])
    
    embed.set_footer(text="Klicke auf einen Button um ein Ticket zu erstellen.")
    
    # Send message
    msg = await channel.send(embed=embed, view=view)
    
    # Update panel with message info
    client.db.update_panel(panel['id'], message_id=str(msg.id), channel_id=str(channel.id))
    
    await interaction.response.send_message(
        f"✅ Panel '{panel['title']}' wurde in {channel.mention} gesendet!",
        ephemeral=True
    )


@client.tree.command(name="ticket-add", description="Fügt einen Button zum letzten Panel hinzu")
@app_commands.describe(
    label="Beschriftung des Buttons",
    description="Beschreibung der Kategorie",
    category="Kategorie für neue Tickets (optional)",
    support_role="Support-Rolle (optional)",
    emoji="Emoji für den Button",
    button_image="URL zu einem Bild für den Button (optional)"
)
async def add_button(interaction: Interaction,
                     label: str,
                     description: str = None,
                     category: discord.CategoryChannel = None,
                     support_role: discord.Role = None,
                     emoji: str = None,
                     button_color: str = "blurple",
                     question_title: str = None,
                     question_placeholder: str = None,
                     require_question: bool = False,
                     max_tickets: int = 3,
                     button_image: str = None):
    """Add a button to the ticket panel."""
    
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung dafür.",
            ephemeral=True
        )
        return
    
    panels = client.db.get_panels(str(interaction.guild.id))
    if not panels:
        await interaction.response.send_message(
            "❌ Kein Panel gefunden. Erstelle zuerst ein Panel mit /ticket-panel.",
            ephemeral=True
        )
        return
    
    panel = panels[0]
    
    custom_id = f"ticket_{panel['id']}_{label.lower().replace(' ', '_')}_{interaction.id}"
    
    button_id = client.db.create_button(
        panel_id=panel['id'],
        label=label,
        custom_id=custom_id,
        emoji=emoji,
        color=button_color,
        category_id=str(category.id) if category else None,
        support_role_id=str(support_role.id) if support_role else None,
        description=description,
        question_title=question_title,
        question_placeholder=question_placeholder,
        require_question=1 if require_question else 0,
        max_tickets=max_tickets,
        image_url=button_image
    )
    
    view = TicketPanelView(client.db, str(interaction.guild.id))
    await view.setup()
    client.add_view(view)
    
    if panel['message_id']:
        try:
            channel_obj = interaction.guild.get_channel(int(panel['channel_id']))
            message = await channel_obj.fetch_message(int(panel['message_id']))
            
            buttons = client.db.get_panel_buttons(panel['id'])
            button_text = "\n".join([f"• **{b['label']}**" + (f" - {b['description']}" if b['description'] else "") for b in buttons])
            
            embed = discord.Embed(
                title=f"🎫 {panel['title']}",
                description=f"{panel['description']}\n\n{button_text}",
                color=discord.Color.blue()
            )
            embed.set_footer(text="Klicke auf einen Button um ein Ticket zu erstellen.")
            
            await message.edit(embed=embed, view=view)
        except:
            pass
    
    await interaction.response.send_message(
        f"✅ Button '{label}' wurde zum Panel hinzugefügt!",
        ephemeral=True
    )


@client.tree.command(name="ticket-close", description="Schließt das aktuelle Ticket")
async def close_ticket(interaction: Interaction, reason: str = None):
    """Close the current ticket."""
    
    channel = interaction.channel
    ticket = client.db.get_ticket_by_channel(str(channel.id))
    
    if not ticket:
        await interaction.response.send_message(
            "❌ Dies ist kein Ticket-Kanal.",
            ephemeral=True
        )
        return
    
    user = interaction.user
    can_close = user.guild_permissions.manage_guild or str(user.id) == ticket['user_id']
    
    if not can_close:
        await interaction.response.send_message(
            "❌ Du kannst dieses Ticket nicht schließen.",
            ephemeral=True
        )
        return
    
    await interaction.response.defer(ephemeral=True)
    
    reason = reason or "Kein Grund angegeben"
    
    # Close ticket in database
    client.db.close_ticket(str(channel.id), str(user.id))
    
    # Save transcript
    transcript_content = []
    async for msg in channel.history(limit=500, oldest_first=True):
        timestamp = msg.created_at.strftime('%d.%m.%Y %H:%M')
        content = msg.content or '[Kein Text]'
        transcript_content.append(f"[{timestamp}] {msg.author}: {content}")
    transcript_text = "\n".join(transcript_content)
    client.db.save_transcript(ticket['ticket_id'], transcript_text)
    
    # Closing embed
    close_embed = discord.Embed(
        title="🔒 Ticket wird geschlossen",
        description=(
            f"**Ticket:** `{ticket['ticket_id']}`\n"
            f"**Geschlossen von:** {user.mention}\n"
            f"**Grund:** {reason}\n\n"
            "⏳ Transkript wird erstellt und der Kanal wird in 5 Sekunden gelöscht..."
        ),
        color=discord.Color.orange()
    )
    close_embed.timestamp = datetime.now()
    
    try:
        await channel.send(embed=close_embed)
    except Exception:
        pass
    
    # Generate and send PDF to log channel
    try:
        pdf_bytes = await generate_ticket_pdf(channel, ticket, user, reason)
        pdf_file = discord.File(pdf_bytes, filename=f"transcript_{ticket['ticket_id']}.pdf")
        
        log_channel_id = client.db.get_setting('log_channel_id', '')
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel:
                log_embed = discord.Embed(
                    title="📋 Ticket Transkript",
                    description=(
                        f"**Ticket:** `{ticket['ticket_id']}`\n"
                        f"**Benutzer:** <@{ticket['user_id']}>\n"
                        f"**Kanal:** #{channel.name}\n"
                        f"**Geschlossen von:** {user.mention}\n"
                        f"**Grund:** {reason}"
                    ),
                    color=discord.Color.blue()
                )
                log_embed.timestamp = datetime.now()
                await log_channel.send(embed=log_embed, file=pdf_file)
    except Exception as e:
        print(f"❌ Error generating/sending PDF: {e}")
    
    await interaction.followup.send(
        "✅ Ticket geschlossen. Kanal wird in 5 Sekunden gelöscht.",
        ephemeral=True
    )
    
    # Delete channel after delay
    import asyncio
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Ticket closed by {user}: {reason}")
    except Exception as e:
        print(f"❌ Error deleting channel: {e}")


@client.tree.command(name="ticket-stats", description="Zeigt Ticket-Statistiken")
async def ticket_stats(interaction: Interaction):
    """Show ticket statistics."""
    
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung dafür.",
            ephemeral=True
        )
        return
    
    tickets = client.db.get_all_tickets(str(interaction.guild.id))
    
    total = len(tickets)
    open_tickets = len([t for t in tickets if t['status'] == 'open'])
    closed_tickets = len([t for t in tickets if t['status'] == 'closed'])
    
    embed = discord.Embed(
        title="📊 Ticket-Statistiken",
        color=discord.Color.green()
    )
    embed.add_field(name="Gesamt", value=str(total), inline=True)
    embed.add_field(name="Offen", value=str(open_tickets), inline=True)
    embed.add_field(name="Geschlossen", value=str(closed_tickets), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(name="ticket-delete", description="Löscht ein Ticket-Panel")
@app_commands.describe(panel_id="Die ID des Panels")
async def delete_panel(interaction: Interaction, panel_id: int):
    """Delete a ticket panel."""
    
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung dafür.",
            ephemeral=True
        )
        return
    
    client.db.delete_panel(panel_id)
    
    await interaction.response.send_message(
        "✅ Panel wurde gelöscht.",
        ephemeral=True
    )


# ==================== MAIN ====================

if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_TOKEN nicht in .env gefunden!")
        exit(1)
    
    client.run(TOKEN)
