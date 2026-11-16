# 다른 몰 가격 비교 작업 (Claude 예약 작업용)

하루 5번(08·11·14·17·20시 무렵) 실행. 쿠팡 상품을 다나와로 대형몰 가격과 비교해 `data/compare.json`에 올린다.

1. 저장소 최신화: `git pull`
2. `python compare_todo.py` → `todo.json` (비교가 필요한 상품만. 0개면 여기서 끝)
3. `todo.json`의 상품마다:
   - `danawa_hint`가 있으면 그 `pcode`·`cate`로 바로 `get_mall_price_list`
   - 없으면 다나와 `search_products`(query·search_keyword = `search_keyword`, limit 5)로 찾는다.
     쿠팡 상품명과 **브랜드·모델명·용량·수량이 같은 것**만 고른다. 확신이 없으면 `danawa: null`, `malls: []`.
   - 고른 상품의 `product_ref`·카테고리로 `get_mall_price_list` 호출
   - 응답 `company` 목록을 그대로 옮긴다 (판단·필터는 compare_save.py가 함):
     shop=shop_name, price=price, delivery=delivery_price, card_price=promotion_price,
     card_name=promotion_name, member_price=member_price, product_name=link_product_name
4. 결과를 `results.json`에 저장 (형식은 compare_save.py 상단 주석)
5. `python compare_save.py results.json`
6. `python build_site.py` 로 오류 없는지 확인 (site/ 폴더는 커밋하지 않음)
7. `git add data/compare.json data/observations.csv && git commit -m "다른 몰 비교 $(date)" && git push`
   → GitHub Actions가 사이트를 자동 갱신

규칙
- 가격·상품명은 다나와 응답 값만 쓴다. 추정하거나 지어내지 않는다.
- 상품이 많으면 다나와 호출은 상품당 최대 2번. 시간이 부족하면 처리한 만큼만 저장하고 push.
- 실패한 상품은 results에서 빼면 다음 회차에 다시 시도된다.
