#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-update script for IPTV playlists from ELAHMAD website
Can be run manually or via GitHub Actions
"""

import os
import sys
import json
import time
import requests
import re
import base64
from urllib.parse import urljoin, urlparse, parse_qs
from collections import OrderedDict
from datetime import datetime

# Fix encoding issues on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Settings
BASE = "https://www.elahmad.ru/tv"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Channel categories with English filenames
POPULAR_CATEGORIES = OrderedDict([
    ("qatar", "قنوات قطر - الجزيرة"),
    ("saudi", "قنوات السعودية - SBC وMBC والرياضية"),
    ("uae", "قنوات الامارات - دبي وابوظبي"),
    ("egypt", "قنوات مصرية - CBC وON وAlNahartv"),
    ("shahid_mbc", "قنوات ام بي سي MBC Group"),
    ("rotana_group", "قنوات روتانا Rotana Group"),
    ("artonline", "قنوات ART Group"),
    ("sports_live_tv", "قنوات رياضية - BeIN وSSC وغيرها"),
    ("almajdtv", "شبكة المجد الفضائية Almajd"),
    ("kids_tv", "قنوات اطفال Kids TV"),
    ("arabic", "قنوات عربية عالمية"),
    ("jordan", "قنوات الاردن"),
    ("lebanon", "قنوات لبنان"),
    ("kuwait", "قنوات الكويت"),
    ("morocco", "قنوات المغرب"),
    ("tunisia", "قنوات تونس"),
    ("algeria", "قنوات الجزائر"),
    ("turkish_tv", "قنوات تركية"),
])

# Mapping for simple English filenames
CATEGORY_FILENAME_MAP = {
    "قنوات قطر - الجزيرة": "qatar_channels",
    "قنوات السعودية - SBC وMBC والرياضية": "saudi_channels",
    "قنوات الامارات - دبي وابوظبي": "uae_channels",
    "قنوات مصرية - CBC وON وAlNahartv": "egypt_channels",
    "قنوات ام بي سي MBC Group": "mbc_channels",
    "قنوات روتانا Rotana Group": "rotana_channels",
    "قنوات ART Group": "art_channels",
    "قنوات رياضية - BeIN وSSC وغيرها": "sports_channels",
    "شبكة المجد الفضائية Almajd": "almajd_channels",
    "قنوات اطفال Kids TV": "kids_channels",
    "قنوات عربية عالمية": "arabic_channels",
    "قنوات الاردن": "jordan_channels",
    "قنوات لبنان": "lebanon_channels",
    "قنوات الكويت": "kuwait_channels",
    "قنوات المغرب": "morocco_channels",
    "قنوات تونس": "tunisia_channels",
    "قنوات الجزائر": "algeria_channels",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.8,en;q=0.6",
}

# Install required libraries
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    HAS_PYCRYPTODOME = True
except ImportError:
    HAS_PYCRYPTODOME = False
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pycryptodome", "-q"])
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        HAS_PYCRYPTODOME = True
    except Exception:
        pass

def aes_decrypt_elahmad(link_4_b64, key_hex, iv_hex):
    """Decrypt encrypted links from ELAHMAD website"""
    if not HAS_PYCRYPTODOME:
        return None
    try:
        ct = base64.b64decode(link_4_b64)
        kb = bytes.fromhex(key_hex)
        ib = bytes.fromhex(iv_hex)
        cipher = AES.new(kb, AES.MODE_CBC, ib)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        s = pt.decode("utf-8", errors="replace").strip("\x00\r\n\t ")
        s = s.rstrip("\x00").strip()
        if s and (s.startswith("http://") or s.startswith("https://")):
            return s
        return s or None
    except Exception:
        return None

def safe_filename(name):
    """Clean filename"""
    s = re.sub(r'[<>:"/\\|?*]', '_', name)
    s = s.strip().strip('.')
    return s[:80] or 'unnamed'

REFERER = "https://www.elahmad.ru/tv/mobile-live-stream/"


def classify_href(href):
    """Return (player_type, stream_id) for a recognized elahmad player link."""
    if 'glarb.php?id=' in href:
        return 'glarb', parse_qs(urlparse(href).query).get('id', [None])[0]
    if 'watchtv.php?id=' in href:
        return 'watchtv', parse_qs(urlparse(href).query).get('id', [None])[0]
    if 'rotanatv.php?id=' in href:
        return 'rotanatv', parse_qs(urlparse(href).query).get('id', [None])[0]
    if 'alkass_hd.php?id=' in href:
        return 'alkass', parse_qs(urlparse(href).query).get('id', [None])[0]
    if '/live/sl.php?id=' in href or '/live_stream.php?id=' in href or 'arabic-tv-online.php?id=' in href:
        return 'other', parse_qs(urlparse(href).query).get('id', [None])[0]
    if '/live/channels.php?id=' in href:
        return 'shahid_channels', parse_qs(urlparse(href).query).get('id', [None])[0]
    if 'shahid_shaka.php?id=' in href:
        return 'shahid_dash', parse_qs(urlparse(href).query).get('id', [None])[0]
    if 'youtube.php?id=' in href:
        return 'youtube', parse_qs(urlparse(href).query).get('id', [None])[0]
    return None, None


def collect_channels(session, categories, delay=0.3):
    """Collect channels from website (recognizes all player link types)."""
    results = []
    for cat_id, cat_name in categories.items():
        print(f"Processing category {cat_id}...", end=" ", flush=True)
        url = f"{BASE}/mobile-live-stream/?id={cat_id}"
        try:
            r = session.get(url, headers={"Referer": REFERER}, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"Failed: {e}")
            continue
        html = r.text

        channels_in_cat = []
        seen = set()
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', html, re.IGNORECASE):
            href = m.group(1).strip()
            text_raw = m.group(2)
            text = re.sub(r'<[^>]+>', '', text_raw).strip()
            text = re.sub(r'\s+', ' ', text)

            ptype, stream_id = classify_href(href)
            if ptype is None or not stream_id or not text:
                continue
            if stream_id in seen:
                continue
            seen.add(stream_id)
            full_href = href if href.startswith("http") else urljoin(url, href)
            channels_in_cat.append({
                "category": cat_name,
                "name": text,
                "stream_id": stream_id,
                "player_url": full_href,
                "player_type": ptype,
            })

        print(f"OK {len(channels_in_cat)} channels")
        results.extend(channels_in_cat)
        time.sleep(delay)
    return results


def find_csrf(html):
    m = re.search(r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)', html, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'csrfToken\s*=\s*["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


def post_embed(session, embed_path, payload, referer):
    url = urljoin("https://www.elahmad.ru", embed_path)
    try:
        r = session.post(url, data=payload, headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
        }, timeout=20)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def resolve_glarb(session, ch):
    """glarb.php -> mirror 'embed_result_elahmad_81.php' flow."""
    try:
        html = session.get(ch["player_url"], headers={"Referer": REFERER}, timeout=20).text
    except Exception:
        return None
    csrf = find_csrf(html)
    emb = re.search(r'embed_result\s*=\s*["\']([^"\']+)["\']', html)
    embed_path = emb.group(1) if emb else "/tv/result/embed_result_elahmad_81.php"
    body = f"id={requests.utils.quote(ch['stream_id'])}&csrf_token={requests.utils.quote(csrf or '')}"
    data = post_embed(session, embed_path, body, ch["player_url"])
    if not data or data.get("error"):
        return None
    l4 = data.get("link_4"); k = data.get("key"); iv = data.get("iv")
    if not (l4 and k and iv):
        return None
    return aes_decrypt_elahmad(l4, k, iv)


def resolve_watchtv(session, ch):
    """watchtv.php -> embed_result_watchtv.php with csrf."""
    try:
        html = session.get(ch["player_url"], headers={"Referer": REFERER}, timeout=20).text
    except Exception:
        return None
    if len(html) < 2000:
        return None
    csrf = find_csrf(html)
    if not csrf:
        return None
    body = f"id={requests.utils.quote(ch['stream_id'])}&csrf_token={requests.utils.quote(csrf)}"
    data = post_embed(session, "/tv/result/embed_result_watchtv.php", body, ch["player_url"])
    if not data or data.get("error"):
        return None
    l4 = data.get("link_4"); k = data.get("key"); iv = data.get("iv")
    if not (l4 and k and iv):
        return None
    return aes_decrypt_elahmad(l4, k, iv)


def resolve_rotanatv(session, ch):
    """rotanatv.php -> POST to same page with dynamic hash, fixed key/iv."""
    try:
        html = session.get(ch["player_url"], headers={"Referer": REFERER}, timeout=20).text
    except Exception:
        return None
    if len(html) < 2000:
        return None
    hm = re.search(r'\{([0-9a-f]{32})\s*:\s*["\']([^"\']+)["\']', html)
    if not hm:
        return None
    hashkey = hm.group(1)
    data = post_embed(session, ch["player_url"], {hashkey: ch["stream_id"]}, ch["player_url"])
    if not data:
        return None
    l4 = data.get("link_url_4") or data.get("link_4")
    if not l4:
        return None
    return aes_decrypt_elahmad(l4, "6bc94d5606eb1d2f10c2e29c81711abd", "ab3e5957703fe28a")


def resolve_stream(session, ch):
    """Get real stream URL by player type."""
    method = {
        "glarb": resolve_glarb,
        "watchtv": resolve_watchtv,
        "rotanatv": resolve_rotanatv,
    }.get(ch["player_type"])
    if method is None:
        return None
    return method(session, ch)


def test_playable(session, url):
    """Return True only if the URL actually serves a valid playlist (HTTP 200 + m3u8 content)."""
    if not url:
        return False
    if not re.search(r'\.(m3u8|mpd)(\?|$)', url):
        return False
    try:
        r = session.get(url, headers={"Referer": "https://www.elahmad.ru/"}, timeout=20)
    except Exception:
        return False
    if r.status_code != 200:
        return False
    body = r.text[:2000].upper()
    return "#EXTM3U" in body or "#EXT-X-STREAM-INF" in body or "#EXTINF" in body


def dedupe_by_name_and_id(channels):
    """Keep the first channel for each (name, stream_id) pair."""
    seen = set()
    out = []
    for ch in channels:
        key = (ch.get("name"), ch.get("stream_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(ch)
    return out

def build_m3u(channels, filename):
    """Build M3U file"""
    lines = ["#EXTM3U"]
    for ch in channels:
        url = ch.get("stream_url") or ch["player_url"]
        logo = ""
        grp = ch["category"]
        name = ch["name"]
        extinf = f'#EXTINF:-1 tvg-id="{ch["stream_id"]}" tvg-name="{name}" tvg-logo="{logo}" group-title="{grp}",{name}'
        lines.append(extinf)
        lines.append(url)
    lines.append("")
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return p

def save_json(obj, filename):
    """Save JSON data"""
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return p

def create_channel_links_file(channels, filename):
    """Create a simple text file with channel names and links"""
    lines = []
    lines.append("# Channel Links File")
    lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"# Total Channels: {len(channels)}")
    lines.append("# Format: Channel Name | Stream URL")
    lines.append("=" * 80)
    
    for ch in channels:
        name = ch["name"]
        url = ch.get("stream_url") or ch["player_url"]
        category = ch["category"]
        lines.append(f"{name} | {category} | {url}")
    
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Created channel links file: {filename}")
    return p

def create_channel_links_json(channels, filename):
    """Create a JSON file with channel information"""
    channel_data = []
    for ch in channels:
        channel_data.append({
            "name": ch["name"],
            "category": ch["category"],
            "stream_url": ch.get("stream_url") or ch["player_url"],
            "stream_id": ch["stream_id"],
            "player_type": ch["player_type"]
        })
    
    data = {
        "generated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_channels": len(channel_data),
        "channels": channel_data
    }
    
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Created channel links JSON: {filename}")
    return p

def create_channel_links_html(channels, filename):
    """Create an HTML file with clickable channel links"""
    html_content = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Arabic IPTV Channels</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            text-align: center;
            color: #333;
        }
        .info {
            text-align: center;
            color: #666;
            margin-bottom: 20px;
        }
        .category {
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 10px;
        }
        .category h2 {
            color: #2c3e50;
        }
        .channel {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px;
            border-bottom: 1px solid #eee;
            transition: background-color 0.3s;
        }
        .channel:hover {
            background-color: #f9f9f9;
        }
        .channel-name {
            font-weight: bold;
            color: #333;
        }
        .channel-link {
            color: #3498db;
            text-decoration: none;
            padding: 5px 10px;
            background-color: #ecf0f1;
            border-radius: 5px;
            font-size: 14px;
        }
        .channel-link:hover {
            background-color: #3498db;
            color: white;
        }
        .copy-btn {
            background-color: #27ae60;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 5px;
            cursor: pointer;
            margin-right: 10px;
        }
        .copy-btn:hover {
            background-color: #2ecc71;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📺 Arabic IPTV Channels</h1>
        <div class="info">
            <p>Generated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
            <p>Total Channels: """ + str(len(channels)) + """</p>
        </div>
"""
    
    # Group by category
    by_cat = {}
    for ch in channels:
        by_cat.setdefault(ch["category"], []).append(ch)
    
    for category, cat_channels in sorted(by_cat.items()):
        html_content += f'<div class="category">\n'
        html_content += f'    <h2>{category}</h2>\n'
        
        for ch in cat_channels:
            name = ch["name"]
            url = ch.get("stream_url") or ch["player_url"]
            html_content += f'    <div class="channel">\n'
            html_content += f'        <span class="channel-name">{name}</span>\n'
            html_content += f'        <div>\n'
            html_content += f'            <button class="copy-btn" onclick="copyToClipboard(\'{url}\')">Copy Link</button>\n'
            html_content += f'            <a href="{url}" class="channel-link" target="_blank">Open Stream</a>\n'
            html_content += f'        </div>\n'
            html_content += f'    </div>\n'
        
        html_content += f'</div>\n'
    
    html_content += """
    </div>
    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(function() {
                alert('Link copied to clipboard!');
            }, function(err) {
                console.error('Could not copy text: ', err);
            });
        }
    </script>
</body>
</html>
"""
    
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Created channel links HTML: {filename}")
    return p

def create_category_files_summary(by_cat, filename):
    """Create a summary file with all category playlist links"""
    lines = []
    lines.append("# Category Playlist Files")
    lines.append(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"# Total Categories: {len(by_cat)}")
    lines.append("# Format: Category Name | Filename | Channel Count")
    lines.append("=" * 80)
    
    for cat_name, cat_chs in sorted(by_cat.items()):
        if cat_name in CATEGORY_FILENAME_MAP:
            filename_key = f"{CATEGORY_FILENAME_MAP[cat_name]}.m3u"
        else:
            filename_key = f"{safe_filename(cat_name)}.m3u"
        
        lines.append(f"{cat_name} | {filename_key} | {len(cat_chs)} channels")
    
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Created category files summary: {filename}")
    return p

def main():
    """Main function"""
    os.chdir(OUTPUT_DIR)
    print("=" * 70)
    print("Updating IPTV playlists from ELAHMAD website")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if not HAS_PYCRYPTODOME:
        print("Warning: pycryptodome not available - will not decrypt links")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # Collect channels
    print("\n[1/3] Collecting channels from website...")
    all_channels = collect_channels(session, POPULAR_CATEGORIES)
    print(f"Total channels: {len(all_channels)}")
    
    # Save raw data
    save_json(all_channels, "elahmad_channels_raw.json")
    
    # Build M3U with initial links
    build_m3u(all_channels, "elahmad_with_player_pages.m3u")
    
    # Decrypt real stream URLs
    if HAS_PYCRYPTODOME:
        print("\n[2/3] Decrypting real stream URLs + playability test...")
        targets = [c for c in all_channels if c["player_type"] in ("glarb", "watchtv", "rotanatv")]
        print(f"Target channels: {len(targets)}")
        
        resolved = []
        ok = 0
        playable = 0
        for idx, ch in enumerate(targets, 1):
            print(f"[{idx}/{len(targets)}] Processing channel...", end=" ", flush=True)
            
            url = None
            try:
                url = resolve_stream(session, ch)
            except Exception:
                url = None
            
            ch2 = dict(ch)
            if url:
                ok += 1
                if test_playable(session, url):
                    playable += 1
                    ch2["stream_url"] = url
                    print("OK")
                else:
                    ch2["stream_url"] = url
                    ch2["not_playable"] = True
                    print("NOT-PLAYABLE")
            else:
                print("FAILED")
            resolved.append(ch2)
            time.sleep(0.5)
        
        # Add YouTube channels
        for c in all_channels:
            if c["player_type"] == "youtube":
                ch2 = dict(c)
                ch2["stream_url"] = c["player_url"]
                resolved.append(ch2)
        
        # Add non-decodable types (player page only)
        for c in all_channels:
            if c["player_type"] in ("shahid_dash", "shahid_channels", "alkass", "other"):
                ch2 = dict(c)
                ch2["note"] = "player_page_only"
                resolved.append(ch2)
        
        print(f"Successfully decrypted: {ok} of {len(targets)} (playable: {playable})")
        
        # Save resolved data
        save_json(resolved, "elahmad_channels_resolved.json")
        
        # Real streams = playable only (dead links excluded)
        only_real = [c for c in resolved if c.get("stream_url") and not c.get("not_playable")]
        # Remove duplicates (same name + id)
        before = len(only_real)
        only_real = dedupe_by_name_and_id(only_real)
        if len(only_real) != before:
            print(f"Removed {before - len(only_real)} duplicate channels (same name+id)")
        
        if only_real:
            build_m3u(only_real, "elahmad_live_real_streams.m3u")
            print(f"Created M3U file with real URLs: {len(only_real)} channels")
            
            # Build per-category files with English names
            by_cat = {}
            for c in only_real:
                by_cat.setdefault(c["category"], []).append(c)
            
            for cat_name, cat_chs in by_cat.items():
                if cat_name in CATEGORY_FILENAME_MAP:
                    filename = f"{CATEGORY_FILENAME_MAP[cat_name]}.m3u"
                else:
                    filename = f"{safe_filename(cat_name)}.m3u"
                build_m3u(cat_chs, filename)
                print(f"Created category file: {filename} ({len(cat_chs)} channels)")
    else:
        print("\n[2/3] Skipping decryption - using initial links")
        only_real = all_channels
        build_m3u(only_real, "elahmad_live_real_streams.m3u")
    
    # Create clean file
    print("\n[3/3] Creating clean file...")
    if only_real:
        build_m3u(only_real, "ELAHMAD_LIVE_CLEAN_100%.m3u")
        print("Clean file created")
        
        # Create individual channel links
        create_channel_links_file(only_real, "channel_links.txt")
        create_channel_links_json(only_real, "channel_links.json")
        create_channel_links_html(only_real, "channel_links.html")
        
        # Build per-category files with English names
        by_cat = {}
        for c in only_real:
            by_cat.setdefault(c["category"], []).append(c)
        
        for cat_name, cat_chs in by_cat.items():
            # Use English filename mapping if available, otherwise use safe filename
            if cat_name in CATEGORY_FILENAME_MAP:
                filename = f"{CATEGORY_FILENAME_MAP[cat_name]}.m3u"
            else:
                filename = f"{safe_filename(cat_name)}.m3u"
            build_m3u(cat_chs, filename)
            print(f"Created category file: {filename} ({len(cat_chs)} channels)")
        
        # Create category files summary
        create_category_files_summary(by_cat, "category_files.txt")
    
    # Save summary
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_channels": len(all_channels),
        "resolved_channels": len(only_real),
        "categories_count": len(POPULAR_CATEGORIES),
        "pycryptodome": HAS_PYCRYPTODOME,
    }
    save_json(summary, "elahmad_summary.json")
    
    print("\n" + "=" * 70)
    print("Update completed successfully!")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total channels collected: {len(all_channels)}")
    print(f"Working/playable channels (after clean + dedupe): {len(only_real)}")
    print("=" * 70)

if __name__ == "__main__":
    main()