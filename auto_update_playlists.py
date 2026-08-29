#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت تحديث تلقائي لقوائم IPTV من موقع ELAHMAD
يمكن تشغيله يدوياً أو عبر GitHub Actions للحصول على قوائم محدثة دائماً
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

# إصلاح مشكلة الترميز على Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# إعدادات
BASE = "https://www.elahmad.ru/tv"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# التعامل مع الأنواع المختلفة من القنوات
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.8,en;q=0.6",
}

# تثبيت المكتبات المطلوبة
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
    """فك تشفير الروابط المشفرة من موقع ELAHMAD"""
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
    """تنظيف اسم الملف"""
    s = re.sub(r'[<>:"/\\|?*]', '_', name)
    s = s.strip().strip('.')
    return s[:80] or 'unnamed'

def collect_channels(session, categories, delay=0.3):
    """جمع القنوات من الموقع"""
    results = []
    for cat_id, cat_name in categories.items():
        print(f"⏳ {cat_name}...", end=" ", flush=True)
        url = f"{BASE}/mobile-live-stream/?id={cat_id}"
        try:
            r = session.get(url, timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f"✗ فشل: {e}")
            continue
        html = r.text

        channels_in_cat = []
        seen = set()
        
        for m in re.finditer(r'<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', html, re.IGNORECASE):
            href = m.group(1).strip()
            text_raw = m.group(2)
            text = re.sub(r'<[^>]+>', '', text_raw).strip()
            text = re.sub(r'\s+', ' ', text)

            is_stream = False
            stream_id = None
            player_type = None
            
            if 'glarb.php?id=' in href:
                qs = parse_qs(urlparse(href).query)
                stream_id = qs.get('id', [None])[0]
                player_type = 'glarb'
                is_stream = True
            elif 'alkass_hd.php?id=' in href:
                qs = parse_qs(urlparse(href).query)
                stream_id = qs.get('id', [None])[0]
                player_type = 'alkass'
                is_stream = True
            elif '/live/sl.php?id=' in href or '/live_stream.php?id=' in href or 'arabic-tv-online.php?id=' in href:
                qs = parse_qs(urlparse(href).query)
                stream_id = qs.get('id', [None])[0]
                player_type = 'other'
                is_stream = True
            elif 'youtube.php?id=' in href:
                qs = parse_qs(urlparse(href).query)
                stream_id = qs.get('id', [None])[0]
                player_type = 'youtube'
                is_stream = True

            if is_stream and stream_id and text and stream_id not in seen:
                seen.add(stream_id)
                full_href = href if href.startswith("http") else urljoin(url, href)
                channels_in_cat.append({
                    "category": cat_name,
                    "name": text,
                    "stream_id": stream_id,
                    "player_url": full_href,
                    "player_type": player_type,
                })

        print(f"✔ {len(channels_in_cat)} قنوات")
        results.extend(channels_in_cat)
        time.sleep(delay)
    return results

def extract_from_player_page(session, player_url):
    """استخراج المعلومات من صفحة المشغل"""
    try:
        r = session.get(player_url, timeout=20)
        html = r.text
    except Exception:
        return None, None, None
    
    csrf = None
    m1 = re.search(r'<meta[^>]*name=["\']csrf-token["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m1:
        csrf = m1.group(1)
    else:
        m2 = re.search(r'csrfToken\s*=\s*["\']([^"\']+)["\']', html)
        if m2:
            csrf = m2.group(1)
    
    embed_m = re.search(r'embed_result\s*=\s*["\']([^"\']+)["\']', html)
    embed_path = embed_m.group(1) if embed_m else "/tv/result/embed_result_elahmad_81.php"
    
    stream_page_id = None
    qs = parse_qs(urlparse(player_url).query)
    stream_page_id = qs.get('id', [None])[0]
    
    return csrf, stream_page_id, embed_path

def resolve_stream(session, ch):
    """الحصول على رابط البث الحقيقي"""
    if ch["player_type"] == "youtube":
        return None
    
    csrf, stream_id, embed_path = extract_from_player_page(session, ch["player_url"])
    if not stream_id:
        return None
    
    embed_url = urljoin("https://www.elahmad.ru", embed_path)
    if not csrf:
        csrf = ""
    
    body = f"id={requests.utils.quote(stream_id)}&csrf_token={requests.utils.quote(csrf)}"
    try:
        r = session.post(embed_url, data=body, headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ch["player_url"],
        }, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    
    if data.get("error"):
        return None
    
    l4 = data.get("link_4")
    k = data.get("key")
    iv = data.get("iv")
    if not (l4 and k and iv):
        return None
    
    return aes_decrypt_elahmad(l4, k, iv)

def build_m3u(channels, filename):
    """بناء ملف M3U"""
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
    """حفظ بيانات JSON"""
    p = os.path.join(OUTPUT_DIR, filename)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return p

def main():
    """الوظيفة الرئيسية"""
    os.chdir(OUTPUT_DIR)
    print("=" * 70)
    print("تحديث قوائم IPTV من موقع ELAHMAD")
    print(f"وقت البدء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    if not HAS_PYCRYPTODOME:
        print("تحذير: مكتبة pycryptodome غير متوفرة - لن يتم فك تشفير الروابط")
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # جمع القنوات
    print("\n[1/3] جمع القنوات من الموقع...")
    all_channels = collect_channels(session, POPULAR_CATEGORIES)
    print(f"إجمالي القنوات: {len(all_channels)}")
    
    # حفظ البيانات الأولية
    save_json(all_channels, "elahmad_channels_raw.json")
    
    # بناء ملف M3U بالروابط الأولية
    build_m3u(all_channels, "elahmad_with_player_pages.m3u")
    
    # فك تشفير الروابط الحقيقية
    if HAS_PYCRYPTODOME:
        print("\n[2/3] فك تشفير روابط البث الحقيقية...")
        targets = [c for c in all_channels if c["player_type"] in ("glarb", "alkass", "other")]
        print(f"القنوات المستهدفة: {len(targets)}")
        
        resolved = []
        ok = 0
        for idx, ch in enumerate(targets, 1):
            short_name = ch["name"][:40] if len(ch["name"]) > 40 else ch["name"]
            print(f"[{idx}/{len(targets)}] {short_name}...", end=" ", flush=True)
            
            try:
                url = resolve_stream(session, ch)
            except Exception:
                url = None
            
            ch2 = dict(ch)
            if url:
                ok += 1
                ch2["stream_url"] = url
                print("OK")
            else:
                print("FAILED")
            resolved.append(ch2)
            time.sleep(0.5)
        
        # إضافة قنوات YouTube
        for c in all_channels:
            if c["player_type"] == "youtube":
                ch2 = dict(c)
                ch2["stream_url"] = c["player_url"]
                resolved.append(ch2)
        
        print(f"نجح فك تشفير: {ok} من {len(targets)}")
        
        # حفظ الروابط المفكوكة
        save_json(resolved, "elahmad_channels_resolved.json")
        
        # بناء ملف M3U بالروابط الحقيقية
        only_real = [c for c in resolved if c.get("stream_url")]
        if only_real:
            build_m3u(only_real, "elahmad_live_real_streams.m3u")
            print(f"تم إنشاء ملف M3U بالروابط الحقيقية: {len(only_real)} قناة")
            
            # بناء ملفات حسب الفئة
            by_cat = {}
            for c in only_real:
                by_cat.setdefault(c["category"], []).append(c)
            
            for cat_name, cat_chs in by_cat.items():
                fn = safe_filename(cat_name)
                build_m3u(cat_chs, f"elahmad_{fn.replace(' ', '_')}_REAL_HLS.m3u")
    else:
        print("\n[2/3] تخطي فك التشفير - استخدام الروابط الأولية")
        only_real = all_channels
        build_m3u(only_real, "elahmad_live_real_streams.m3u")
    
    # إنشاء ملف محسّن
    print("\n[3/3] إنشاء ملف محسّن...")
    if only_real:
        build_m3u(only_real, "ELAHMAD_LIVE_CLEAN_100%.m3u")
        print("تم إنشاء الملف المحسّن")
    
    # حفظ الملخص
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_channels": len(all_channels),
        "resolved_channels": len(only_real),
        "categories_count": len(POPULAR_CATEGORIES),
        "pycryptodome": HAS_PYCRYPTODOME,
    }
    save_json(summary, "elahmad_summary.json")
    
    print("\n" + "=" * 70)
    print("اكتمل التحديث بنجاح!")
    print(f"وقت الانتهاء: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"إجمالي القنوات: {len(all_channels)}")
    print(f"القنوات المفكوكة: {len(only_real)}")
    print("=" * 70)

if __name__ == "__main__":
    main()