
# PenguinGEOMap – HACS Integration + Server

This bundle contains:
- **Home Assistant HACS integration** `custom_components/penguin_geomap`
- **PHP server** `penguin_geomap_server` (Leaflet-based, self-hosted)

## Quick Start

### 1) Install the HACS Integration
1. Copy `homeassistant/custom_components/penguin_geomap` into your Home Assistant `custom_components/` folder.
2. Restart Home Assistant.
3. Go to *Settings → Devices & Services → Add Integration* and search **PenguinGEOMap**.
4. Create the integration (no initial fields). Then open the integration *Options* and add one or more devices:
   - **Name**: e.g., "My iPhone"
   - **Sensor**: select your `device_tracker.XX` entity (e.g., `device_tracker.myiphone`). This must provide `latitude` and `longitude` attributes.
   - **Server URL**: e.g., `https://YOUR.DOMAIN/penguin_geomap_server`
   - **Key**: A per-device key (only A–Z a–z 0–9 `_` `-`). This secures your data on the server.
   - **Enabled**: Turn on/off without deleting.
5. After saving, every time the tracker updates, the integration will POST to `SERVER_URL/api/ingest.php` with `{{ key, lat, lon, ts }}`.

### 2) Deploy the Server
1. Copy `server/penguin_geomap_server` to your web server.
2. Ensure PHP 8.1+ with PDO SQLite and that `server/penguin_geomap_server/data` is writable.
3. Download Leaflet (1.9.x) and place `leaflet.css` and `leaflet.js` into `assets/leaflet/`.
4. Open `https://YOUR.DOMAIN/penguin_geomap_server/login.php` and **login with the same Key** you used in Home Assistant.
5. The map defaults to **today**. Change the date with the picker; click **Verbinden** to draw a dashed route between points (chronological).

### Example URL (shown in Options forms)
```
https://YOUR.DOMAIN/penguin_geomap_server  (POST endpoint: /api/ingest.php)
```

## Privacy & Security
- The **key** gates access to a device’s data. Keep it secret.
- All traffic should be served over **HTTPS** end-to-end.
- The server stores points in a local **SQLite** database on your host.
- No third-party trackers or CDNs. You self-host Leaflet and assets.
- You can rotate a key: update it both in Home Assistant options and use the new key for login; old data remains but becomes inaccessible unless you keep the old key.

## Notes
- The integration debounces identical coordinates and posts only on state changes that contain `latitude`/`longitude` attributes.
- You can add multiple devices and edit or delete them later via the integration options menu.
