# 🎫 Discord Ticket Bot - Premium Edition

Ein professioneller Discord Ticket Bot mit vollständigem Web-Dashboard. Alle Einstellungen können bequem über das Dashboard vorgenommen werden.

## ✨ Features

### Dashboard
- **Modernes Web-Interface** - Professionelles, cleanes Design
- **Live-Statistiken** - Übersicht aller Ticket-Aktivitäten
- **Panel-Verwaltung** - Erstelle und bearbeite Ticket-Panels
- **Button-Verwaltung** - Vollständig anpassbare Buttons mit individuellen Einstellungen
- **Button-Grafiken** - Optionale Bilder für jeden Button
- **Panel-Grafiken** - Optionale Header-Bilder für Panels
- **Ticket-Verwaltung** - Alle Tickets einsehen und verwalten
- **Transkript-Export** - Automatische Transkript-Speicherung

### Ticket-System
- **Mehrere Panels** - Erstelle beliebig viele Ticket-Panels
- **Individuelle Buttons** - Jeder Button mit eigenen Einstellungen
- **Button-Bilder** - Bilder für jeden Button (URL oder Upload)
- **Vorfragen** - Frage nach Betreff bevor Ticket erstellt wird
- **Max. Tickets** - Limitiere offene Tickets pro Person
- **Support-Rollen** - Automatische Berechtigungen für Support-Team
- **Foren-Support** - Optional Forum-Kanäle statt Text-Kanäle

### Discord-Befehle
- `/ticket-panel` - Erstellt ein neues Ticket-Panel
- `/ticket-add` - Fügt einen Button zum Panel hinzu
- `/ticket-close` - Schließt das aktuelle Ticket
- `/ticket-stats` - Zeigt Ticket-Statistiken
- `/ticket-delete` - Löscht ein Panel

## 🚀 Installation

### Voraussetzungen
- Python 3.9 oder höher
- Discord Bot Token
- Internetverbindung

### 1. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 2. Bot konfigurieren

Bearbeite die `.env` Datei:

```env
DISCORD_TOKEN=dein_bot_token_hier
SECRET_KEY=dein_geheimer_schluessel
DASHBOARD_PASSWORD=dein_passwort
```

### 3. Bot-Token erhalten

1. Gehe zu [Discord Developer Portal](https://discord.com/developers/applications)
2. Erstelle eine neue Application
3. Navigiere zu "Bot" und erstelle einen Bot
4. Kopiere den Token in die `.env` Datei
5. Aktiviere unter "Bot" -> "Privileged Gateway Intents":
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT

### 4. Bot einladen

1. Gehe zu OAuth2 -> URL Generator
2. Wähle folgende Scopes:
   - ✅ bot
   - ✅ applications.commands
3. Wähle folgende Bot Permissions:
   - ✅ Send Messages
   - ✅ Manage Channels
   - ✅ Read Message History
   - ✅ View Channels
4. Kopiere die generierte URL und öffne sie in deinem Browser

## 🎮 Verwendung

### Bot starten

```bash
# Bot und Dashboard in separaten Terminals starten

# Terminal 1: Bot
python bot.py

# Terminal 2: Dashboard
python dashboard.py
```

### Dashboard öffnen

Öffne deinen Browser und gehe zu:
```
http://localhost:5000
```

Standard-Login:
- Passwort: `admin`

### Panel erstellen (Dashboard)

1. Gehe zu "Panels" im Dashboard
2. Klicke auf "Neues Panel"
3. Gib Titel und Beschreibung ein
4. Klicke auf "Erstellen"

### Button hinzufügen (Dashboard)

1. Gehe zu "Buttons" im Dashboard
2. Klicke auf "Neuer Button"
3. Konfiguriere alle Einstellungen:
   - Panel auswählen
   - Beschriftung und Emoji
   - Farbe wählen
   - Optional: Kategorie/Support-Rolle
   - Optional: Vorfrage aktivieren

### Panel in Discord senden

Nutze den `/ticket-panel` Slash-Befehl in Discord:

```
/ticket-panel channel:#tickets title:"Support Tickets" description:"Wähle eine Kategorie"
```

Danach Buttons hinzufügen:

```
/ticket-add label:"Allgemeine Frage" emoji:"❓" description:"Allgemeine Anfragen"
/ticket-add label:"Technischer Support" emoji:"🔧" description:"Technische Probleme"
/ticket-add label:"Bug melden" emoji:"🐛" description:"Fehler reporten"
```

## ⚙️ Button-Einstellungen (Detailliert)

| Einstellung | Beschreibung |
|-------------|--------------|
| **Panel** | Das Panel zu dem der Button gehört |
| **Beschriftung** | Angezeigter Text auf dem Button |
| **Emoji** | Emoji vor der Beschriftung |
| **Farbe** | Blau, Grau, Grün oder Rot |
| **Kategorie ID** | Discord Kategorie für neue Tickets |
| **Support-Rolle ID** | Rolle mit Zugriff auf Tickets |
| **Max. Tickets** | Maximale offene Tickets pro Person |
| **Vorfrage aktivieren** | Fragt nach Betreff vor Erstellung |
| **Frage-Titel** | Titel der Frage (z.B. "Betreff") |
| **Platzhalter** | Placeholder-Text im Eingabefeld |
| **Bild-URL** | URL zu einem Bild für den Button |
| **Bild-Upload** | Eigenes Bild hochladen |

## 🎨 Design-Anpassung

Das Dashboard verwendet CSS-Variablen. Ändere diese in `static/css/dashboard.css`:

```css
:root {
    --primary: #5865F2;      /* Hauptfarbe */
    --success: #23A55A;      /* Erfolg-Farbe */
    --warning: #F0B232;     /* Warnung-Farbe */
    --danger: #DA373C;      /* Fehler-Farbe */
    /* ... */
}
```

## 🔒 Sicherheit

- Ändere das Dashboard-Passwort nach der ersten Anmeldung
- Verwende einen starken SECRET_KEY in Produktion
- Teile niemals deinen Discord Bot Token
- Nutze HTTPS in Produktionsumgebungen

## 📁 Projektstruktur

```
├── bot.py              # Discord Bot Code
├── dashboard.py        # Web Dashboard (Flask)
├── templates/          # HTML Templates
├── static/             # CSS & JavaScript
├── .env.example       # Beispiel-Konfiguration
├── .gitignore         # Git Ignores
├── requirements.txt   # Python Abhängigkeiten
└── README.md          # Diese Datei
```

## 🛠️ Troubleshooting

### Bot reagiert nicht
- Prüfe ob der Token korrekt ist
- Prüfe ob alle Intents aktiviert sind
- Prüfe ob der Bot auf dem Server ist

### Dashboard funktioniert nicht
- Prüfe ob Port 5000 frei ist
- Prüfe die Flask-Logs

### Buttons funktionieren nicht
- Panels müssen erst in Discord gesendet werden
- Buttons müssen dem richtigen Panel zugeordnet sein

## 📝 Lizenz

Dieses Projekt ist privat und für den persönlichen Gebrauch gedacht.

## 🤝 Support

Bei Fragen oder Problemen, erstelle ein Issue im Repository.

---

Mit ❤️ erstellt für Discord Server
