# ROAD6 cloud monitor -- runs on GitHub Actions every 15 min, 7x24, PC-independent.
# News: Yahoo Finance RSS per stock (HK media, trad-chinese).
# Prices: Tencent fqkline day-K (last bar = live price intraday).
# Push: Bark -> iPhone. State: state.json committed back to repo by workflow.
# Rev: road6-cloud 20261014a

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

HKT = timezone(timedelta(hours=8))
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json')
BARK_KEY = os.environ.get('BARK_KEY', '')
GROUP = 'road6'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

STOCKS = [
    {'yahoo': '1810.HK', 'tencent': 'hk01810', 'name': '小米集团-W'},
    {'yahoo': '0883.HK', 'tencent': 'hk00883', 'name': '中海油H'},
    {'yahoo': '0700.HK', 'tencent': 'hk00700', 'name': '腾讯控股'},
    {'yahoo': '0941.HK', 'tencent': 'hk00941', 'name': '中移动H'},
    {'yahoo': '3998.HK', 'tencent': 'hk03998', 'name': '波司登'},
    {'yahoo': '2899.HK', 'tencent': 'hk02899', 'name': '紫金矿业'},
    {'yahoo': '2020.HK', 'tencent': 'hk02020', 'name': '安踏体育'},
]

# -- price alert rules ------------------------------------------------------
# zone: push once while close inside [lo, hi]; re-arm after close leaves range.
# cross_up: push when close >= level (level desc); re-arm when close < level*0.97.
# cross_down: push when close <= level; urgent if 'urgent'; re-arm close > level*1.03.
PRICE_ALERTS = {
    'hk01810': {
        'cross_up': [(27.50, 'T1 减持 1/3'), (31.00, 'T2 减持'), (33.00, 'T3 减持')],
        'cross_down': [(21.30, '跌破 21.30 止损线', True)],
    },
    'hk00883': {'zone': (23.50, 24.00, 'B1 买入区间 23.50-24.00')},
    'hk00941': {'zone': (78.00, 79.00, 'B1 买入区间 78-79')},
    'hk03998': {'zone': (4.20, 4.35, 'B1 买入区间 4.20-4.35')},
    'hk00700': {'zone': (400.0, 410.0, 'DV 买入区间 400-410')},
    'hk02899': {'zone': (30.9, 31.5, 'B1 买入区间 30.9-31.5')},
    'hk02020': {'zone': (70.0, 72.0, '回踩加仓区间 70-72')},
}

# -- news scoring (subset of local ROAD6_MONITOR rules) ---------------------
KEY3 = ['锁单', '订单', '出货量', '交付', '财报', '业绩', '盈警', '盈喜', '召回',
        '评级', '目标价', '升', '下调', '回购', '增持', '减持', '停牌', '复牌',
        '收购', '并购', '私有化', '违约', '调查', '诉讼', '罚款', '处罚',
        '退市', '中标', '合同', '量产', '获批', '研发失败']
KEY2 = ['发布', '推出', '合作', '签约', '分红', '派息', '战略', '融资',
        '新品', '涨价', '降价', '扩产', '中标', '上榜']


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', 'replace')


def bark(title, body, level='active'):
    """Push to iPhone via Bark. level: active | timeSensitive | critical."""
    if not BARK_KEY:
        print('[bark] no key, skip:', title)
        return False
    url = ('https://api.day.app/%s/%s/%s?group=%s&level=%s'
           % (BARK_KEY, urllib.parse.quote(title), urllib.parse.quote(body),
              GROUP, level))
    try:
        out = http_get(url, timeout=15)
        ok = '"code":200' in out
        print('[bark]', 'OK' if ok else 'FAIL', title)
        return ok
    except Exception as e:
        print('[bark] error:', e)
        return False


def fetch_rss(yahoo_code):
    """Return [{title, link, date}] from Yahoo Finance headline RSS."""
    url = ('https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s'
           '&region=HK&lang=zh-Hant' % urllib.parse.quote(yahoo_code))
    try:
        txt = http_get(url)
        root = ET.fromstring(txt)
    except Exception as e:
        print('[rss] %s error: %s' % (yahoo_code, e))
        return []
    items = []
    for it in root.iter('item'):
        t = (it.findtext('title') or '').strip()
        l = (it.findtext('link') or '').strip()
        d = (it.findtext('pubDate') or '').strip()
        if t:
            items.append({'title': t, 'link': l, 'date': d})
    return items


def score_title(title):
    sc = 0
    for k in KEY3:
        if k in title:
            sc = 3
            break
    if sc < 3:
        for k in KEY2:
            if k in title:
                sc = 2
                break
    return sc


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print('[state] load error, fresh start:', e)
    return {'seen': {}, 'fired': {}, 'digest_date': '', 'digest_items': [],
            'baselined': False}


def save_state(st):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def get_price(tencent_code):
    """Live/last price from Tencent fqkline (last day bar close)."""
    url = ('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s,day,,,2,qfq'
           % tencent_code)
    try:
        data = json.loads(http_get(url))
        bars = data['data'][tencent_code].get('day') or []
        if bars:
            return float(bars[-1][2]), bars[-1][0]
    except Exception as e:
        print('[price] %s error: %s' % (tencent_code, e))
    return None, None


def check_price(sym, name, price, day, st, first_run):
    rules = PRICE_ALERTS.get(sym)
    if not rules or price is None:
        return
    fired = st['fired'].setdefault(sym, {})

    def push(msg, urgent=False):
        bark('%s %s' % (name, '价格提醒' if not urgent else '急报'),
             '%s\n现价 %.2f (%s)\n-- ROAD6 云端监控' % (msg, price, day),
             'timeSensitive' if urgent else 'active')

    z = rules.get('zone')
    if z:
        lo, hi, desc = z
        key = 'zone'
        inside = lo <= price <= hi
        if inside and not fired.get(key):
            if first_run:
                print('[price] %s in zone (baseline, no push)' % sym)
            else:
                push('进入 %s，现价 %.2f' % (desc, price))
            fired[key] = True
        elif not inside and fired.get(key):
            fired[key] = False
            print('[price] %s left zone, re-armed' % sym)

    for level, desc in rules.get('cross_up', []):
        key = 'up:%s' % level
        if price >= level and not fired.get(key):
            if first_run:
                print('[price] %s above %s (baseline)' % (sym, level))
            else:
                push('上穿 %.2f -- %s' % (level, desc))
            fired[key] = True
        elif price < level * 0.97 and fired.get(key):
            fired[key] = False

    for rule in rules.get('cross_down', []):
        level, desc = rule[0], rule[1]
        urgent = rule[2] if len(rule) > 2 else False
        key = 'dn:%s' % level
        if price <= level and not fired.get(key):
            if first_run:
                print('[price] %s below %s (baseline)' % (sym, level))
            else:
                push('跌破 %.2f -- %s' % (level, desc), urgent=urgent)
            fired[key] = True
        elif price > level * 1.03 and fired.get(key):
            fired[key] = False


def main():
    now = datetime.now(HKT)
    today = now.strftime('%Y-%m-%d')
    st = load_state()
    first_run = not st.get('baselined')
    hard_hits, soft_items = 0, []

    # 1) news scan
    for s in STOCKS:
        sym = s['tencent']
        seen = st['seen'].setdefault(sym, [])
        for item in fetch_rss(s['yahoo']):
            key = item['link'] or item['title']
            if key in seen:
                continue
            seen.append(key)
            sc = score_title(item['title'])
            if first_run:
                continue  # baseline run: record only, no push
            line = '%s | %s' % (s['name'], item['title'])
            if sc >= 3:
                hard_hits += 1
                bark('新闻脉冲: %s' % s['name'],
                     '%s\n\n(Yahoo 港股源, 云端自动推送)' % item['title'])
            elif sc == 2:
                soft_items.append(line)

    # 2) price checks
    for s in STOCKS:
        price, day = get_price(s['tencent'])
        check_price(s['tencent'], s['name'], price, day, st, first_run)
        if price is not None:
            print('[price] %s %.2f (%s)' % (s['tencent'], price, day))

    # 3) daily digest after HK close (first run at/after 16:10 HKT each day)
    digest_due = (now.hour > 16 or (now.hour == 16 and now.minute >= 10)) \
        and st.get('digest_date') != today
    if digest_due:
        lines = []
        for x in soft_items[:8]:
            lines.append('- %s' % x)
        body = ('今日一般新闻 %d 条:\n%s\n\n(云端监控, 硬事件已单独推送)'
                % (len(soft_items), '\n'.join(lines) if lines else '(无)'))
        bark('ROAD6 每日汇总 %s' % today, body)
        st['digest_date'] = today
        print('[digest] sent, %d soft items' % len(soft_items))

    # 4) trim seen lists
    for sym in st['seen']:
        del st['seen'][sym][:-200]
    st['baselined'] = True
    save_state(st)
    print('[done] HKT %s, hard=%d, soft=%d, first_run=%s'
          % (now.strftime('%H:%M'), hard_hits, len(soft_items), first_run))


if __name__ == '__main__':
    sys.exit(main())
