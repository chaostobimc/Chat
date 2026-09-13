"""
Spawner Price List Module for Discord Ticket Bot.
Adds /spawner, /sendspawner, /updateprice, /spawnertext, /removespawner commands.
"""

import asyncio
import discord
from discord import app_commands, Interaction
from discord.ui import View, Button, button
from datetime import datetime
from typing import Optional, Dict, List

from utils import is_admin


def parse_price(price_input: str) -> str:
    """
    Parse a price string with optional suffixes into a formatted number string.
    Supports: K (thousand), M (million), B (billion), T (trillion)
    Examples: '5M' -> '5.000.000', '500K' -> '500.000', '1.5M' -> '1.500.000'
    """
    text = price_input.strip().replace(' ', '').replace('$', '').replace('€', '')

    suffixes = {
        'k': 1_000,
        'm': 1_000_000,
        'b': 1_000_000_000,
        't': 1_000_000_000_000,
    }

    multiplier = 1
    for suffix, mult in suffixes.items():
        if text.lower().endswith(suffix):
            text = text[:-1]
            multiplier = mult
            break

    # Smart decimal detection:
    # If suffix is used (K/M/B/T), treat . and , as decimal separator
    # If no suffix, check if . or , looks like thousands separator
    if multiplier > 1:
        # With suffix: . and , are always decimal separators
        clean = text.replace('.', '').replace(',', '.')
        # But if there were multiple dots (like 1.000.000), they were thousands separators
        if text.count('.') > 1:
            clean = text.replace('.', '').replace(',', '.')
        elif text.count(',') > 1:
            clean = text.replace(',', '')
        else:
            clean = text.replace('.', '.').replace(',', '.')
    else:
        # Without suffix: try to detect format
        # "1.000.000" -> dots are thousands separators
        # "1,5" -> comma is decimal separator (German)
        # "1.5" -> dot is decimal separator (English)
        if text.count('.') > 1:
            # Multiple dots = thousands separators (1.000.000)
            clean = text.replace('.', '').replace(',', '.')
        elif text.count(',') > 1:
            # Multiple commas = thousands separators (1,000,000)
            clean = text.replace(',', '')
        else:
            # Single . or , = decimal separator
            clean = text.replace(',', '.')

    try:
        value = float(clean) * multiplier
        if value == int(value):
            value = int(value)
            return f"{value:,}".replace(",", ".")
        else:
            return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return price_input  # Return as-is if not parseable


# ==================== SPAWNER VIEWS ====================

class SpawnerTradeView(View):
    """View with Buy/Sell buttons that create tickets."""

    def __init__(self, db, guild_id: str):
        super().__init__(timeout=None)
        self.db = db
        self.guild_id = guild_id

    @button(style=discord.ButtonStyle.green, label="Kaufen", emoji="🛒", custom_id="spawner_buy")
    async def buy_spawner(self, interaction: Interaction, btn: Button):
        await interaction.response.send_modal(SpawnerTradeModal(self.db, self.guild_id, "buy"))

    @button(style=discord.ButtonStyle.red, label="Verkaufen", emoji="💰", custom_id="spawner_sell")
    async def sell_spawner(self, interaction: Interaction, btn: Button):
        await interaction.response.send_modal(SpawnerTradeModal(self.db, self.guild_id, "sell"))


class SpawnerTradeModal(discord.ui.Modal):
    """Modal for buy/sell spawner trade requests."""

    def __init__(self, db, guild_id: str, trade_type: str):
        self.db = db
        self.guild_id = guild_id
        self.trade_type = trade_type

        title = "Spawner Kaufen" if trade_type == "buy" else "Spawner Verkaufen"
        super().__init__(title=title, timeout=300)

        # Import helper here to avoid circular imports
        from bot import create_text_input

        self.spawner_name = create_text_input(
            label="Welcher Spawner?",
            placeholder="Name des Spawners...",
            required=True,
            max_length=100
        )
        self.amount = create_text_input(
            label="Anzahl",
            placeholder="Wie viele?",
            required=True,
            max_length=10
        )
        self.extra_info = create_text_input(
            label="Zusätzliche Info (optional)",
            placeholder="Weitere Details...",
            required=False,
            max_length=500
        )
        self.add_item(self.spawner_name)
        self.add_item(self.amount)
        self.add_item(self.extra_info)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        user = interaction.user

        trade_label = "Kaufanfrage" if self.trade_type == "buy" else "Verkaufsanfrage"
        emoji = "🛒" if self.trade_type == "buy" else "💰"

        # Get spawner trade category from settings
        category_id = self.db.get_setting('spawner_trade_category_id', '')
        category = None
        if category_id:
            category = guild.get_channel(int(category_id))

        # Create ticket
        from bot import parse_role_mentions, PermissionOverwrite, ChannelType, discord as _discord

        ticket_count = self.db.increment_ticket_count(str(guild.id))
        ticket_id = f"ticket-{ticket_count:04d}"

        overwrites = {
            guild.default_role: PermissionOverwrite(read_messages=False),
            user: PermissionOverwrite(read_messages=True, send_messages=True),
        }

        # Add support roles
        default_roles = self.db.get_default_support_roles()
        if default_roles:
            support_roles = parse_role_mentions(default_roles, guild)
            for role in support_roles:
                overwrites[role] = PermissionOverwrite(
                    read_messages=True, send_messages=True
                )

        prefix = "kauf" if self.trade_type == "buy" else "verkauf"
        channel_name = f"{prefix}-{self.spawner_name.value.lower().replace(' ', '-')}-{ticket_count:04d}"

        try:
            channel = await guild.create_text_channel(
                channel_name,
                overwrites=overwrites,
                category=category,
                topic=f"Ticket ID: {ticket_id} | {trade_label} | Benutzer: {user.id}"
            )

            # Create ticket in DB (button_id=0 for spawner tickets)
            subject = f"{trade_label}: {self.spawner_name.value} x{self.amount.value}"
            self.db.create_ticket(
                ticket_id, str(user.id), str(guild.id),
                str(channel.id), 0, subject
            )

            # Create embed
            embed = discord.Embed(
                title=f"{emoji} {trade_label} - {ticket_id}",
                description=(
                    f"**Benutzer:** {user.mention}\n"
                    f"**Spawner:** {self.spawner_name.value}\n"
                    f"**Anzahl:** {self.amount.value}\n"
                    f"**Erstellt:** {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                ),
                color=discord.Color.green() if self.trade_type == "buy" else discord.Color.gold()
            )

            if self.extra_info.value:
                embed.add_field(name="📝 Details", value=self.extra_info.value, inline=False)

            embed.set_footer(text="Ein Teammitglied wird sich so schnell wie möglich melden.")

            from bot import TicketActionView
            view = TicketActionView(str(channel.id), str(user.id))

            await channel.send(
                content=f"{user.mention} Deine {trade_label} wurde erstellt!",
                embed=embed,
                view=view
            )

            await interaction.followup.send(
                f"✅ Deine {trade_label} wurde erstellt: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            await interaction.followup.send(
                f"❌ Fehler beim Erstellen des Tickets: {str(e)}",
                ephemeral=True
            )


class SpawnerTextEditView(View):
    """View for confirming/cancelling spawner text edits."""

    def __init__(self, db, user_id: int, new_text: str):
        super().__init__(timeout=120)
        self.db = db
        self.user_id = user_id
        self.new_text = new_text
        self.result = None  # 'confirm' or 'cancel'

    @button(style=discord.ButtonStyle.green, label="Übernehmen", emoji="✅", custom_id="spawner_text_confirm")
    async def confirm(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das bestätigen.", ephemeral=True)
            return
        self.result = 'confirm'
        self.db.set_setting('spawner_header_text', self.new_text)
        for child in self.children:
            child.disabled = True
        btn.label = "✅ Übernommen!"
        await interaction.response.edit_message(view=self)
        self.stop()

    @button(style=discord.ButtonStyle.red, label="Abbrechen", emoji="❌", custom_id="spawner_text_cancel")
    async def cancel(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das abbrechen.", ephemeral=True)
            return
        self.result = 'cancel'
        for child in self.children:
            child.disabled = True
        btn.label = "❌ Abgebrochen"
        await interaction.response.edit_message(view=self)
        self.stop()


# ==================== HELPER FUNCTIONS ====================

def build_spawner_embed(db, guild_id: str) -> discord.Embed:
    """Build the spawner price list embed."""
    header_text = db.get_setting('spawner_header_text', '')
    spawners = db.get_spawners(guild_id)

    embed = discord.Embed(
        title="🏷️ Spawner Preisliste",
        color=discord.Color.from_rgb(88, 101, 242)
    )

    # Add custom header text if set
    if header_text:
        embed.description = header_text

    if not spawners:
        embed.add_field(
            name="Keine Spawner",
            value="Es wurden noch keine Spawner hinzugefügt.",
            inline=False
        )
    else:
        # Build the price list
        lines = []
        for i, sp in enumerate(spawners, 1):
            lines.append(f"**{i}.** {sp['name']} — `{sp['price']}$`")

        # Split into chunks if too long (Discord limit is 1024 per field)
        chunk = ""
        field_count = 0
        for line in lines:
            if len(chunk) + len(line) + 1 > 1024:
                field_count += 1
                embed.add_field(
                    name="Spawner" if field_count == 1 else f"Spawner (Fortsetzung {field_count})",
                    value=chunk.strip(),
                    inline=False
                )
                chunk = ""
            chunk += line + "\n"

        if chunk:
            field_count += 1
            embed.add_field(
                name="Spawner" if field_count == 1 else f"Spawner (Fortsetzung {field_count})",
                value=chunk.strip(),
                inline=False
            )

    embed.set_footer(text=f"Letzte Aktualisierung: {datetime.now().strftime('%d.%m.%Y %H:%M')} • {len(spawners)} Spawner")
    return embed


async def update_spawner_message(db, guild: discord.Guild):
    """Update the sent spawner list message in Discord."""
    channel_id = db.get_setting('spawner_list_channel_id', '')
    message_id = db.get_setting('spawner_list_message_id', '')

    if not channel_id or not message_id:
        return False

    try:
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return False

        message = await channel.fetch_message(int(message_id))
        embed = build_spawner_embed(db, str(guild.id))
        view = SpawnerTradeView(db, str(guild.id))
        await message.edit(embed=embed, view=view)
        return True
    except Exception as e:
        print(f"❌ Error updating spawner message: {e}")
        return False


async def spawner_name_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice]:
    """Autocomplete for spawner names."""
    # We need access to the client's db
    try:
        db = interaction.client.db
        guild_id = str(interaction.guild.id) if interaction.guild else None
        spawners = db.get_spawners(guild_id)
        choices = []
        for sp in spawners:
            if current.lower() in sp['name'].lower():
                choices.append(app_commands.Choice(name=sp['name'], value=sp['name']))
                if len(choices) >= 25:  # Discord limit
                    break
        return choices
    except Exception:
        return []


# ==================== REGISTER COMMANDS ====================

def register_spawner_commands(client):
    """Register all spawner-related slash commands."""

    @client.tree.command(name="spawner", description="Fügt einen Spawner zur Preisliste hinzu")
    @app_commands.describe(
        name="Name des Spawners",
        preis="Preis des Spawners (z.B. 500000 oder 500k)"
    )
    async def add_spawner(interaction: Interaction, name: str, preis: str):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        # Check if spawner already exists
        existing = client.db.get_spawner_by_name(guild_id, name)
        if existing:
            await interaction.response.send_message(
                f"⚠️ Spawner **{name}** existiert bereits mit dem Preis `{existing['price']}$`.\n"
                f"Nutze `/updateprice` um den Preis zu ändern.",
                ephemeral=True
            )
            return

        client.db.add_spawner(guild_id, name, parse_price(preis))

        # Update sent message if exists
        await update_spawner_message(client.db, interaction.guild)

        embed = discord.Embed(
            title="✅ Spawner hinzugefügt",
            description=f"**Name:** {name}\n**Preis:** `{parse_price(preis)}$`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="sendspawner", description="Sendet die Spawner-Preisliste in einen Kanal")
    @app_commands.describe(channel="Der Kanal für die Preisliste")
    async def send_spawner_list(interaction: Interaction, channel: discord.TextChannel):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        # Build embed
        embed = build_spawner_embed(client.db, guild_id)

        # Create trade view
        view = SpawnerTradeView(client.db, guild_id)

        # Send message
        msg = await channel.send(embed=embed, view=view)

        # Save channel and message IDs
        client.db.set_setting('spawner_list_channel_id', str(channel.id))
        client.db.set_setting('spawner_list_message_id', str(msg.id))
        client.db.set_setting('spawner_list_guild_id', guild_id)

        # Register persistent view
        client.add_view(view)

        await interaction.response.send_message(
            f"✅ Spawner-Preisliste wurde in {channel.mention} gesendet!",
            ephemeral=True
        )

    @client.tree.command(name="updateprice", description="Aktualisiert den Preis eines Spawners")
    @app_commands.describe(
        name="Name des Spawners",
        neuer_preis="Der neue Preis"
    )
    @app_commands.autocomplete(name=spawner_name_autocomplete)
    async def update_price(interaction: Interaction, name: str, neuer_preis: str):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        # Check if spawner exists
        existing = client.db.get_spawner_by_name(guild_id, name)
        if not existing:
            await interaction.response.send_message(
                f"❌ Spawner **{name}** nicht gefunden.\n"
                f"Nutze `/spawner` um einen neuen Spawner hinzuzufügen.",
                ephemeral=True
            )
            return

        old_price = existing['price']
        parsed_price = parse_price(neuer_preis)
        client.db.update_spawner_price(guild_id, name, parsed_price)

        # Update sent message
        await update_spawner_message(client.db, interaction.guild)

        # Send price update notification to the spawner channel
        channel_id = client.db.get_setting('spawner_list_channel_id', '')
        if channel_id:
            try:
                spawner_channel = interaction.guild.get_channel(int(channel_id))
                if spawner_channel:
                    update_embed = discord.Embed(
                        title="🔄 Preis aktualisiert!",
                        description=(
                            f"**Spawner:** {name}\n"
                            f"**Alter Preis:** ~~`{old_price}$`~~\n"
                            f"**Neuer Preis:** `{parsed_price}$`\n"
                            f"**Geändert von:** {interaction.user.mention}"
                        ),
                        color=discord.Color.gold()
                    )
                    update_embed.timestamp = datetime.now()
                    await spawner_channel.send(embed=update_embed)
            except Exception as e:
                print(f"❌ Error sending price update: {e}")

        embed = discord.Embed(
            title="✅ Preis aktualisiert",
            description=(
                f"**Spawner:** {name}\n"
                f"**Alter Preis:** ~~`{old_price}$`~~\n"
                f"**Neuer Preis:** `{parsed_price}$`"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="removespawner", description="Entfernt einen Spawner aus der Preisliste")
    @app_commands.describe(name="Name des Spawners")
    @app_commands.autocomplete(name=spawner_name_autocomplete)
    async def remove_spawner(interaction: Interaction, name: str):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        existing = client.db.get_spawner_by_name(guild_id, name)
        if not existing:
            await interaction.response.send_message(
                f"❌ Spawner **{name}** nicht gefunden.",
                ephemeral=True
            )
            return

        client.db.remove_spawner(guild_id, name)
        await update_spawner_message(client.db, interaction.guild)

        embed = discord.Embed(
            title="🗑️ Spawner entfernt",
            description=f"**{name}** wurde aus der Preisliste entfernt.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="spawnertext", description="Setzt den Header-Text über der Spawner-Preisliste")
    async def set_spawner_text(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        current_text = client.db.get_setting('spawner_header_text', '')

        # Send instruction message
        instruction_embed = discord.Embed(
            title="📝 Spawner-Text bearbeiten",
            description=(
                "Sende jetzt deine **neue Nachricht** in diesen Kanal.\n"
                "Der Bot wird sie kopieren und als Header-Text verwenden.\n\n"
                "**Tipp:** Du kannst Discord-Formatierung nutzen:\n"
                "`**fett**` → **fett**\n"
                "`*kursiv*` → *kursiv*\n"
                "`__unterstrichen__` → __unterstrichen__\n"
                "`> Zitat` → Zitat\n\n"
                "⏱️ Du hast **60 Sekunden** Zeit."
            ),
            color=discord.Color.blue()
        )

        if current_text:
            instruction_embed.add_field(
                name="📋 Aktueller Text",
                value=current_text[:500] + ("..." if len(current_text) > 500 else ""),
                inline=False
            )

        await interaction.response.send_message(embed=instruction_embed, ephemeral=True)

        # Wait for the user's next message in this channel
        def check(msg):
            return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id

        try:
            user_msg = await client.wait_for('message', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "⏱️ Zeit abgelaufen. Versuche es erneut mit `/spawnertext`.",
                ephemeral=True
            )
            return

        new_text = user_msg.content

        # Delete the user's message
        try:
            await user_msg.delete()
        except Exception:
            pass

        # Show preview and ask for confirmation
        preview_embed = discord.Embed(
            title="👀 Vorschau - Neuer Spawner-Text",
            description=new_text,
            color=discord.Color.blue()
        )
        preview_embed.set_footer(text="Möchtest du diesen Text übernehmen?")

        view = SpawnerTextEditView(client.db, interaction.user.id, new_text)
        msg = await interaction.followup.send(embed=preview_embed, view=view, ephemeral=True)

        # Wait for the view to be interacted with
        await view.wait()

        if view.result == 'confirm':
            # Update the sent spawner message
            await update_spawner_message(client.db, interaction.guild)
            await interaction.followup.send(
                "✅ Text wurde übernommen und die Spawner-Liste aktualisiert!",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Änderung wurde abgebrochen. Der alte Text bleibt bestehen.",
                ephemeral=True
            )

    @client.tree.command(name="spawnertrade-category", description="Setzt die Kategorie für Kauf-/Verkauf-Tickets")
    @app_commands.describe(category="Die Kategorie für Spawner-Trade-Tickets")
    async def set_spawner_trade_category(interaction: Interaction, category: discord.CategoryChannel):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        client.db.set_setting('spawner_trade_category_id', str(category.id))

        await interaction.response.send_message(
            f"✅ Kategorie für Spawner-Trade-Tickets wurde auf **{category.name}** gesetzt.",
            ephemeral=True
        )

    @client.tree.command(name="clearspawners", description="Löscht ALLE Spawner aus der Preisliste")
    async def clear_all_spawners(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        spawners = client.db.get_spawners(guild_id)

        if not spawners:
            await interaction.response.send_message(
                "ℹ️ Es gibt keine Spawner zum Löschen.",
                ephemeral=True
            )
            return

        # Show confirmation with buttons
        confirm_view = ConfirmClearView(client.db, interaction.user.id, guild_id)
        embed = discord.Embed(
            title="⚠️ Alle Spawner löschen?",
            description=(
                f"Du bist dabei **{len(spawners)} Spawner** unwiderruflich zu löschen.\n\n"
                "Dies kann nicht rückgängig gemacht werden!"
            ),
            color=discord.Color.red()
        )

        # List spawner that will be deleted
        names = "\n".join([f"• {sp['name']} (`{sp['price']}$`)" for sp in spawners[:20]])
        if len(spawners) > 20:
            names += f"\n• ... und {len(spawners) - 20} weitere"
        embed.add_field(name="Spawner die gelöscht werden:", value=names, inline=False)

        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        await confirm_view.wait()

    @client.tree.command(name="clearspawnertext", description="Entfernt den Header-Text über der Preisliste")
    async def clear_spawner_text(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        current_text = client.db.get_setting('spawner_header_text', '')
        if not current_text:
            await interaction.response.send_message(
                "ℹ️ Es ist kein Header-Text gesetzt.",
                ephemeral=True
            )
            return

        client.db.set_setting('spawner_header_text', '')
        await update_spawner_message(client.db, interaction.guild)

        embed = discord.Embed(
            title="🗑️ Header-Text entfernt",
            description="Der Text über der Spawner-Preisliste wurde gelöscht.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="deletespawnerlist", description="Löscht die gesendete Preisliste aus dem Discord-Kanal")
    async def delete_spawner_list_message(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        channel_id = client.db.get_setting('spawner_list_channel_id', '')
        message_id = client.db.get_setting('spawner_list_message_id', '')

        if not channel_id or not message_id:
            await interaction.response.send_message(
                "ℹ️ Es wurde keine Preisliste gesendet.",
                ephemeral=True
            )
            return

        try:
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                message = await channel.fetch_message(int(message_id))
                await message.delete()
        except Exception as e:
            print(f"⚠️ Could not delete message (already deleted?): {e}")

        # Clear stored IDs
        client.db.set_setting('spawner_list_channel_id', '')
        client.db.set_setting('spawner_list_message_id', '')

        embed = discord.Embed(
            title="🗑️ Preisliste gelöscht",
            description="Die Spawner-Preisliste wurde aus dem Kanal entfernt.\nDie Spawner-Daten bleiben erhalten.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="spawnerlist", description="Zeigt alle Spawner in der Datenbank an")
    async def list_spawners(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)
        spawners = client.db.get_spawners(guild_id)

        if not spawners:
            await interaction.response.send_message(
                "ℹ️ Es sind keine Spawner in der Datenbank.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📋 Alle Spawner ({len(spawners)})",
            color=discord.Color.blue()
        )

        lines = []
        for i, sp in enumerate(spawners, 1):
            lines.append(f"**{i}.** {sp['name']} — `{sp['price']}$`")

        text = "\n".join(lines[:25])
        if len(spawners) > 25:
            text += f"\n\n*... und {len(spawners) - 25} weitere*"

        embed.description = text
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @client.tree.command(name="spawnerreset", description="Setzt alles zurück: Alle Spawner, Text und die gesendete Liste")
    async def reset_all_spawner_data(interaction: Interaction):
        if not is_admin(interaction.user.id):
            await interaction.response.send_message(
                "❌ Du hast keine Berechtigung dafür.",
                ephemeral=True
            )
            return

        guild_id = str(interaction.guild.id)

        # Show confirmation
        confirm_view = ConfirmResetView(client.db, interaction.user.id, guild_id, interaction.guild)
        embed = discord.Embed(
            title="⚠️ Alles zurücksetzen?",
            description=(
                "Dies wird **alles** löschen:\n"
                "• Alle Spawner aus der Datenbank\n"
                "• Den Header-Text\n"
                "• Die gesendete Preisliste im Kanal\n\n"
                "**Dies kann nicht rückgängig gemacht werden!**"
            ),
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
        await confirm_view.wait()


class ConfirmClearView(View):
    """Confirmation view for clearing all spawners."""

    def __init__(self, db, user_id: int, guild_id: str):
        super().__init__(timeout=30)
        self.db = db
        self.user_id = user_id
        self.guild_id = guild_id

    @button(style=discord.ButtonStyle.red, label="Ja, alle löschen", emoji="🗑️", custom_id="confirm_clear_yes")
    async def confirm_yes(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das bestätigen.", ephemeral=True)
            return

        count = len(self.db.get_spawners(self.guild_id))
        self.db.clear_spawners(self.guild_id)

        for child in self.children:
            child.disabled = True
        btn.label = f"✅ {count} Spawner gelöscht!"

        await interaction.response.edit_message(view=self)
        self.stop()

    @button(style=discord.ButtonStyle.grey, label="Abbrechen", emoji="❌", custom_id="confirm_clear_no")
    async def confirm_no(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das abbrechen.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        btn.label = "❌ Abgebrochen"

        await interaction.response.edit_message(view=self)
        self.stop()


class ConfirmResetView(View):
    """Confirmation view for full spawner reset."""

    def __init__(self, db, user_id: int, guild_id: str, guild):
        super().__init__(timeout=30)
        self.db = db
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild

    @button(style=discord.ButtonStyle.red, label="Ja, alles zurücksetzen", emoji="💣", custom_id="confirm_reset_yes")
    async def confirm_yes(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das bestätigen.", ephemeral=True)
            return

        # Delete all spawners
        self.db.clear_spawners(self.guild_id)

        # Clear header text
        self.db.set_setting('spawner_header_text', '')

        # Delete sent message
        channel_id = self.db.get_setting('spawner_list_channel_id', '')
        message_id = self.db.get_setting('spawner_list_message_id', '')
        if channel_id and message_id:
            try:
                channel = self.guild.get_channel(int(channel_id))
                if channel:
                    message = await channel.fetch_message(int(message_id))
                    await message.delete()
            except Exception:
                pass

        # Clear stored IDs
        self.db.set_setting('spawner_list_channel_id', '')
        self.db.set_setting('spawner_list_message_id', '')

        for child in self.children:
            child.disabled = True
        btn.label = "✅ Alles zurückgesetzt!"

        await interaction.response.edit_message(view=self)
        self.stop()

    @button(style=discord.ButtonStyle.grey, label="Abbrechen", emoji="❌", custom_id="confirm_reset_no")
    async def confirm_no(self, interaction: Interaction, btn: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Nur der Ersteller kann das abbrechen.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        btn.label = "❌ Abgebrochen"

        await interaction.response.edit_message(view=self)
        self.stop()
