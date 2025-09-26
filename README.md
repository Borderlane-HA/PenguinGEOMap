# PenguinGEOMap

**HACS integration for Home Assistant** + **self‑hosted server** to visualize movement data on an OpenStreetMap map.  
Supports multiple devices (each with its own **key**, **server URL**, and **device_tracker**), server‑side login protection, and a **“connect”** option to draw route lines.

> Examples in this README:
> - Device name: `myiphone`  
> - Entity: `device_tracker.myiphone`  
> - Server: `https://myserverurl/penguin_geomap_server`  
> - Key / password: `MYPASS-KEY`

---

## Features

- Add multiple devices manually (name, device tracker, key, server URL, verify SSL, poll interval).
- Server login via **key** (only people with the key can see the device’s points).
- **OpenStreetMap** map (Leaflet via CDN).
- **“Connect”** button: draw a dashed line between points of the selected day.
- Defaults to **today**; pick other days with the date picker or automatically show the **latest** day (`date=latest`).
- **Robust**: event listener + optional **polling** (default 30 s, configurable per device).

---

## Table of contents

1. [Requirements](#requirements)  
2. [Installation – Home Assistant (HACS)](#installation--home-assistant-hacs)  
3. [Installation – Server](#installation--server)  
4. [Initial configuration](#initial-configuration)  
5. [Services (Home Assistant)](#services-home-assistant)  
6. [Examples](#examples)  
7. [Security & privacy](#security--privacy)  
8. [Troubleshooting](#troubleshooting)  
9. [FAQ](#faq)

---

## Requirements

- **Home Assistant** (Core or OS/Supervised). HACS recommended.
- A **`device_tracker.*`** entity that exposes `latitude` and `longitude` attributes  
  (e.g. `device_tracker.myiphone`).
- A web server with **PHP** (incl. **PDO SQLite**) for the server part. The folder  
  `server/penguin_geomap_server/data/` must be writable.

---

## Installation – Home Assistant (HACS)

> Alternatively, copy manually to `/config/custom_components/penguin_geomap`.

1. Add this repository to HACS as a **custom repository**.
2. URL: https://github.com/Borderlane-HA/PenguinGEOMap
3. Typ: Integration
4. Install **PenguinGEOMap**.  
5. **Restart** Home Assistant.

After restart: **Settings → Devices & Services → Add Integration → “PenguinGEOMap”**.

---

## Installation – Server

1. Copy `server/penguin_geomap_server` to your web server, e.g.  
   `/var/www/html/penguin_geomap_server`.
2. Make sure the `data/` folder is **writable** (e.g. `chown -R www-data:www-data data/` and `chmod -R 775 data/`).
3. (Optional) Make `logs/` writable as well for server logs (e.g. `ingest.log`).
4. **Leaflet** loads from CDN (no other external deps).
5. **Access**:
   - Login: `https://myserverurl/penguin_geomap_server/login.php`  
   - Map: `https://myserverurl/penguin_geomap_server/index.php`

---

## Initial configuration

### In Home Assistant

When adding the integration, you’ll see a form:

- **Name**: free text (e.g. `myiphone`)  
- **Entity**: e.g. `device_tracker.myiphone`  
- **Server URL**: `https://myserverurl/penguin_geomap_server`  
  > **Important:** **Do not** include `/api/ingest.php` — the integration appends it automatically.
- **Key**: `MYPASS-KEY`  
  Allowed: `A–Z a–z 0–9 _ -` (4–64 chars)
- **Verify SSL**: enable if your certificate is valid; disable for self‑signed during tests.
- **Poll seconds**: e.g. `30` (set `0` to disable polling)

After saving, if the entity already has coordinates, the integration will **send one initial point** immediately.

### Log in on the server

- Open `https://myserverurl/penguin_geomap_server/login.php`  
- Enter **the same key** you configured in Home Assistant (here: `MYPASS-KEY`).  
- By default **today** is shown; pick other dates via the date picker.  
- The **“Connect”** button draws a dashed line between the day’s waypoints.  
- Use **Logout** to end the session.

---

## Services (Home Assistant)

You’ll find all services under **Developer Tools → Services**.

### `penguin_geomap.send_now`

Reads the current coordinates from the given `device_tracker` and sends them immediately.

```yaml
service: penguin_geomap.send_now
data:
  entity_id: device_tracker.myiphone
```

> If you omit `entity_id`, the **first configured device** will be used (if present).

---

### `penguin_geomap.test_post`

Sends a **test point** (Munich by default) to the server—independent of the tracker’s real state.  
Great for **end‑to‑end diagnostics**.

```yaml
service: penguin_geomap.test_post
data:
  device_index: 0    # optional (0 = first device)
  # lat: 48.137154   # optional
  # lon: 11.576124   # optional
```

---

### `penguin_geomap.update_device`

Allows **editing an existing entry** by index, useful if your HA version does not show the “Configure” options dialog.

```yaml
service: penguin_geomap.update_device
data:
  index: 0                           # 0 = first device
  name: myiphone                     # optional
  entity_id: device_tracker.myiphone # optional
  server_url: https://myserverurl/penguin_geomap_server  # optional
  key: MYPASS-KEY                    # optional
  verify_ssl: true                   # optional
  enabled: true                      # optional
  poll_seconds: 30                   # optional (0 = off)
```

> The integration writes to options and **auto‑reloads** — changes take effect immediately.

---

## Examples

### 1) Send a test point via curl (today’s UNIX timestamp)

```bash
curl -X POST "https://myserverurl/penguin_geomap_server/api/ingest.php"   -H "Content-Type: application/json"   -d '{"key":"MYPASS-KEY","lat":48.137154,"lon":11.576124,"ts":'$(date +%s)'}'
```

Expected response: `{"ok":true}`  
Check: `https://myserverurl/penguin_geomap_server/api/debug.php?key=MYPASS-KEY&limit=5`

---

### 2) “Send now” (current location)

```yaml
service: penguin_geomap.send_now
data:
  entity_id: device_tracker.myiphone
```

---

### 3) Test point (diagnostics)

```yaml
service: penguin_geomap.test_post
data:
  device_index: 0
```

---

### 4) Edit device (server/key/sensor)

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

## Security & privacy

- Access to map data is **key‑protected** (server login with the device’s key, e.g. `MYPASS-KEY`).  
- **HTTPS** strongly recommended. For self‑signed certs during testing, disable `Verify SSL` in the integration.
- The server stores per point only:
  - `device_key` (your key),
  - `ts` (UNIX timestamp),
  - `lat`, `lon`.

---

## Troubleshooting

1. **No points visible**
   - In Home Assistant, call `penguin_geomap.test_post`.  
     - Do points show up in `debug.php`?  
       - **Yes** → HA ↔ server connectivity is fine.  
       - **No** → Check URL, certificate (Verify SSL), and firewall/port 443.
   - **Date filter**: The map filters by the selected day. Choose **today** or use `date=latest` (default on first load).

2. **Check server**
   - `https://myserverurl/penguin_geomap_server/api/debug.php?key=MYPASS-KEY&limit=5`
   - Log file: `server/penguin_geomap_server/logs/ingest.log`

3. **“POST … failed (404)”**
   - **Wrong URL**: Do **not** include `/api/ingest.php` in options.  
     Correct **base URL**: `https://myserverurl/penguin_geomap_server`

4. **SSL errors**
   - Self‑signed cert? Disable `Verify SSL` in options during testing.

5. **Event listener doesn’t fire**
   - The integration also has **polling** (default 30 s).  
   - Adjust `poll_seconds` via options/service (e.g. 15 s).

6. **Edit configuration later**
   - Either via **Configure** (options flow)  
   - or with the service `penguin_geomap.update_device` (see above).

7. **Enable HA logs**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.penguin_geomap: debug
   ```

---

## FAQ

**Which entities are supported?**  
Any `device_tracker.*` exposing `latitude` & `longitude` (e.g. `device_tracker.myiphone`).

**Can I track multiple devices?**  
Yes — add more devices in the integration (each with its own key & server URL, or even the same server if you prefer).

**May the server URL contain `/api/ingest.php`?**  
**No.** Provide only the **base URL** (e.g. `https://myserverurl/penguin_geomap_server`). The integration appends `/api/ingest.php` automatically.

**What does “Connect” do?**  
It connects the day’s points **in chronological order** with a dashed polyline.

---

Enjoy **PenguinGEOMap** 🐧
