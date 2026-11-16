"""
Claude가 다나와로 조회한 결과(results.json)를 검증해서 data/compare.json에 반영
results.json 형식 (상품마다 1개):
[
  {"id": "쿠팡 상품ID",
   "danawa": {"pcode": "71504639", "name": "필립스 NA230/00", "cate": [1, 28320, 221512, 0]},   # 못 찾으면 null
   "malls": [{"shop": "11번가", "price": 121250, "delivery": 0,
              "card_price": 0, "card_name": "", "member_price": 0,
              "product_name": "[하이마트] 필립스 2000시리즈 에어프라이어 6.2L NA-230"}, ...]}
   다나와 get_mall_price_list 응답 대응: shop=shop_name, price=price, delivery=delivery_price,
   card_price=promotion_price, card_name=promotion_name, member_price=member_price, product_name=link_product_name
]
검증:
- 대형몰(MAJOR_MALLS)만 인정
- 몰 상품명과 쿠팡 상품명의 매칭이 '낮음'이면 그 몰 가격 제외
- 다른 대형몰 중간값의 85% 미만인 가격은 오류 의심으로 제외
"""
import json
import statistics
import sys
from datetime import timedelta

from common import OUTLIER_RATIO, append_obs, config_of, is_major, load, match_confidence, now, save


def judge(coupang_name, malls):
    kept, dropped = [], []
    for m in malls:
        total = int(m.get("price") or 0) + int(m.get("delivery") or 0)
        if total <= 0:
            continue
        if not is_major(m.get("shop")):
            dropped.append({**m, "why": "소형몰"})
            continue
        level, score = match_confidence(coupang_name, m.get("product_name") or "")
        if level == "낮음":
            dropped.append({**m, "why": "다른 상품 의심"})
            continue
        kept.append({"shop": m["shop"], "price": int(m["price"]), "delivery": int(m.get("delivery") or 0),
                     "total": total, "card_price": int(m.get("card_price") or 0) or None,
                     "card_name": m.get("card_name") or "",
                     "member_price": int(m.get("member_price") or 0) or None,
                     "product_name": m.get("product_name") or "", "match": level})
    # 가격 오류 의심 제거
    if len(kept) >= 3:
        med = statistics.median(k["total"] for k in kept)
        sus = [k for k in kept if k["total"] < med * OUTLIER_RATIO]
        kept = [k for k in kept if k not in sus]
        dropped += [{**s, "why": "가격 오류 의심"} for s in sus]
    kept.sort(key=lambda k: k["total"])
    return kept, dropped


def main(path):
    with open(path, encoding="utf-8") as f:
        results = json.load(f)
    coupang = {p["id"]: p for p in load("coupang.json", {"items": []})["items"]}
    compare = load("compare.json", {})
    ts = now().isoformat(timespec="minutes")
    n_win = 0
    obs = []
    for r in results:
        p = coupang.get(r["id"])
        if not p:
            continue
        kept, dropped = judge(p["name"], r.get("malls") or [])
        cfg = config_of(p["name"])
        for k in kept:      # 관측 기록: 판매처별 일반가 1줄 + 카드가·회원가가 있으면 별도 줄
            base = {"checked_at": ts, "product_id": r["id"], "seller": k["shop"], "config": cfg,
                    "delivery": k["delivery"], "source": "다나와"}
            obs.append({**base, "price": k["price"], "total": k["total"], "condition": "일반"})
            if k["card_price"]:
                obs.append({**base, "price": k["card_price"], "total": k["card_price"] + k["delivery"],
                            "card_price": k["card_price"], "condition": f"카드 {k['card_name']}".strip()})
            if k["member_price"]:
                obs.append({**base, "price": k["member_price"], "total": k["member_price"] + k["delivery"],
                            "member_price": k["member_price"], "condition": "회원"})
        best = kept[0] if kept else None
        win = bool(best) and p["price"] < best["total"]
        n_win += win
        compare[r["id"]] = {
            "checked_at": ts,
            "coupang_price_at_check": p["price"],
            "danawa": r.get("danawa"),
            "malls": kept[:8],
            "dropped": len(dropped),
            "other_min": best["total"] if best else None,
            "other_min_shop": best["shop"] if best else None,
        }
    # 쿠팡 목록에서 빠진 지 7일 넘은 비교 결과 정리
    append_obs(obs)
    cutoff = (now() - timedelta(days=7)).isoformat(timespec="minutes")
    save("compare.json", {k: v for k, v in compare.items() if k in coupang or v["checked_at"] >= cutoff})
    print(f"비교 저장 {len(results)}개, 쿠팡 최저 {n_win}개")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "results.json")
