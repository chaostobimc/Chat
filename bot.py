"""
Discord Ticket Bot - Premium Edition
A professional ticket management system with web dashboard.
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

import discord
from discord import (
    app_commands, 
    TextInput,
    Interaction,
    ChannelType,
    PermissionOverwrite
)
from discord.ui import View, button, Button, Modal
from dotenv import load_dotenv

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
        await interaction.response.defer(ephemeral=True)
        
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        button_id = self.button_data['id']
        
        max_tickets = self.button_data['max_tickets'] or 3
        current_tickets = self.db.count_user_tickets(user_id, guild_id, button_id)
        
        if current_tickets >= max_tickets:
            await interaction.followup.send(
                f"❌ Du hast bereits {max_tickets} offene Tickets für diese Kategorie.",
                ephemeral=True
            )
            return
        
        # Check if button uses custom modal
        if self.button_data.get('use_modal') and self.button_data.get('modal_fields'):
            modal = CustomTicketModal(self.db, self.button_data)
            await interaction.response.send_modal(modal)
        # Check if button uses simple question
        elif self.button_data.get('require_question') and self.button_data.get('question_title'):
            modal = TicketSubjectModal(self.db, self.button_data)
            await interaction.response.send_modal(modal)
        else:
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
        
        if button_data['support_role_id']:
            support_role = guild.get_role(int(button_data['support_role_id']))
            if support_role:
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
            
            await interaction.followup.send(
                f"✅ Dein Ticket wurde erstellt: {channel.mention}",
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Fehler beim Erstellen des Tickets: {str(e)}",
                ephemeral=True
            )


class TicketSubjectModal(Modal, title="Ticket erstellen"):
    def __init__(self, db: Database, button_data: Dict):
        super().__init__(timeout=300)
        self.db = db
        self.button_data = button_data
        
        self.subject_input = TextInput(
            label=button_data['question_title'] or "Betreff",
            placeholder=button_data['question_placeholder'] or "Beschreibe kurz dein Anliegen...",
            style=discord.TextStyle.short,
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
            
            text_input = TextInput(
                label=field.get('label', f'Feld {i+1}'),
                placeholder=field.get('placeholder', ''),
                style=style,
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
    def __init__(self, channel_id: str, user_id: str):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.user_id = user_id
    
    @button(style=discord.ButtonStyle.red, label="Schließen", emoji="🔒", custom_id="ticket_close")
    async def close_ticket(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(
            CloseTicketModal(self.channel_id, self.user_id)
        )
    
    @button(style=discord.ButtonStyle.grey, label="Transkript", emoji="📄", custom_id="ticket_transcript")
    async def transcript_ticket(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(
            "⏳ Transkript wird erstellt...",
            ephemeral=True
        )


class CloseTicketModal(Modal, title="Ticket schließen"):
    def __init__(self, channel_id: str, user_id: str):
        super().__init__(timeout=300)
        self.channel_id = channel_id
        self.user_id = user_id
        
        self.reason_input = TextInput(
            label="Grund für das Schließen",
            placeholder="Optional: Gib einen Grund an...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: Interaction):
        channel = interaction.channel
        reason = self.reason_input.value or "Kein Grund angegeben"
        
        embed = discord.Embed(
            title="🔒 Ticket geschlossen",
            description=f"**Ticket-ID:** `{self.channel_id}`\n**Geschlossen von:** {interaction.user.mention}\n**Grund:** {reason}",
            color=discord.Color.orange()
        )
        embed.timestamp = datetime.now()
        
        await channel.send(embed=embed)
        await channel.set_permissions(
            interaction.guild.default_role,
            overwrite=PermissionOverwrite(read_messages=False)
        )
        
        await interaction.response.send_message(
            "✅ Ticket wurde geschlossen.",
            ephemeral=True
        )


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


client = TicketBot()


@client.event
async def on_ready():
    print(f"🤖 Bot ist online als {client.user}")
    print(f"📊 Geladen: {len(client.guilds)} Server")
    
    for guild in client.guilds:
        panels = client.db.get_panels(str(guild.id))
        for panel in panels:
            view = TicketPanelView(client.db, str(guild.id))
            await view.setup()
            client.add_view(view, message_id=int(panel['message_id']) if panel['message_id'] else None)


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
    
    client.db.close_ticket(str(channel.id), str(user.id))
    
    transcript_content = []
    async for msg in channel.history(limit=500):
        transcript_content.append(f"[{msg.created_at.strftime('%d.%m.%Y %H:%M')}] {msg.author}: {msg.content}")
    
    transcript = "\n".join(transcript_content)
    client.db.save_transcript(ticket['ticket_id'], transcript)
    
    await channel.set_permissions(
        interaction.guild.default_role,
        overwrite=PermissionOverwrite(read_messages=False)
    )
    
    embed = discord.Embed(
        title="🔒 Ticket geschlossen",
        description=f"**Ticket-ID:** `{ticket['ticket_id']}`\n**Geschlossen von:** {user.mention}\n**Grund:** {reason or 'Nicht angegeben'}",
        color=discord.Color.orange()
    )
    embed.timestamp = datetime.now()
    
    await channel.send(embed=embed)
    
    await interaction.response.send_message(
        "✅ Ticket wurde geschlossen.",
        ephemeral=True
    )


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
