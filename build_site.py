"""
data/ → site/ 정적 사이트 생성 + 특가 상태(data/deals.json) 갱신
- 특가 조건: 쿠팡 가격이 같은 시점에 확인한 대형몰 최저가보다 쌈 (현재 비교몰 최저가)
- 배지: 관측 이래 최저가 / 최근 60일 최저가 / 평균보다 20% 저렴 / 현재 비교몰 최저가 / 기록 수집 중
- 같은 상품은 페이지 1개(p/쿠팡상품ID.html)를 계속 갱신
- 오래된 가격(쿠팡 3시간, 타몰 8시간 초과)은 특가 판정에서 제외
"""
import os
import shutil
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape as e

from common import BASE, KST, load, now, read_obs, save

OUT = os.path.join(BASE, "site")
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
NAME = "세이버체크"
COUPANG_STALE_H = 3
COMPARE_STALE_H = 8
MIN_DAYS_FOR_PERIOD = 14      # 기간 최저가 배지를 붙이기 위한 최소 기록 일수
DISCLOSURE = "이 사이트는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."

CSS = """
*{box-sizing:border-box}body{margin:0;background:#F4F5F1;color:#13221B;font-family:'Noto Sans KR',sans-serif}
a{color:#13221B}a:hover{color:#1F7A4D}.num{font-family:'JetBrains Mono',monospace;letter-spacing:-.02em}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px}
header{background:#13221B}header .wrap{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;padding-top:16px;padding-bottom:16px}
.logo{display:flex;align-items:center;gap:10px;text-decoration:none;color:#F4F5F1;font-weight:900;font-size:20px;letter-spacing:-.03em}
nav a{color:#C9D6CE;text-decoration:none;font-size:15px;padding:12px 10px;display:inline-block}nav a:hover{color:#fff}
.status{font-size:13px;color:#A9BDB2}
h1{font-size:clamp(28px,5vw,40px);font-weight:900;letter-spacing:-.04em;line-height:1.25;margin:0}
.eyebrow{font-size:14px;font-weight:700;color:#1F7A4D;margin:0 0 12px}
.note{font-size:13px;color:#5B6C62;line-height:1.7}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin:16px 0 40px}
.card{background:#fff;border:1px solid #DCE2DC;border-radius:14px;overflow:hidden;display:flex;flex-direction:column}
.card .img{display:block;aspect-ratio:1;background:#EEF1EC}.card .img img{width:100%;height:100%;object-fit:cover;display:block}
.card .body{padding:16px;display:flex;flex-direction:column;gap:10px;flex:1}
.card h3{margin:0;font-size:15px;line-height:1.45;font-weight:700}
.card h3 a{text-decoration:none}
.badges{display:flex;flex-wrap:wrap;gap:5px}
.badge{display:inline-block;font-size:12px;font-weight:700;border-radius:4px;padding:3px 7px;background:#EEF1EC;color:#3F5248}
.b-low{background:#13221B;color:#7FD1A3}.b-60{background:#E3F2E9;color:#17603C}.b-avg{background:#FFF3DD;color:#7A4A00}
.b-cmp{background:#1F7A4D;color:#fff}.b-wait{background:#EEF1EC;color:#5B6C62}.b-end{background:#FBE6DA;color:#9A3412}
.price{font-size:24px;font-weight:700}.price small{font-size:13px;font-family:'Noto Sans KR',sans-serif;font-weight:400}
.vs{font-size:13px;color:#3F5248}.save{color:#17603C;font-weight:700}
.btn{display:block;text-align:center;text-decoration:none;font-weight:700;font-size:15px;color:#fff;background:#13221B;border-radius:10px;padding:13px}
.btn:hover{color:#fff;background:#1F3A2D}.btn.ghost{background:transparent;color:#13221B;border:1px solid #13221B}
.fine{font-size:11px;color:#8A9A90;margin:0;text-align:center}
.bar{position:relative;height:8px;border-radius:4px;background:linear-gradient(90deg,#1F7A4D,#D9E3D6 50%,#E9B48F)}
.bar span{position:absolute;top:-4px;width:4px;height:16px;border-radius:2px;background:#13221B;box-shadow:0 0 0 2px #fff}
.barlab{display:flex;justify-content:space-between;font-size:11px;color:#5B6C62;margin-top:4px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #DCE2DC}
th,td{text-align:left;padding:11px 13px;border-bottom:1px solid #E4E8E3;font-size:14px;white-space:nowrap}
th{font-size:12px;color:#5B6C62;background:#F7F9F6}tr.me{background:#F1F8F3}
.detail{display:flex;flex-wrap:wrap;gap:28px;margin:24px 0}
.detail .pic{flex:0 1 360px;max-width:100%}.detail .pic img{width:100%;border-radius:14px;background:#EEF1EC}
.detail .info{flex:1 1 360px;min-width:0;display:flex;flex-direction:column;gap:14px}
.ended{opacity:.75}
footer{color:#8A9A90;font-size:12px;line-height:1.8;padding:28px 0 40px;margin-top:20px;border-top:1px solid #DCE2DC}
"""

LOGO = ('<svg width="28" height="28" viewBox="0 0 30 30" aria-hidden="true"><rect x="1" y="1" width="28" height="28" rx="7" '
        'fill="none" stroke="#7FD1A3" stroke-width="2"/><path d="M8 15.5l4.5 4.5L22 10" fill="none" stroke="#7FD1A3" '
        'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def won(n):
    return f"{int(n):,}"


def hm(iso):
    return datetime.fromisoformat(iso).strftime("%m.%d %H:%M") if iso else "-"


def page(title, desc, body, path, status, depth=0, img=""):
    up = "../" * depth
    canon = f'<link rel="canonical" href="{SITE_URL}/{path}">' if SITE_URL else ""
    ogimg = f'<meta property="og:image" content="{e(img)}">' if img else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">{canon}
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">{ogimg}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header><div class="wrap"><a class="logo" href="{up}index.html">{LOGO}{NAME}</a>
<span class="status">{e(status)}</span>
<nav aria-label="주 메뉴"><a href="{up}index.html">오늘의 쿠팡 최저가</a><a href="{up}ended.html">종료된 특가</a><a href="{up}index.html#method">검증 기준</a></nav></div></header>
<main class="wrap">{body}</main>
<footer><div class="wrap"><p style="margin:0">{DISCLOSURE}</p>
<p style="margin:0">가격·재고·할인·배송 조건은 판매처에 따라 달라질 수 있습니다. 다른 쇼핑몰 가격은 다나와 기준이며, 구매 전 최종 결제 금액을 확인해 주세요.</p>
<p style="margin:0">© {now().year} {NAME}</p></div></footer>
</body></html>"""


# ───────── 판정 ─────────
def daily_reps(obs):
    """상품별 쿠팡 일반가의 일별 대표가격(그날 최저)"""
    reps = defaultdict(dict)
    for o in obs:
        if o["seller"] != "쿠팡" or o["condition"] != "일반":
            continue
        d, pid, p = o["checked_at"][:10], o["product_id"], int(o["price"])
        reps[pid][d] = min(p, reps[pid].get(d, p))
    return reps


def badges_for(price, reps, today, cmp_win):
    """[(css, 라벨)], 기록 요약"""
    out = []
    days = sorted(reps)
    if cmp_win:
        out.append(("b-cmp", "현재 비교몰 최저가"))
    info = {"start": days[0] if days else today, "n_days": len(days)}
    if len(days) < MIN_DAYS_FOR_PERIOD:
        out.append(("b-wait", f"기록 수집 중 ({len(days)}일째)"))
        return out, info
    vals = [reps[d] for d in days]
    info.update(low=min(vals), high=max(vals))
    if price <= min(vals):
        out.append(("b-low", "관측 이래 최저가"))
    cut60 = (datetime.fromisoformat(today) - timedelta(days=59)).strftime("%Y-%m-%d")
    if days[0] <= cut60:                               # 60일 이상 기록이 있을 때만
        v60 = [reps[d] for d in days if d >= cut60]
        if price <= min(v60) and ("b-low", "관측 이래 최저가") not in out:
            out.append(("b-60", "최근 60일 최저가"))
    recent = [reps[d] for d in days if d >= cut60]
    avg = statistics.mean(recent)
    info["avg"] = round(avg)
    if price <= avg * 0.8:
        out.append(("b-avg", f"평균보다 {round((1 - price / avg) * 100)}% 저렴"))
    return out, info


def evaluate():
    t = now()
    today = t.strftime("%Y-%m-%d")
    cj = load("coupang.json", {"collected_at": None, "items": []})
    coupang_ok = bool(cj["collected_at"]) and (t - datetime.fromisoformat(cj["collected_at"])) < timedelta(hours=COUPANG_STALE_H)
    current = {p["id"]: p for p in cj["items"]} if coupang_ok else {}
    products = load("products.json", {})
    compare = load("compare.json", {})
    deals = load("deals.json", {})
    reps = daily_reps(read_obs())

    rows = {}
    for pid, p in products.items():
        cur = current.get(pid)
        c = compare.get(pid)
        cmp_ok = bool(c) and (t - datetime.fromisoformat(c["checked_at"])) < timedelta(hours=COMPARE_STALE_H)
        price = cur["price"] if cur else p.get("last_price")
        win = bool(cur and cmp_ok and c.get("other_min") and price < c["other_min"])
        bs, info = badges_for(price, reps.get(pid, {}), today, win)
        d = deals.get(pid, {})
        if win:
            if d.get("status") != "active":
                d = {"status": "active", "since": t.isoformat(timespec="minutes")}
        elif d.get("status") == "active":
            if not coupang_ok:
                reason = "가격 확인 지연"
            elif not cur:
                reason = "쿠팡 특가 종료 또는 품절"
            elif not cmp_ok:
                reason = "타몰 비교 만료"
            elif c and c.get("other_min") and price >= c["other_min"]:
                reason = f"가격 변동 ({c['other_min_shop']}가 같거나 더 쌈)"
            else:
                reason = "조건 미충족"
            d = {**d, "status": "ended", "ended": t.isoformat(timespec="minutes"), "reason": reason}
        deals[pid] = d
        rows[pid] = {**p, "price": price, "current": bool(cur), "compare": c if cmp_ok else None,
                     "compare_any": c, "badges": bs, "rec": info, "deal": d,
                     "reps": reps.get(pid, {})}
    save("deals.json", {k: v for k, v in deals.items() if v})
    return rows, cj, coupang_ok


# ───────── 화면 조각 ─────────
def badge_html(bs, ended=False):
    h = "".join(f'<span class="badge {c}">{e(l)}</span>' for c, l in bs)
    if ended:
        h = '<span class="badge b-end">특가 종료</span>' + h
    return f'<div class="badges">{h}</div>'


def bar_html(r):
    rec = r["rec"]
    if "low" not in rec or rec["high"] == rec["low"]:
        return ""
    pos = round((r["price"] - rec["low"]) / (rec["high"] - rec["low"]) * 100)
    pos = max(0, min(100, pos))
    return (f'<div><div class="bar" role="img" aria-label="기록 최저~최고 사이 {pos}% 위치"><span style="left:calc({pos}% - 2px)"></span></div>'
            f'<div class="barlab"><span>최저 {won(rec["low"])}</span><span>최고 {won(rec["high"])}</span></div></div>')


def buy(r, cls="btn"):
    return (f'<a class="{cls}" href="{e(r["url"])}" rel="sponsored nofollow noopener" target="_blank">쿠팡에서 보기</a>'
            f'<p class="fine">파트너스 활동으로 수수료를 받을 수 있어요</p>')


def card(r, depth=0):
    up = "../" * depth
    c = r["compare"] or r["compare_any"] or {}
    vs = ""
    if c.get("other_min"):
        diff = c["other_min"] - r["price"]
        vs = (f'<p class="vs" style="margin:0">{e(c["other_min_shop"])} {won(c["other_min"])}원 대비 '
              f'<span class="save">{won(diff)}원 저렴</span></p>' if diff > 0 else
              f'<p class="vs" style="margin:0">{e(c["other_min_shop"])} {won(c["other_min"])}원</p>')
    ended = r["deal"].get("status") == "ended"
    return f"""<article class="card{' ended' if ended else ''}">
<a class="img" href="{up}p/{r['id']}.html"><img src="{e(r['image'])}" alt="{e(r['name'])}" loading="lazy"></a>
<div class="body">{badge_html(r['badges'], ended)}
<h3><a href="{up}p/{r['id']}.html">{e(r['name'])}</a></h3>
{f'<p class="note" style="margin:0">구성 {e(r["config"])}</p>' if r.get('config') else ''}
<div class="price num">{won(r['price'])}<small>원 · 쿠팡</small></div>{vs}
{bar_html(r)}
<div style="margin-top:auto;display:flex;flex-direction:column;gap:6px">{buy(r)}</div></div></article>"""


def detail(r, status):
    c = r["compare_any"] or {}
    rows = (f"<tr class='me'><td><b>쿠팡</b></td><td class='num'>{won(r['price'])}</td>"
            f"<td>{'무료(로켓)' if r.get('rocket') else ('무료' if r.get('free_ship') else '판매처 확인')}</td>"
            f"<td>-</td><td>{'현재 확인' if r['current'] else '확인 안 됨'}</td></tr>")
    for m in c.get("malls", []):
        card_p = f"{won(m['card_price'])} ({e(m.get('card_name') or '카드')})" if m.get("card_price") else "-"
        mem = f" · 회원 {won(m['member_price'])}" if m.get("member_price") else ""
        rows += (f"<tr><td>{e(m['shop'])}</td><td class='num'>{won(m['price'])}</td>"
                 f"<td>{'무료' if not m['delivery'] else won(m['delivery'])}</td>"
                 f"<td class='num'>{card_p}{mem}</td><td>매칭 {e(m['match'])}</td></tr>")
    rec = r["rec"]
    rec_txt = (f"기록 시작 {rec['start']} · {rec['n_days']}일치"
               + (f" · 기간 최저 {won(rec['low'])}원 · 평균 {won(rec['avg'])}원" if "avg" in rec else " · 14일 이상 쌓이면 기간 최저가를 판정해요"))
    d = r["deal"]
    state = ""
    if d.get("status") == "active":
        state = f'<p class="save" style="margin:0">특가 진행 중 · {hm(d["since"])}부터</p>'
    elif d.get("status") == "ended":
        state = f'<p style="margin:0;color:#9A3412;font-weight:700">특가 종료 · {hm(d["ended"])} · {e(d.get("reason", ""))}</p>'
    body = f"""<p class="note" style="margin:20px 0 0"><a href="../index.html">오늘의 쿠팡 최저가</a> › 상품</p>
<section class="detail"><div class="pic"><img src="{e(r['image'])}" alt="{e(r['name'])}"></div>
<div class="info">{badge_html(r['badges'], d.get('status') == 'ended')}
<h1 style="font-size:26px">{e(r['name'])}</h1>
{f'<p class="note" style="margin:0">구성 {e(r["config"])}</p>' if r.get('config') else ''}
<div class="price num" style="font-size:32px">{won(r['price'])}<small>원 · 쿠팡 일반가</small></div>
{state}{bar_html(r)}
<p class="note" style="margin:0">{e(rec_txt)}</p>
<div style="max-width:360px">{buy(r)}</div></div></section>
<h2 style="font-size:20px;margin:8px 0 10px">판매처별 가격</h2>
<div style="overflow-x:auto"><table><thead><tr><th scope="col">판매처</th><th scope="col">일반가</th><th scope="col">배송비</th><th scope="col">카드·회원 전용가</th><th scope="col">비고</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">쿠팡 가격 확인 {hm(r.get('last_seen'))} · 다른 판매처 다나와 기준 {hm(c.get('checked_at'))} 조회. 카드·회원 전용가는 해당 카드나 회원만 적용돼서 최저가 판정에는 일반가만 써요. 같은 모델·구성으로 판단된 판매처만 표시해요.</p>"""
    desc = f"{r['name']} 쿠팡 {won(r['price'])}원" + (f", {c['other_min_shop']} {won(c['other_min'])}원과 비교" if c.get("other_min") else "")
    return page(f"{r['name']} 최저가 비교 | {NAME}", desc, body, f"p/{r['id']}.html", status, depth=1, img=r.get("image", ""))


def main():
    rows, cj, coupang_ok = evaluate()
    t = now()
    last_cmp = max((r["compare_any"]["checked_at"] for r in rows.values() if r["compare_any"]), default=None)
    status = f"쿠팡 {hm(cj['collected_at'])} · 다른 몰 {hm(last_cmp)} 확인"
    if not coupang_ok:
        status = f"⚠ 가격 확인 지연 · 마지막 {hm(cj['collected_at'])}"

    active = [r for r in rows.values() if r["deal"].get("status") == "active"]
    active.sort(key=lambda r: -((r["compare"]["other_min"] - r["price"]) / r["compare"]["other_min"]))
    ended = [r for r in rows.values() if r["deal"].get("status") == "ended"]
    ended.sort(key=lambda r: r["deal"]["ended"], reverse=True)
    pending = [r for r in rows.values() if r["current"] and not r["compare"]]

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "p"))
    w = lambda rel, s: open(os.path.join(OUT, rel), "w", encoding="utf-8").write(s)

    empty = ('<p class="note" style="background:#fff;border:1px dashed #C4CEC6;border-radius:12px;padding:28px;text-align:center">'
             '지금은 쿠팡이 다른 대형몰보다 싼 상품이 없어요. 다음 확인 때 다시 업데이트돼요.</p>')
    body = f"""<section style="padding:36px 0 4px"><p class="eyebrow">쿠팡 특가 × 대형몰 가격 비교 · 매시간 갱신</p>
<h1>지금 쿠팡이 제일 싼 상품 {len(active)}개</h1>
<p class="note" style="font-size:15px;margin:10px 0 0">쿠팡 가격을 같은 시점의 11번가·G마켓·SSG·롯데ON·하이마트 등 대형몰 일반가와 비교해, 쿠팡이 더 싼 상품만 모았어요.{f' 비교 대기 {len(pending)}개.' if pending else ''}</p></section>
{('<div class="grid">' + ''.join(card(r) for r in active) + '</div>') if active else empty}
<section id="method" style="background:#E8ECE6;border-radius:16px;padding:24px;margin:8px 0 20px">
<h2 style="margin:0 0 10px;font-size:20px">배지 기준</h2>
<p class="note" style="margin:0;font-size:14px"><b>현재 비교몰 최저가</b> 같은 시점에 확인한 대형몰 일반가보다 쌈 · <b>관측 이래 최저가</b> 기록 전체의 최저가 이하 · <b>최근 60일 최저가</b> 60일 이상 기록 중 최근 60일 최저가 이하 · <b>평균보다 20% 저렴</b> 일별 대표가격 평균 대비 · <b>기록 수집 중</b> 기록이 {MIN_DAYS_FOR_PERIOD}일 미만이라 기간 판정 보류. 카드·회원 전용가는 따로 표시하고 판정에는 쓰지 않아요.</p></section>"""
    first = active[0] if active else None
    w("index.html", page(f"{NAME} — 지금 쿠팡이 제일 싼 상품", f"쿠팡이 다른 대형몰보다 싼 상품 {len(active)}개 · {status}",
                         body, "index.html", status, img=first["image"] if first else ""))
    ebody = (f'<section style="padding:36px 0 4px"><h1>종료된 특가</h1><p class="note">가격이 오르거나 쿠팡 특가가 끝난 상품이에요.</p></section>'
             + ('<div class="grid">' + "".join(card(r) for r in ended[:60]) + "</div>" if ended else '<p class="note">아직 없어요.</p>'))
    w("ended.html", page(f"종료된 특가 | {NAME}", "최근 종료된 쿠팡 최저가 특가", ebody, "ended.html", status))
    pages = [r for r in rows.values() if r["deal"]]
    for r in pages:
        w(f"p/{r['id']}.html", detail(r, status))
    if SITE_URL:
        urls = ["index.html", "ended.html"] + [f"p/{r['id']}.html" for r in pages]
        w("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{SITE_URL}/{u}</loc></url>" for u in urls) + "</urlset>")
        w("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"사이트: 특가 {len(active)} · 종료 {len(ended)} · 상품 페이지 {len(pages)} · 비교 대기 {len(pending)}")


if __name__ == "__main__":
    main()
