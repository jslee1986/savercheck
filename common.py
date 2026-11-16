"""공통: 경로, 시간, 상품 매칭, 비교 대상 몰 목록"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
KST = timezone(timedelta(hours=9))
MIN_PRICE = 30000                 # 3만원 미만 제외
COMPARE_TTL_HOURS = 5             # 비교 결과를 다시 확인하는 주기
COUPANG_VALID_H = 3              # 골드박스 가격 유효 시간
WATCH_VALID_H = 12               # 관심 모델 가격 유효 시간 (5개씩 순환 확인)
MAX_COMPARE_PER_RUN = 25         # 한 번에 비교할 최대 상품 수
OUTLIER_RATIO = 0.85              # 다른 대형몰 중간값의 85% 미만이면 가격 오류 의심

# 비교에 인정하는 대형몰 (다나와 shop_name 기준, 부분 일치)
MAJOR_MALLS = [
    "11번가", "G마켓", "지마켓", "옥션", "SSG", "이마트몰", "신세계몰", "신세계백화점",
    "롯데ON", "롯데온", "롯데백화점", "롯데홈쇼핑", "롯데하이마트", "하이마트",
    "현대Hmall", "Hmall", "더현대", "현대백화점", "GS SHOP", "GS샵", "CJ온스타일", "CJmall",
    "홈&쇼핑", "홈앤쇼핑", "공영쇼핑", "신세계라이브쇼핑", "NS몰", "NS홈쇼핑", "갤러리아", "AK몰",
    "전자랜드", "삼성닷컴", "삼성전자", "LG전자", "오늘의집", "컬리", "올리브영", "무신사", "29CM",
]


def now():
    return datetime.now(KST)


def load(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def is_major(shop_name):
    s = (shop_name or "").replace(" ", "").lower()
    return any(m.replace(" ", "").lower() in s for m in MAJOR_MALLS)


# ───────── 같은 상품인지 판정 ─────────
UNIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|l|g|kg|매|개입|개|입|팩|병|롤|정|포|캔|봉|hz|w|인치|만화소|mah|gb|tb)(?![a-z])", re.I)
MODEL_RE = re.compile(r"\b([A-Z]{1,5}-?\d{2,}[A-Z0-9/-]*)\b")
NOISE_RE = re.compile(r"\[.*?\]|\(.*?\)|[^\w\s./-]")


def tokens(name):
    s = NOISE_RE.sub(" ", name.lower())
    return {t for t in s.split() if len(t) > 1}


def specs(name):
    return sorted({(float(n), u.lower()) for n, u in UNIT_RE.findall(name)})


def models(name):
    return {m.replace("-", "").split("/")[0] for m in MODEL_RE.findall(name.upper())}


COLORS = ["골드", "니켈", "옐로우", "블랙", "화이트", "실버", "그레이", "블루", "레드", "핑크", "퍼플",
          "그린", "베이지", "네이비", "브라운", "아이보리", "민트", "코퍼", "브론즈", "라벤더", "차콜"]
YEAR_RE = re.compile(r"(20\d\d)\s*년?\s*(?:\d{1,2}\s*월)?\s*(?:신형|신제품|출시)")


def colors(name):
    return {c for c in COLORS if c in name}


def match_confidence(a, b):
    """('높음'|'보통'|'낮음', 점수)"""
    ta, tb = tokens(a), tokens(b)
    jac = len(ta & tb) / max(1, len(ta | tb))
    ca, cb = colors(a), colors(b)
    if ca and cb and not (ca & cb):            # 색상이 서로 다르면 다른 상품
        return "낮음", 0.1
    ya, yb = YEAR_RE.findall(a), YEAR_RE.findall(b)
    if ya != yb and (ya or yb):                # 한쪽만 '2026년 신형' 등 → 다른 버전
        return "낮음", 0.1
    ma, mb = models(a), models(b)
    sa, sb = specs(a), specs(b)
    if ma and mb:
        return ("높음", 0.95) if ma & mb else ("낮음", 0.1)
    if sa and sb and sa != sb:
        return "낮음", 0.15
    if sa and sa == sb and jac >= 0.3:
        return "높음", min(1.0, round(0.6 + jac / 2, 2))
    if jac >= 0.5:
        return "보통", round(jac, 2)
    return "낮음", round(jac, 2)


def config_of(name):
    """상품 구성 문자열: '2L · 24병' 처럼 상품명에서 용량·수량만 뽑음"""
    out = []
    for n, u in UNIT_RE.findall(name):
        s = f"{n}{u}"
        if s not in out:
            out.append(s)
    return " · ".join(out)


# ───────── 가격 관측 기록 ─────────
OBS_FIELDS = ["checked_at", "product_id", "seller", "config", "price", "delivery", "total",
              "card_price", "member_price", "condition", "source"]


def append_obs(rows):
    import csv
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, "observations.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OBS_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in OBS_FIELDS})


def read_obs():
    import csv
    path = os.path.join(DATA, "observations.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def search_keyword(name):
    s = NOISE_RE.sub(" ", name)
    return " ".join(s.split()[:6])
