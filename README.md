# PenguinGEOMap

**HACS-Integration für Home Assistant** + **selbstgehosteter Server** zur Visualisierung von Bewegungsdaten auf einer OpenStreetMap-Karte.  
Unterstützt beliebig viele Geräte (je Gerät eigener **Key**, **Server-URL**, **device_tracker**), Login-Schutz auf dem Server und eine „**Verbinden**“-Option für Weglinien.

> Beispiele in dieser README:
> - Gerät: `myiphone`  
> - Entity: `device_tracker.myiphone`  
> - Server: `https://myserverurl/penguin_geomap_server`  
> - Key / Passwort: `MYPASS-KEY`

---

## Features

- Mehrere Geräte manuell hinzufügen (Name, Device-Tracker, Key, Server-URL, Verify-SSL, Poll-Intervall).
- Server-Login per **Key** (nur wer den Key kennt, sieht die Punkte des Geräts).
- Karte auf **OpenStreetMap**-Basis (Leaflet, via CDN).
- **„Verbinden“**-Schaltfläche: zeichne eine gestrichelte Linie zwischen den Punkten des gewählten Tages.
- **Heute** wird standardmäßig angezeigt; über Datepicker andere Tage wählbar oder automatisch der **letzte belegte Tag** (`date=latest`).
- **Robust**: Event-Listener + optionales **Polling** (Standard 30 s, einstellbar pro Gerät).

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)  
2. [Installation – Home Assistant (HACS)](#installation--home-assistant-hacs)  
3. [Installation – Server](#installation--server)  
4. [Erstkonfiguration](#erstkonfiguration)  
5. [Services (Home Assistant)](#services-home-assistant)  
6. [Beispiele](#beispiele)  
7. [Sicherheit & Datenschutz](#sicherheit--datenschutz)  
8. [Troubleshooting](#troubleshooting)  
9. [FAQ](#faq)

---

## Voraussetzungen

- **Home Assistant** (Core oder OS/Supervised), HACS empfohlen.
- Ein **`device_tracker.*`**, der die Attribute `latitude` und `longitude` liefert (z. B. `device_tracker.myiphone`).
- Ein Webserver mit **PHP** (inkl. **PDO SQLite**) für den Server-Teil. Schreibrechte für den Ordner `server/penguin_geomap_server/data/`.

---

## Installation – Home Assistant (HACS)

> Alternativ: Manuell nach `/config/custom_components/penguin_geomap` kopieren.

1. Dieses Repository in HACS als **benutzerdefiniertes Repository** hinzufügen.  
2. **PenguinGEOMap** installieren.  
3. Home Assistant **neu starten**.

Nach dem Neustart: **Einstellungen → Geräte & Dienste → Integration hinzufügen → „PenguinGEOMap“**.

---

## Installation – Server

1. Den Ordner `server/penguin_geomap_server` auf deinen Webserver kopieren, z. B. nach  
   `/var/www/html/penguin_geomap_server`.
2. Der Ordner `data/` **muss schreibbar** sein (z. B. `chown -R www-data:www-data data/` und `chmod -R 775 data/`).
3. (Optional) `logs/` für Server-Logs (z. B. `ingest.log`) ebenfalls schreibbar machen.
4. **Leaflet** wird per CDN geladen (keine weiteren externen Abhängigkeiten).
5. **Aufruf**:
   - Login: `https://myserverurl/penguin_geomap_server/login.php`  
   - Karte: `https://myserverurl/penguin_geomap_server/index.php`

---

## Erstkonfiguration

### In Home Assistant

Beim Hinzufügen der Integration erscheint ein Formular:

- **Name**: frei (z. B. `myiphone`)  
- **Entity**: z. B. `device_tracker.myiphone`  
- **Server-URL**: `https://myserverurl/penguin_geomap_server`  
  > **Wichtig:** **ohne** `/api/ingest.php` – die Integration hängt das selbst an!
- **Key**: `MYPASS-KEY`  
  Erlaubt: `A–Z a–z 0–9 _ -` (4–64 Zeichen)
- **Verify SSL**: aktivieren, wenn dein Zertifikat gültig ist; bei Self-Signed deaktivieren.
- **Poll seconds**: z. B. `30` (0 = Polling aus)

Nach dem Speichern sendet die Integration, **sofern bereits Koordinaten vorhanden sind**, einmalig direkt einen Punkt.

### Auf dem Server einloggen

- Öffne `https://myserverurl/penguin_geomap_server/login.php`  
- Gib **denselben Key** ein, den du in Home Assistant verwendet hast (hier: `MYPASS-KEY`).  
- Standardmäßig wird **heute** angezeigt; über den Datepicker andere Tage.  
- Der Button **„Verbinden“** zeichnet eine gestrichelte Linie zwischen den Wegpunkten des Tages.  
- Über **Logout** trennst du die Session.

---

## Services (Home Assistant)

Alle Dienste findest du unter **Entwicklerwerkzeuge → Dienste**.

### `penguin_geomap.send_now`

Liest die aktuellen Koordinaten des angegebenen `device_tracker` und sendet sie sofort.

```yaml
service: penguin_geomap.send_now
data:
  entity_id: device_tracker.myiphone
```

> Wenn du kein `entity_id` angibst, wird – falls vorhanden – das **erste** konfigurierte Gerät verwendet.

---

### `penguin_geomap.test_post`

Sendet einen **Testpunkt** (default München) an den Server – unabhängig vom tatsächlichen Tracker-Zustand.  
Perfekt für die **Strecken-Diagnose**.

```yaml
service: penguin_geomap.test_post
data:
  device_index: 0    # optional (0 = erstes Gerät)
  # lat: 48.137154   # optional
  # lon: 11.576124   # optional
```

---

### `penguin_geomap.update_device`

Erlaubt das **nachträgliche Editieren** eines existierenden Eintrags, falls du (z. B. in deiner HA-Version) keinen „Konfigurieren“-Dialog bekommst.

```yaml
service: penguin_geomap.update_device
data:
  index: 0                           # 0 = erstes Gerät
  name: myiphone                     # optional
  entity_id: device_tracker.myiphone # optional
  server_url: https://myserverurl/penguin_geomap_server  # optional
  key: MYPASS-KEY                    # optional
  verify_ssl: true                   # optional
  enabled: true                      # optional
  poll_seconds: 30                   # optional (0 = aus)
```

> Die Integration speichert in den Options und **lädt automatisch neu** – die Änderung ist direkt aktiv.

---

## Beispiele

### 1) Testpunkt per Curl senden (heutiger Timestamp)

```bash
curl -X POST "https://myserverurl/penguin_geomap_server/api/ingest.php"   -H "Content-Type: application/json"   -d '{"key":"MYPASS-KEY","lat":48.137154,"lon":11.576124,"ts":'$(date +%s)'}'
```

Erwartete Antwort: `{"ok":true}`  
Prüfen: `https://myserverurl/penguin_geomap_server/api/debug.php?key=MYPASS-KEY&limit=5`

---

### 2) „Sende jetzt sofort“ (aktueller Standort)

```yaml
service: penguin_geomap.send_now
data:
  entity_id: device_tracker.myiphone
```

---

### 3) Testpunkt (Diagnose)

```yaml
service: penguin_geomap.test_post
data:
  device_index: 0
```

---

### 4) Gerät nachträglich ändern (Server/Key/Sensor)

```yaml
service: penguin_geomap.update_device
data:
  index: 0
  server_url: https://myserverurl/penguin_geomap_server
  key: MYPASS-KEY
  entity_id: device_tracker.myiphone
  verify_ssl: true
  poll_seconds: 30
```

---

## Sicherheit & Datenschutz

- Zugriff auf die Kartendaten erfolgt **nur nach Login** mit dem **Key** des Geräts (`MYPASS-KEY`).  
- **HTTPS** dringend empfohlen. Bei Self-Signed-Zertifikat kannst du in der Integration `Verify SSL` deaktivieren.
- Auf dem Server werden pro Punkt gespeichert:
  - `device_key` (dein Key),
  - `ts` (UNIX-Timestamp),
  - `lat`, `lon`.

---

## Troubleshooting

1. **Keine Punkte sichtbar**
   - In Home Assistant den Dienst `penguin_geomap.test_post` aufrufen.  
     - Kommen Punkte in `debug.php` an?  
       - **Ja** → HA ↔ Server-Verbindung ok.  
       - **Nein** → URL prüfen, Zertifikat (Verify SSL), Firewall/Port 443.
   - **Datum** prüfen: Die Karte filtert auf den gewählten Tag. Wähle `heute` oder nutze `date=latest` (Standard beim Laden).

2. **Debug/Server prüfen**
   - `https://myserverurl/penguin_geomap_server/api/debug.php?key=MYPASS-KEY&limit=5`
   - Logdatei: `server/penguin_geomap_server/logs/ingest.log`

3. **„POST … failed (404)“**
   - **Falsche URL**: In den Optionen **kein** `/api/ingest.php` angeben.  
     Richtig ist die **Basis-URL**: `https://myserverurl/penguin_geomap_server`

4. **SSL-Fehler**
   - Selbstsigniertes Zertifikat? In den Optionen `Verify SSL: false`.

5. **Event-Listener triggert nicht**
   - Integration hat zusätzlich **Polling** (Default 30 s).  
   - Du kannst `poll_seconds` per Options-Flow/Service anpassen (z. B. 15 s).

6. **Konfiguration nachträglich ändern**
   - Entweder über **Konfigurieren** (Options-Flow)  
   - oder per Service `penguin_geomap.update_device` (siehe oben).

7. **HA-Logs aktivieren**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.penguin_geomap: debug
   ```

---

## FAQ

**Welche Entities werden unterstützt?**  
Alle `device_tracker.*`, die `latitude` & `longitude` als Attribute liefern (z. B. `device_tracker.myiphone`).

**Kann ich mehrere Geräte nutzen?**  
Ja – einfach in der Integration weitere Geräte hinzufügen (jeder mit eigenem Key & Server-URL, oder gemeinsam).

**Darf die Server-URL `/api/ingest.php` enthalten?**  
**Nein.** Gib **nur** die Basis-URL an (z. B. `https://myserverurl/penguin_geomap_server`). Die Integration hängt `/api/ingest.php` automatisch an.

**Was macht „Verbinden“?**  
Verbindet die Punkte des ausgewählten Tages **in zeitlicher Reihenfolge** mit einer gestrichelten Linie.

---

Viel Spaß mit **PenguinGEOMap** 🐧
