"""
쿠팡 수집 (GitHub Actions, 매시간)
- 골드박스 + watchlist.txt 키워드 검색 결과 중 3만원 이상
- data/coupang.json      : 이번 확인에서 잡힌 상품 (내 파트너스 링크·이미지 포함)
- data/products.json     : 지금까지 잡힌 모든 상품의 상태 (중복 없이 갱신)
- data/observations.csv  : 가격 관측 기록 (판매처·구성·가격·배송비·조건·확인 시각)
환경변수: COUPANG_ACCESS_KEY, COUPANG_SECRET_KEY
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

from common import BASE, MIN_PRICE, append_obs, config_of, load, now, save

HOST = "https://api-gateway.coupang.com"
API = "/v2/providers/affiliate_open_api/apis/openapi"
SUB_ID = "savercheck"


def auth(method, path, query, ak, sk):
    signed = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    sig = hmac.new(sk.encode(), (signed + method + path + query).encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={ak}, signed-date={signed}, signature={sig}"


def get(path, params):
    ak, sk = os.environ["COUPANG_ACCESS_KEY"], os.environ["COUPANG_SECRET_KEY"]
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{HOST}{path}?{query}", headers={
        "Authorization": auth("GET", path, query, ak, sk),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.loads(r.read().decode("utf-8"))
    if str(body.get("rCode")) != "0":
        raise RuntimeError(f"쿠팡 API 오류 {body.get('rCode')}: {body.get('rMessage')}")
    return body.get("data")


def normalize(it, source):
    return {
        "id": str(it.get("productId")),
        "name": (it.get("productName") or "").strip(),
        "price": int(it.get("productPrice") or 0),
        "rocket": bool(it.get("isRocket")),
        "free_ship": bool(it.get("isFreeShipping")),
        "category": it.get("categoryName") or "",
        "image": it.get("productImage") or "",
        "url": it.get("productUrl") or "",      # 쿠팡 파트너스 추적 링크 (내 수익 링크)
        "source": source,
    }


def main():
    items = {}
    for it in get(f"{API}/products/goldbox", {"subId": SUB_ID, "imageSize": "512x512"}) or []:
        p = normalize(it, "골드박스")
        items[p["id"]] = p

    wl = os.path.join(BASE, "watchlist.txt")
    if os.path.exists(wl):
        kws = [l.strip() for l in open(wl, encoding="utf-8") if l.strip() and not l.startswith("#")]
        for kw in kws[:10]:                       # 검색 API 호출 제한을 고려해 최대 10개
            try:
                data = get(f"{API}/products/search", {"keyword": kw, "limit": 5, "subId": SUB_ID})
                for it in (data or {}).get("productData", []):
                    p = normalize(it, f"관심:{kw}")
                    items.setdefault(p["id"], p)
            except Exception as e:
                print(f"  검색 실패 {kw}: {e}")
            time.sleep(1)

    items = {k: v for k, v in items.items() if v["price"] >= MIN_PRICE and v["url"]}
    ts = now().isoformat(timespec="minutes")

    # 상품 상태: 같은 상품은 새로 만들지 않고 갱신 (쿠팡 상품ID 기준)
    products = load("products.json", {})
    obs = []
    for p in items.values():
        old = products.get(p["id"], {})
        products[p["id"]] = {**old, **p,
                             "config": config_of(p["name"]),
                             "first_seen": old.get("first_seen", ts),
                             "last_seen": ts}
        # 관측 기록: 가격이 바뀌었거나 그날 첫 확인일 때만 한 줄 추가
        if old.get("last_price") != p["price"] or old.get("last_obs_day") != ts[:10]:
            obs.append({"checked_at": ts, "product_id": p["id"], "seller": "쿠팡",
                        "config": config_of(p["name"]), "price": p["price"],
                        "delivery": 0 if (p["rocket"] or p["free_ship"]) else "",
                        "total": p["price"], "condition": "일반",
                        "source": "쿠팡 파트너스 API"})
            products[p["id"]]["last_price"] = p["price"]
            products[p["id"]]["last_obs_day"] = ts[:10]
    append_obs(obs)
    save("products.json", products)
    save("coupang.json", {"collected_at": ts, "items": list(items.values())})
    print(f"쿠팡 {len(items)}개 확인, 기록 {len(obs)}줄 추가 ({ts})")


if __name__ == "__main__":
    main()
