"""
다나와 비교가 필요한 쿠팡 상품 목록을 출력 (Claude 예약 작업이 실행)
- 아직 비교 안 했거나, 비교한 지 COMPARE_TTL_HOURS 시간이 지난 상품
사용: python compare_todo.py  → todo.json 생성 + 요약 출력
"""
import json
from datetime import datetime

from common import COMPARE_TTL_HOURS, MAX_COMPARE_PER_RUN, load, now, search_keyword


def main():
    coupang = load("coupang.json", {"items": []})["items"]
    compare = load("compare.json", {})
    t = now()
    todo = []
    for p in coupang:
        c = compare.get(p["id"])
        if c:
            age = (t - datetime.fromisoformat(c["checked_at"])).total_seconds() / 3600
            if age < COMPARE_TTL_HOURS:
                continue
        todo.append({"id": p["id"], "name": p["name"], "coupang_price": p["price"],
                     "search_keyword": search_keyword(p["name"]),
                     # 관심 모델이면 다나와 상품번호가 정해져 있음 → 모델명으로 검색해 이 번호와 같은 결과만 사용
                     "danawa_pcode": p.get("danawa_pcode"), "model": p.get("model"),
                     "danawa_hint": (c or {}).get("danawa")})   # 지난번에 찾은 다나와 상품
    # 오래된 비교부터, 한 번에 최대 MAX_COMPARE_PER_RUN개
    todo.sort(key=lambda x: (compare.get(x["id"]) or {}).get("checked_at", ""))
    todo = todo[:MAX_COMPARE_PER_RUN]
    with open("todo.json", "w", encoding="utf-8") as f:
        json.dump(todo, f, ensure_ascii=False, indent=1)
    print(f"비교 필요: {len(todo)}개 / 전체 {len(coupang)}개 → todo.json")


if __name__ == "__main__":
    main()
