"""Diamas'ın sade dil görünümü: hiç bilmeyen biri için cümleler, robot kartları, hava durumu.

run_live.build() bu modülün parts() fonksiyonunu çağırır; dönen sözlük şablondaki {{...}}
yer tutucularını doldurur. Rakamlar, eski (uzman) görünümle aynı kaynaktan gelir.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

GUN = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

SEKTOR = {
    "Information Technology": "Teknoloji", "Communication Services": "İletişim, medya",
    "Consumer Discretionary": "Tüketim, perakende", "Consumer Staples": "Gıda, temel tüketim",
    "Health Care": "Sağlık, ilaç", "Financials": "Finans", "Industrials": "Sanayi", "Energy": "Enerji",
    "Utilities": "Elektrik, su", "Real Estate": "Gayrimenkul", "Materials": "Hammadde, kimya",
}

ROBOT = {
    "pead": dict(emoji="📋", name="Karne Avcısı",
                 rule="Bir şirketin <span class='term' data-t='bilanco'>karnesi</span> beklenenden iyi gelir ve hissesi "
                      "o gün yükselirse alır. 10 gün tutar, satar."),
    "rsi2": dict(emoji="🏷️", name="İndirim Avcısı",
                 rule="Genelde iyi giden bir hisse birkaç gün üst üste sert düşerse \"indirim\" sayıp alır. "
                      "Toparlanınca ya da en geç 10 günde satar. Borsada panik varsa hiç almaz."),
    "trend": dict(emoji="⛵", name="Rüzgâr Takipçisi",
                  rule="<span class='term' data-t='spy'>Borsanın tamamını</span> alır. Borsa yokuş aşağı dönünce satar "
                       "ve <span class='term' data-t='nakit'>nakitte</span> bekler."),
}
ORDER = ["pead", "rsi2", "trend"]


def esc(x):
    return html.escape(str(x))


def usd(x):
    return f"{x:,.0f}".replace(",", ".") + " $"


def yuzde(x, d=1, sign=True):
    """−%2,4 biçimi (Türkçe ondalık virgül)."""
    if x is None or not np.isfinite(x):
        return "–"
    s = "−" if x < 0 else ("+" if sign and x > 0 else "")
    return f"{s}%{abs(x) * 100:.{d}f}".replace(".", ",")


def renk(x):
    return "pos" if x > 0 else ("neg" if x < 0 else "")


def tarih(d):
    return f"{d.day} {AY[d.month - 1]}"


# ---------------------------------------------------------------- şirket adları
_SON_EK = r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Companies|Co\.|plc|Holdings|Group|Platforms|" \
          r"Technologies|Pharmaceuticals)$"


def kisa_ad(n: str) -> str:
    n = re.sub(r"\s*\(.*?\)", "", n).strip()
    while True:
        m = re.sub(_SON_EK, "", n).strip()
        if m == n or not m:
            return n
        n = m


def sirketler():
    try:
        sp = pd.read_parquet(ROOT / "data" / "sp500.parquet").set_index("ticker")
    except Exception:  # noqa: BLE001
        return {}
    return {t: (kisa_ad(r["name"]), SEKTOR.get(r["sector"], "")) for t, r in sp.iterrows()}


SIRKET: dict = {}


def ad(t):
    if t == "SPY":
        return "Borsa sepeti"
    return SIRKET.get(t, (t, ""))[0]


def sektor(t):
    if t == "SPY":
        return "500 şirket"
    return SIRKET.get(t, ("", ""))[1]


def ad_sektor(t):
    s = sektor(t)
    return f"<b>{esc(ad(t))}</b>" + (f" ({esc(s.lower())})" if s else "")


# ---------------------------------------------------------------- bölümler
def hero(eq, total, spy_v, cap):
    days = len(eq)
    r_pnl, s_pnl = total - cap, spy_v - cap
    ret, spy_ret = total / cap - 1, spy_v / cap - 1
    diff = ret - spy_ret
    sure = f"{days} gün" if days < 10 else f"{round(days / 5)} hafta"
    sure_de = sure + ("de" if days < 10 else "da")
    lead = (f"9 Ekim'de {usd(cap)} ile başladılar. {sure_de} "
            + (f"<b class='pos'>{usd(r_pnl)} kazandılar</b>." if r_pnl >= 0 else f"<b class='neg'>{usd(-r_pnl)} kaybettiler</b>."))
    if abs(diff) < 0.01:
        head = "Başa baş, robotlar azıcık " + ("önde." if diff >= 0 else "geride.")
    elif diff > 0:
        head = "Robotlar borsadan iyi gidiyor."
    else:
        head = "Robotlar borsanın gerisinde."
    cls = "good" if diff >= 0 else ("warn" if diff > -0.03 else "bad")
    body = (f" Hiçbir şey yapmadan borsayı alıp bekleseydin {usd(abs(s_pnl))} "
            f"{'kazanacaktın' if s_pnl >= 0 else 'kaybedecektin'}; robotlar {usd(abs(r_pnl - s_pnl))} "
            f"{'daha iyi' if r_pnl >= s_pnl else 'daha kötü'}.")
    if days < 60:
        body += f" {sure} çok kısa; birkaç ay görmeden \"işe yarıyor\" demek için erken."
    return dict(lead=lead, ret=yuzde(ret), ret_cls=renk(ret), spy=yuzde(spy_ret), spy_cls=renk(spy_ret),
                verdict=f"<div class='verdict {cls}'><span class='light {cls}'></span><div><b>{head}</b>{body}</div></div>")


def hava(ctx):
    up200 = ctx["spy_close"] > ctx["spy_sma200"]
    vix = ctx["vix"]
    if vix >= 30:
        ico, h, p = "⛈️", "Fırtınalı", "Borsada panik havası var. İndirim Avcısı böyle günlerde hiç alım yapmaz."
    elif not up200:
        ico, h, p = "🌧️", "Yağmurlu", "Borsa uzun süredir düşüşte."
    elif ctx["trend_up"] and vix < 20:
        ico, h, p = "☀️", "Güneşli", "Borsa yükselişte."
    else:
        ico, h, p = "⛅", "Parçalı bulutlu", "Uzun vadede yön hâlâ yukarı, ama son haftalarda biraz geriledi." \
            if not ctx["trend_up"] else "Uzun vadede yön yukarı, ama ortalık biraz tedirgin."
    if vix < 30:
        p += " Ortalık sakin, panik yok." if vix < 20 else " Biraz tedirginlik var."
    lbl = "sakin" if vix < 20 else ("tedirgin" if vix < 30 else "panik")
    gap = ctx["spy_close"] / ctx["spy_sma200"] - 1
    return {
        "{{H_ICO}}": ico, "{{H_TITLE}}": h, "{{H_TEXT}}": p,
        "{{H_DIR}}": "Yukarı ☀️" if up200 else "Aşağı 🌧️", "{{H_DIR_CLS}}": "pos" if up200 else "neg",
        "{{H_DIR_TEXT}}": f"Borsa son 10 ayın ortalamasından %{abs(gap) * 100:.0f} {'yukarıda' if gap >= 0 else 'aşağıda'}.",
        "{{H_VIX}}": f"{vix:.0f} · {lbl}", "{{H_VIX_POS}}": f"{min(vix / 40, 1) * 100:.1f}",
    }


def robotlar(st, eq, cap, shares, health, acc):
    acc_by = {a["sleeve"]: a for a in acc}
    out = []
    for s in ORDER:
        r = ROBOT[s]
        v = eq[s].iloc[-1] if len(eq) else cap * shares[s]
        ret = v / (cap * shares[s]) - 1
        cl = [c for c in st.closed if c["sleeve"] == s]
        wins = sum(c["ret"] > 0 for c in cl)
        h = health.get(s, {})
        a = acc_by.get(s, {})
        exp_win, live_win = a.get("exp_win", np.nan), (wins / len(cl) if cl else np.nan)
        dd = (f"şu anki düşüşü {yuzde(abs(h['dd_now']), 0, False)}, geçmişte yaşadığı en kötü düşüş "
              f"{yuzde(abs(h['dd_hist']), 0, False)}") if h else ""
        note = ""
        if h.get("status") == "alarm":
            cls, lbl = "bad", "Alarm"
            note = f"Alarm: {dd}. Kural bozulmuş olabilir; geçmişte hiç bu kadar kötü gitmemişti."
        elif h.get("status") == "dikkat" or (len(cl) >= 8 and live_win < exp_win - 0.25):
            cls, lbl = "warn", "Gözümüz üstünde"
            note = (f"Kazanma oranı: geçmiş testlerde {yuzde(exp_win, 0, False)}, burada {yuzde(live_win, 0, False)}. "
                    if np.isfinite(live_win) else "")
            if dd:
                note += f"Henüz alarm değil: {dd}. Bu sınır aşılırsa alarm çalar ve burası kırmızı olur."
        elif len(cl) >= 3 and live_win >= exp_win:
            cls, lbl = "good", "İyi gidiyor"
        else:
            cls, lbl = "good", "Normal"

        if cl:
            dots = "".join(f"<i class='{'w' if c['ret'] > 0 else 'l'}'></i>" for c in cl[-40:])
            if wins == 0:
                res = "<b>hiçbirini kazanamadı</b>"
            else:
                res = f"<b>{'sadece ' if wins / len(cl) < 0.4 else ''}{wins}'{_ek(wins)} kazandı</b>"
            score = f"Biten {len(cl)} işin {res}<div class='dots'>{dots}</div>"
        else:
            score = "Henüz biten işi yok. "
        held = [ps for ps in st.positions if ps.sleeve == s]
        if s == "trend":
            hold = "Şu an borsayı elinde tutuyor." if held else "Şu an nakitte bekliyor."
        else:
            hold = f"Şu an elinde {len(held)} hisse var." if held else "Şu an elinde hisse yok, fırsat bekliyor."
        score += f"<span class='lbl'>{hold}</span>"
        out.append(f"""<div class="card robot">
  <div class="ava">{r['emoji']}</div>
  <div><div class="rhead"><h3>{r['name']}</h3><span class="status {cls}">{lbl}</span></div>
  <p class="rule">{r['rule']}</p></div>
  <div class="rstats"><div><span>Parası</span><b>{usd(v)}</b></div><div><span>Başlangıçtan beri</span><b class="{renk(ret)}">{yuzde(ret)}</b></div></div>
  <div class="score">{score}</div>
  {f'<div class="rnote {cls}">{note}</div>' if note else ''}
</div>""")
    return "\n".join(out)


def _ek(n):
    """Sayıdan sonra gelen iyelik eki: 5'ini, 2'sini, 3'ünü, 6'sını ..."""
    son = {0: "ını", 1: "ini", 2: "sini", 3: "ünü", 4: "ünü", 5: "ini", 6: "sını", 7: "sini", 8: "ini", 9: "unu"}
    onlar = {10: "unu", 20: "sini", 30: "unu", 40: "ını", 50: "sini", 60: "ını", 70: "ini", 80: "ini", 90: "ını"}
    if n % 10:
        return son[n % 10]
    if n % 100:
        return onlar[n % 100]
    return "ünü"


def emirler(pending, last_px):
    if not pending:
        return "<div class='empty'>Robotlar bir sonraki gün hiçbir şey yapmayacak; ellerindekileri tutmaya devam ediyorlar.</div>"
    rows = []
    for o in sorted(pending, key=lambda o: (o.side != "SAT", ORDER.index(o.sleeve))):
        r = ROBOT[o.sleeve]
        if o.sleeve == "trend":
            what = "borsadan çıkıp nakite geçecek." if o.side == "SAT" else "borsanın tamamını alacak."
            why = ("Borsa son 100 günün ortalamasının altına indi; robot bunu \"rüzgâr döndü\" sayıyor." if o.side == "SAT"
                   else "Borsa son 100 günün ortalamasının üstüne çıktı; rüzgâr arkadan esiyor.")
            line = f"{r['emoji']} {r['name']} {what}"
        else:
            line = f"{r['emoji']} {r['name']} {'satacak' if o.side == 'SAT' else 'alacak'}: {ad_sektor(o.ticker)}"
            if o.side == "AL" and o.sleeve == "pead":
                i = o.info
                why = (f"Karnesi beklenenden %{i['surprise']:.0f} iyi geldi, hisse o gün %{i['react'] * 100:.0f} yükseldi."
                       if i else "Karnesi beklenenden iyi geldi ve hisse o gün yükseldi.")
            elif o.side == "AL":
                why = "Son günlerde sert düştü, ama uzun vadede hâlâ yükselişte."
            else:
                ps = o.pos
                px = last_px.get(o.ticker, np.nan)
                pr = ps.shares * px / ps.cost_basis - 1 if ps is not None and np.isfinite(px) else np.nan
                durum = (f" Şu an <span class='{renk(pr)}'>{yuzde(pr)}</span> {'kârda' if pr >= 0 else 'zararda'}."
                         if np.isfinite(pr) else "")
                if "5 günlük" in o.reason:
                    why = "Toparlandı: fiyat son 5 günün ortalamasını geçti." + durum
                elif o.sleeve == "rsi2":
                    why = "10 günü doldu, toparlanmayı beklemeden çıkıyor." + durum
                else:
                    why = "10 günü doldu." + durum
        cls = "sell" if o.side == "SAT" else "buy"
        rows.append(f"<li><span class='act {cls}'>{o.side}</span><div><p>{line}</p><small>Neden? {why}</small></div></li>")
    return "<ul class='todo'>" + "".join(rows) + "</ul>"


def sonraki_acilis(asof):
    d = (asof + pd.offsets.BDay(1)).to_pydatetime()
    ny = datetime(d.year, d.month, d.day, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    tr = ny.astimezone(ZoneInfo("Europe/Istanbul"))
    return GUN[d.weekday()], tr.strftime("%H:%M")


def elindekiler(st, last_px):
    if not st.positions:
        return "<div class='empty'>Robotların elinde şu an hiçbir şey yok; para nakitte bekliyor.</div>"
    items = []
    for ps in st.positions:
        px = last_px.get(ps.ticker, np.nan)
        r = ps.shares * px / ps.cost_basis - 1 if np.isfinite(px) else np.nan
        items.append((r if np.isfinite(r) else -9, ps, r))
    out = []
    for _, ps, r in sorted(items, key=lambda x: -x[0]):
        sk = sektor(ps.ticker)
        out.append(f"<div class='hold'><b>{esc(ad(ps.ticker))} <span class='{renk(r)}'>{yuzde(r)}</span></b>"
                   f"<span>{esc(sk)}{' · ' if sk else ''}{ROBOT[ps.sleeve]['emoji']}</span></div>")
    return "<div class='holds'>" + "".join(out) + "</div>"


def ozet(eq, asof, up_e, brief_html):
    """'Bugün 3 cümlede': Claude'un sabah yazdığı özet tazeyse o, yoksa veriden üretilen 3 cümle."""
    m = re.search(r"(?is)<h3>\s*3 cümlede bugün\s*</h3>\s*<ul>(.*?)</ul>", brief_html or "")
    t = re.search(r"Hazırlanma:\s*(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})", brief_html or "")
    if m and t:
        dd, mm, yy, hh, mi = map(int, t.groups())
        when = datetime(yy, mm, dd, hh, mi)
        items = re.findall(r"(?is)<li>(.*?)</li>", m.group(1))[:3]
        if items and datetime.now() - when < timedelta(days=4):
            ps = "".join(f"<p><span class='n'>{k + 1}</span>{x.strip()}</p>" for k, x in enumerate(items))
            return ps + f"<div class='byline'>Claude yazdı · {tarih(when)} {when:%H:%M} · kaynaklar \"Detaylar\" bölümünde</div>"
    out = []
    if len(eq) >= 2:
        g = GUN[asof.weekday()]
        sr = eq["SPY"].iloc[-1] / eq["SPY"].iloc[-2] - 1
        rr = eq["toplam"].iloc[-1] / eq["toplam"].iloc[-2] - 1
        if abs(sr) < 0.002:
            out.append(f"{g} günü Amerikan borsası neredeyse hiç değişmedi.")
        else:
            out.append(f"{g} günü Amerikan borsası <b>{yuzde(abs(sr), 1, False)} {'yükseldi' if sr > 0 else 'düştü'}</b>.")
        fiil = "kazandı" if rr >= 0 else "kaybetti"
        if (rr < 0) == (sr < 0) and abs(sr) >= 0.002:
            kar = "daha az " if abs(rr) < abs(sr) else "daha çok "
            out.append(f"Robotlar aynı gün {kar}{fiil}: <b>{yuzde(abs(rr), 1, False)}</b>.")
        else:
            out.append(f"Robotlar aynı gün <b>{yuzde(abs(rr), 1, False)} {fiil}</b>.")
    names = []
    for t in up_e["ticker"].tolist() if len(up_e) else []:
        n = ad(t)
        if n not in names:
            names.append(n)
    if names:
        names = names[:3]
        lst = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ve " + names[-1]
        out.append(f"Önümüzdeki günlerde {esc(lst)} karnelerini açıklayacak. Karne Avcısı bunları bekliyor.")
    ps = "".join(f"<p><span class='n'>{k + 1}</span>{x}</p>" for k, x in enumerate(out))
    return ps + "<div class='byline'>Robotların verisinden otomatik yazıldı</div>"


def parts(st, eq, total, spy_v, cap, shares, ctx, pending, last_px, up_e, asof, health, acc, brief_html):
    global SIRKET
    SIRKET = sirketler()
    h = hero(eq, total, spy_v, cap)
    gun, saat = sonraki_acilis(asof)
    return {
        "{{B_ASOF}}": f"{tarih(asof)} kapanışı",
        "{{B_TOTAL}}": usd(total), "{{B_LEAD}}": h["lead"], "{{B_RET}}": h["ret"], "{{B_RET_CLS}}": h["ret_cls"],
        "{{B_SPY}}": h["spy"], "{{B_SPY_CLS}}": h["spy_cls"], "{{B_VERDICT}}": h["verdict"],
        "{{B_OZET}}": ozet(eq, asof, up_e, brief_html),
        **hava(ctx),
        "{{B_ROBOTS}}": robotlar(st, eq, cap, shares, health, acc),
        "{{B_NEXT_DAY}}": gun, "{{B_NEXT_TIME}}": saat,
        "{{B_ORDERS}}": emirler(pending, last_px),
        "{{B_HOLDS}}": elindekiler(st, last_px),
    }
