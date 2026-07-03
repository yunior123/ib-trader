#!/usr/bin/env python3
"""webhook_defense.py - candado de webhooks del guild. Borra TODO webhook no whitelisteado.

LaunchAgent: com.ibtrader.webhookdefense (RunAtLoad + KeepAlive).
Evidencia de cada intruso: config/defensa_intruso_<id>.json  Log: config/defensa_webhooks.log
"""
import json, sys, time, os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discord_client as dc

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(REPO, 'config')

gid = dc.guild_id()
WHITELIST = set()  # CANDADO TOTAL: cualquier webhook que aparezca se borra
log = open(os.path.join(CFG, 'defensa_webhooks.log'), 'a')

def say(msg):
    line = '%s %s' % (datetime.now(timezone.utc).isoformat(), msg)
    print(line, flush=True)
    log.write(line + chr(10))
    log.flush()

say('DEFENSA ACTIVA - whitelist: %s' % WHITELIST)
while True:
    try:
        hooks = dc.request('GET', '/guilds/%s/webhooks' % gid)
        for w in hooks:
            if w.get('name') not in WHITELIST:
                say('INTRUSO: webhook %r id=%s canal=%s creador=%s -> BORRANDO' %
                    (w.get('name'), w['id'], w.get('channel_id'), (w.get('user') or {}).get('username')))
                with open(os.path.join(CFG, 'defensa_intruso_%s.json' % w['id']), 'w') as f:
                    json.dump(w, f, indent=1)
                try:
                    dc.request('DELETE', '/webhooks/%s' % w['id'])
                    say('  borrado OK')
                except dc.DiscordError as ex:
                    say('  fallo: %s' % ex)
    except dc.DiscordError as ex:
        say('ERROR API: %s' % ex)
    time.sleep(30)
