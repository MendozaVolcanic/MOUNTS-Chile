"""
Notificacion via Telegram cuando se detectan anomalias nuevas.

Lee de mounts.db las anomalias con detected_at en este run (los ultimos 30
minutos) que NO esten en una tabla local notified_alerts. Manda mensaje al
bot configurado, marca como notificadas. Idempotente — re-correr no spam.

Requiere variables de entorno:
    TELEGRAM_BOT_TOKEN  — del @BotFather
    TELEGRAM_CHAT_ID    — id del chat o canal a notificar

Si las env vars no estan, el script termina silenciosamente (no falla el
pipeline). Eso permite usarlo opcional en local sin configuracion.

Uso:
    python notify_telegram.py
    python notify_telegram.py --dry-run   # solo muestra que enviaria
    python notify_telegram.py --test      # manda un mensaje de prueba

Setup del bot (una vez):
    1. Telegram: chat con @BotFather, /newbot, anota TOKEN
    2. @BotFather: /mybots, elegi el bot, Bot Settings -> Allow Groups
    3. Agrega el bot a un grupo o chateale directo
    4. https://api.telegram.org/bot<TOKEN>/getUpdates -> copia 'chat.id'
    5. En GitHub repo -> Settings -> Secrets:
       TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
"""

import argparse
import io
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# Force UTF-8 stdout para que el dry-run con emojis funcione en Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "mounts.db"

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

SEV_EMOJI = {
    "red":    "🔴",
    "orange": "🟠",
    "yellow": "🟡",
    "green":  "🟢",
    "stale":  "⚫",
}


def get_credentials():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat  = os.environ.get("TELEGRAM_CHAT_ID")
    return token, chat


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    r = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }, timeout=15)
    r.raise_for_status()
    return r.json()


def ensure_notified_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notified_alerts (
            anomaly_id INTEGER PRIMARY KEY,
            notified_at TEXT NOT NULL
        )
    """)
    conn.commit()


def fetch_new_anomalies(conn, lookback_minutes: int = 30):
    """
    Anomalias con detected_at reciente que aun NO se hayan notificado.
    Filtra a las relevantes (z>=3, no persistente puede pasar; persistente
    siempre se notifica).
    """
    ensure_notified_table(conn)
    cur = conn.execute("""
        SELECT a.id, a.volcano_key, v.name, a.product, a.date, a.value,
               a.zscore, a.severity, a.detected_at
        FROM anomalies a
        JOIN volcanoes v ON v.key = a.volcano_key
        LEFT JOIN notified_alerts n ON n.anomaly_id = a.id
        WHERE n.anomaly_id IS NULL
          AND a.detected_at > datetime('now', '-' || ? || ' minutes')
          AND a.zscore >= 3
        ORDER BY a.zscore DESC
    """, (lookback_minutes,))
    return cur.fetchall()


def fetch_new_multi_alerts(conn, lookback_minutes: int = 30):
    cur = conn.execute("""
        SELECT id, volcano_key, date_center, products, n_products,
               zscore_max, confidence
        FROM multi_alerts
        WHERE detected_at > datetime('now', '-' || ? || ' minutes')
        ORDER BY n_products DESC, zscore_max DESC
    """, (lookback_minutes,))
    return cur.fetchall()


def format_anomaly_message(anoms, multis):
    """Mensaje HTML para Telegram."""
    lines = [
        "🌋 <b>MOUNTS-Chile · Nuevas anomalías detectadas</b>",
        f"⏱ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
    ]

    if multis:
        lines.append(f"<b>🔗 Multi-producto (cross-sensor) — {len(multis)} eventos</b>")
        for _, vol, date, prods_json, n_prods, zmax, conf in multis[:5]:
            import json as _json
            try:
                prods = _json.loads(prods_json)
                prods_str = "+".join(p.upper() for p in prods)
            except (ValueError, TypeError):
                prods_str = prods_json
            z_disp = f">+50σ" if zmax > 50 else f"+{zmax:.1f}σ"
            emoji = "🚨" if conf == "high" else "⚠️"
            lines.append(f"  {emoji} <b>{vol}</b> {date[:10]}: {prods_str} ({z_disp})")
        lines.append("")

    if anoms:
        lines.append(f"<b>📊 Single-producto — {len(anoms)} detecciones</b>")
        for _, vol_k, vol_name, prod, date, val, z, sev, _ in anoms[:10]:
            emoji = SEV_EMOJI.get(sev, "•")
            z_disp = f">+50σ" if z > 50 else f"+{z:.1f}σ"
            lines.append(
                f"  {emoji} <b>{vol_name}</b> {prod.upper()} "
                f"{date[:10]}: {val:.3g} ({z_disp})"
            )
        if len(anoms) > 10:
            lines.append(f"  <i>... +{len(anoms)-10} adicionales</i>")
        lines.append("")

    lines.append('📈 <a href="https://mendozavolcanic.github.io/MOUNTS-Chile/">Ver dashboard</a>')
    return "\n".join(lines)


def mark_notified(conn, anomaly_ids):
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "INSERT OR IGNORE INTO notified_alerts(anomaly_id, notified_at) VALUES (?,?)",
        [(aid, now) for aid in anomaly_ids],
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra que se enviaria, no manda")
    parser.add_argument("--test", action="store_true",
                        help="Manda mensaje de prueba")
    parser.add_argument("--lookback-min", type=int, default=30,
                        help="Anomalias detectadas en ultimos N minutos (default 30)")
    args = parser.parse_args()

    token, chat = get_credentials()
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados; skip notificacion.")
        print("Setup: ver docstring de notify_telegram.py")
        return 0

    if args.test:
        send_message(token, chat,
                     "🌋 <b>MOUNTS-Chile</b> · test de notificación OK")
        print("Test enviado.")
        return 0

    if not DB_PATH.exists():
        print("mounts.db no existe; nada que notificar")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    try:
        anoms = fetch_new_anomalies(conn, args.lookback_min)
        multis = fetch_new_multi_alerts(conn, args.lookback_min)

        if not anoms and not multis:
            print("Sin anomalias nuevas; nada que notificar")
            return 0

        msg = format_anomaly_message(anoms, multis)
        print(f"Anomalias nuevas: {len(anoms)} single, {len(multis)} multi-product")

        if args.dry_run:
            print("--- mensaje que se enviaria ---")
            print(msg)
            return 0

        try:
            resp = send_message(token, chat, msg)
            print(f"Mensaje enviado (msg_id={resp.get('result',{}).get('message_id')})")
            mark_notified(conn, [a[0] for a in anoms])
        except requests.RequestException as e:
            print(f"ERROR enviando Telegram: {e}")
            return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
