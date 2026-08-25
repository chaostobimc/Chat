"""
Discord Ticket Bot - Web Dashboard
A beautiful, modern dashboard for managing the ticket bot.
"""

import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# ==================== DATABASE HELPER ====================

def get_db():
    """Get database connection."""
    conn = sqlite3.connect("database/tickets.db")
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    """Convert sqlite Row to dict."""
    return dict(row) if row else None


# ==================== AUTH ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Landing page / redirect to dashboard."""
    if session.get('authenticated'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login')
def login():
    """Login page."""
    if session.get('authenticated'):
        return redirect(url_for('dashboard'))
    
    error = request.args.get('error')
    return render_template('login.html', error=error)


@app.route('/auth', methods=['POST'])
def auth():
    """Handle login authentication."""
    password = request.form.get('password')
    expected_password = os.getenv('DASHBOARD_PASSWORD', 'admin')
    
    if password == expected_password:
        session['authenticated'] = True
        session['username'] = 'Admin'
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login', error='Invalid password'))


@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page."""
    db = get_db()
    
    # Get statistics
    total_tickets = db.execute("SELECT COUNT(*) as count FROM tickets").fetchone()['count']
    open_tickets = db.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'open'").fetchone()['count']
    closed_tickets = db.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'closed'").fetchone()['count']
    
    # Get recent tickets
    recent_tickets = db.execute("""
        SELECT t.*, b.label as button_label 
        FROM tickets t 
        LEFT JOIN ticket_buttons b ON t.button_id = b.id 
        ORDER BY t.created_at DESC LIMIT 10
    """).fetchall()
    
    # Get panels
    panels = db.execute("SELECT * FROM ticket_panels ORDER BY created_at DESC").fetchall()
    
    # Get all buttons with panel info
    buttons = db.execute("""
        SELECT tb.*, tp.title as panel_title 
        FROM ticket_buttons tb 
        JOIN ticket_panels tp ON tb.panel_id = tp.id 
        ORDER BY tb.id DESC
    """).fetchall()
    
    db.close()
    
    # Convert to list of dicts
    recent_tickets = [dict(row) for row in recent_tickets]
    panels = [dict(row) for row in panels]
    buttons = [dict(row) for row in buttons]
    
    return render_template(
        'dashboard.html',
        total_tickets=total_tickets,
        open_tickets=open_tickets,
        closed_tickets=closed_tickets,
        recent_tickets=recent_tickets,
        panels=panels,
        buttons=buttons
    )


@app.route('/panels')
@login_required
def panels_page():
    """Panels management page."""
    db = get_db()
    panels = db.execute("""
        SELECT p.*, COUNT(tb.id) as button_count 
        FROM ticket_panels p 
        LEFT JOIN ticket_buttons tb ON p.id = tb.panel_id 
        GROUP BY p.id 
        ORDER BY p.created_at DESC
    """).fetchall()
    db.close()
    
    panels = [dict(row) for row in panels]
    return render_template('panels.html', panels=panels)


@app.route('/panels/create', methods=['POST'])
@login_required
def create_panel():
    """Create a new panel."""
    title = request.form.get('title', 'Support Tickets')
    description = request.form.get('description', 'Wähle eine Kategorie für dein Anliegen')
    
    db = get_db()
    db.execute(
        "INSERT INTO ticket_panels (guild_id, title, description) VALUES (?, ?, ?)",
        ('dashboard', title, description)
    )
    db.commit()
    db.close()
    
    flash('Panel erfolgreich erstellt!', 'success')
    return redirect(url_for('panels_page'))


@app.route('/panels/<int:panel_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_panel(panel_id):
    """Edit a panel."""
    db = get_db()
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        message_id = request.form.get('message_id')
        channel_id = request.form.get('channel_id')
        
        db.execute(
            "UPDATE ticket_panels SET title = ?, description = ?, message_id = ?, channel_id = ? WHERE id = ?",
            (title, description, message_id, channel_id, panel_id)
        )
        db.commit()
        flash('Panel erfolgreich aktualisiert!', 'success')
        db.close()
        return redirect(url_for('panels_page'))
    
    panel = db.execute("SELECT * FROM ticket_panels WHERE id = ?", (panel_id,)).fetchone()
    buttons = db.execute("SELECT * FROM ticket_buttons WHERE panel_id = ?", (panel_id,)).fetchall()
    db.close()
    
    return render_template('panel_edit.html', panel=dict(panel), buttons=[dict(b) for b in buttons])


@app.route('/panels/<int:panel_id>/delete', methods=['POST'])
@login_required
def delete_panel(panel_id):
    """Delete a panel."""
    db = get_db()
    db.execute("DELETE FROM ticket_buttons WHERE panel_id = ?", (panel_id,))
    db.execute("DELETE FROM ticket_panels WHERE id = ?", (panel_id,))
    db.commit()
    db.close()
    
    flash('Panel erfolgreich gelöscht!', 'success')
    return redirect(url_for('panels_page'))


@app.route('/buttons')
@login_required
def buttons_page():
    """Buttons management page."""
    db = get_db()
    buttons = db.execute("""
        SELECT tb.*, tp.title as panel_title 
        FROM ticket_buttons tb 
        JOIN ticket_panels tp ON tb.panel_id = tp.id 
        ORDER BY tb.id DESC
    """).fetchall()
    panels = db.execute("SELECT * FROM ticket_panels").fetchall()
    db.close()
    
    return render_template(
        'buttons.html', 
        buttons=[dict(b) for row in buttons for b in [row]],  # Convert
        panels=[dict(p) for p in panels]
    )


@app.route('/buttons/create', methods=['POST'])
@login_required
def create_button():
    """Create a new button."""
    panel_id = request.form.get('panel_id', type=int)
    label = request.form.get('label')
    emoji = request.form.get('emoji')
    color = request.form.get('color', 'blurple')
    description = request.form.get('description')
    category_id = request.form.get('category_id')
    support_role_id = request.form.get('support_role_id')
    question_title = request.form.get('question_title')
    question_placeholder = request.form.get('question_placeholder')
    require_question = 1 if request.form.get('require_question') else 0
    max_tickets = request.form.get('max_tickets', type=int, default=3)
    image_url = request.form.get('image_url')
    
    # Modal settings
    use_modal = 1 if request.form.get('use_modal') else 0
    modal_title = request.form.get('modal_title')
    modal_fields_json = request.form.get('modal_fields_json', '[]')
    
    # Handle image upload
    image_local = None
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename:
            os.makedirs('static/uploads', exist_ok=True)
            filename = f"btn_{datetime.now().timestamp()}_{file.filename.replace(' ', '_')}"
            filepath = os.path.join('static/uploads', filename)
            file.save(filepath)
            image_local = f'/static/uploads/{filename}'
    
    custom_id = f"ticket_{panel_id}_{label.lower().replace(' ', '_')}_{datetime.now().timestamp()}"
    
    db = get_db()
    db.execute("""
        INSERT INTO ticket_buttons 
        (panel_id, custom_id, label, emoji, color, description, 
         category_id, support_role_id, question_title, question_placeholder,
         require_question, max_tickets, image_url, image_local,
         use_modal, modal_title, modal_fields)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (panel_id, custom_id, label, emoji, color, description,
          category_id, support_role_id, question_title, question_placeholder,
          require_question, max_tickets, image_url, image_local,
          use_modal, modal_title, modal_fields_json))
    db.commit()
    db.close()
    
    flash('Button erfolgreich erstellt!', 'success')
    return redirect(url_for('buttons_page'))


@app.route('/buttons/<int:button_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_button(button_id):
    """Edit a button."""
    db = get_db()
    
    if request.method == 'POST':
        label = request.form.get('label')
        emoji = request.form.get('emoji')
        color = request.form.get('color', 'blurple')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        support_role_id = request.form.get('support_role_id')
        question_title = request.form.get('question_title')
        question_placeholder = request.form.get('question_placeholder')
        require_question = 1 if request.form.get('require_question') else 0
        max_tickets = request.form.get('max_tickets', type=int, default=3)
        image_url = request.form.get('image_url')
        
        # Modal settings
        use_modal = 1 if request.form.get('use_modal') else 0
        modal_title = request.form.get('modal_title')
        modal_fields_json = request.form.get('modal_fields_json', '[]')
        
        # Handle image upload
        image_local = request.form.get('image_local')
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename:
                os.makedirs('static/uploads', exist_ok=True)
                filename = f"btn_{datetime.now().timestamp()}_{file.filename.replace(' ', '_')}"
                filepath = os.path.join('static/uploads', filename)
                file.save(filepath)
                image_local = f'/static/uploads/{filename}'
        
        if request.form.get('delete_image'):
            image_local = None
            image_url = None
        
        db.execute("""
            UPDATE ticket_buttons SET 
                label = ?, emoji = ?, color = ?, description = ?,
                category_id = ?, support_role_id = ?, 
                question_title = ?, question_placeholder = ?,
                require_question = ?, max_tickets = ?,
                image_url = ?, image_local = ?,
                use_modal = ?, modal_title = ?, modal_fields = ?
            WHERE id = ?
        """, (label, emoji, color, description, category_id, support_role_id,
              question_title, question_placeholder, require_question, max_tickets,
              image_url, image_local, use_modal, modal_title, modal_fields_json, button_id))
        db.commit()
        flash('Button erfolgreich aktualisiert!', 'success')
        db.close()
        return redirect(url_for('buttons_page'))
    
    button = db.execute("SELECT * FROM ticket_buttons WHERE id = ?", (button_id,)).fetchone()
    panels = db.execute("SELECT * FROM ticket_panels").fetchall()
    db.close()
    
    # Parse modal fields for template
    button_dict = dict(button)
    if button_dict.get('modal_fields'):
        try:
            import json
            button_dict['modal_fields_parsed'] = json.loads(button_dict['modal_fields'])
        except:
            button_dict['modal_fields_parsed'] = []
    else:
        button_dict['modal_fields_parsed'] = []
    
    return render_template(
        'button_edit.html', 
        button=button_dict, 
        panels=[dict(p) for p in panels]
    )


@app.route('/buttons/<int:button_id>/delete', methods=['POST'])
@login_required
def delete_button(button_id):
    """Delete a button."""
    db = get_db()
    db.execute("DELETE FROM ticket_buttons WHERE id = ?", (button_id,))
    db.commit()
    db.close()
    
    flash('Button erfolgreich gelöscht!', 'success')
    return redirect(url_for('buttons_page'))


@app.route('/tickets')
@login_required
def tickets_page():
    """Tickets management page."""
    status = request.args.get('status', 'all')
    
    db = get_db()
    if status == 'all':
        tickets = db.execute("""
            SELECT t.*, b.label as button_label 
            FROM tickets t 
            LEFT JOIN ticket_buttons b ON t.button_id = b.id 
            ORDER BY t.created_at DESC
        """).fetchall()
    else:
        tickets = db.execute("""
            SELECT t.*, b.label as button_label 
            FROM tickets t 
            LEFT JOIN ticket_buttons b ON t.button_id = b.id 
            WHERE t.status = ?
            ORDER BY t.created_at DESC
        """, (status,)).fetchall()
    db.close()
    
    tickets = [dict(row) for row in tickets]
    
    return render_template('tickets.html', tickets=tickets, status=status)


@app.route('/tickets/<int:ticket_id>')
@login_required
def ticket_detail(ticket_id):
    """Ticket detail page."""
    db = get_db()
    ticket = db.execute("""
        SELECT t.*, b.label as button_label, b.description as button_description
        FROM tickets t 
        LEFT JOIN ticket_buttons b ON t.button_id = b.id 
        WHERE t.id = ?
    """, (ticket_id,)).fetchone()
    
    transcript = db.execute(
        "SELECT * FROM transcripts WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1",
        (ticket['ticket_id'],)
    ).fetchone()
    
    db.close()
    
    if not ticket:
        flash('Ticket nicht gefunden!', 'error')
        return redirect(url_for('tickets_page'))
    
    return render_template(
        'ticket_detail.html', 
        ticket=dict(ticket),
        transcript=dict(transcript) if transcript else None
    )


@app.route('/settings')
@login_required
def settings_page():
    """Settings page."""
    db = get_db()
    settings = db.execute("SELECT key, value FROM settings").fetchall()
    settings_dict = {row['key']: row['value'] for row in settings}
    db.close()
    
    return render_template('settings.html', settings=settings_dict)


@app.route('/settings/save', methods=['POST'])
@login_required
def save_settings():
    """Save settings."""
    db = get_db()
    
    for key, value in request.form.items():
        if key.startswith('setting_'):
            setting_key = key.replace('setting_', '')
            db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (setting_key, value)
            )
    
    db.commit()
    db.close()
    
    flash('Einstellungen erfolgreich gespeichert!', 'success')
    return redirect(url_for('settings_page'))


# ==================== API ROUTES ====================

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint for dashboard statistics."""
    db = get_db()
    
    stats = {
        'total': db.execute("SELECT COUNT(*) as count FROM tickets").fetchone()['count'],
        'open': db.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'open'").fetchone()['count'],
        'closed': db.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'closed'").fetchone()['count'],
        'panels': db.execute("SELECT COUNT(*) as count FROM ticket_panels").fetchone()['count'],
        'buttons': db.execute("SELECT COUNT(*) as count FROM ticket_buttons").fetchone()['count'],
    }
    
    # Tickets per day (last 7 days)
    tickets_by_day = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count 
        FROM tickets 
        WHERE created_at >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY day
    """).fetchall()
    
    stats['tickets_by_day'] = [dict(row) for row in tickets_by_day]
    
    db.close()
    
    return jsonify(stats)


# ==================== MAIN ====================

if __name__ == "__main__":
    # Ensure database directory exists
    os.makedirs("database", exist_ok=True)
    
    # Run dashboard
    print("🌐 Dashboard wird gestartet auf http://localhost:5000")
    print("🔐 Standard-Passwort: admin (ändere es in settings!)")
    app.run(host="0.0.0.0", port=5000, debug=True)
