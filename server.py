"""
Korean Agriculture MCP Server
한국 농산물 도매시장 경매 데이터 MCP 서버

Data Source: data.go.kr - 한국농수산식품유통공사 전국 공영도매시장 실시간 경매정보
API: https://apis.data.go.kr/B552845/katRealTime2/trades2
"""

import os
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

DATA_GO_KR_KEY = os.getenv("DATA_GO_KR_API_KEY", "")

mcp = FastMCP("Korean Agriculture Market")

# ─── 전국 도매시장 코드 ───

MARKETS = {
    "110001": "서울가락", "110008": "서울강서",
    "310101": "수원", "310401": "안양", "310901": "안산", "311201": "구리",
    "230001": "인천남촌", "230003": "인천삼산",
    "360301": "순천",
    "240001": "광주각화", "240004": "광주서부",
    "350402": "정읍", "350301": "익산", "350101": "전주",
    "250001": "대전오정", "250003": "대전노은",
    "330101": "청주", "340101": "천안", "330201": "충주",
    "370401": "안동", "371501": "구미",
    "220001": "대구북부",
    "380401": "진주", "380101": "창원팔용", "380303": "창원내서",
    "210001": "부산엄궁", "210009": "부산반여",
    "380201": "울산", "370101": "포항",
    "320201": "원주", "320101": "춘천", "320301": "강릉",
    "210005": "부산국제수산",
}

# 부류(대분류) 코드
CATEGORIES = {
    "06": "과실류", "08": "과일과채류", "09": "과채류",
    "10": "엽경채류", "11": "근채류", "12": "조미채소류",
    "13": "양채류", "14": "산채류", "17": "버섯류",
    "05": "서류", "03": "두류", "02": "맥류",
    "07": "수실류", "16": "특용작물류", "18": "인삼류",
    "19": "약용작물류", "26": "관엽식물류",
    "43": "국내산육류", "76": "신선 해조류",
    "89": "건제품", "91": "농림가공", "93": "수산가공",
}

# ─── 캐싱 ───

CACHE_TTL = {
    "realtime": 120,      # 실시간: 2분
    "daily": 3600,        # 일별: 1시간
    "market_list": 86400, # 시장 목록: 24시간
}

_cache: dict[str, tuple[float, str]] = {}


def _cache_get(key: str) -> str | None:
    if key in _cache:
        expires, value = _cache[key]
        if time.time() < expires:
            return value
        del _cache[key]
    return None


def _cache_set(key: str, value: str, ttl_key: str):
    ttl = CACHE_TTL.get(ttl_key, 600)
    _cache[key] = (time.time() + ttl, value)


# ─── data.go.kr API 클라이언트 ───

API_BASE = "https://apis.data.go.kr/B552845/katRealTime2/trades2"


async def _fetch_auction(params: dict) -> dict:
    """data.go.kr 실시간 경매 API 호출"""
    if not DATA_GO_KR_KEY:
        return {"error": "DATA_GO_KR_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."}

    query = {
        "serviceKey": DATA_GO_KR_KEY,
        "returnType": "json",
        "pageNo": str(params.get("pageNo", 1)),
        "numOfRows": str(params.get("numOfRows", 100)),
    }

    # 조건 파라미터 추가
    if params.get("date"):
        query["cond[trd_clcln_ymd::EQ]"] = params["date"]
    if params.get("market_code"):
        query["cond[whsl_mrkt_cd::EQ]"] = params["market_code"]
    if params.get("corp_code"):
        query["cond[corp_cd::EQ]"] = params["corp_code"]
    if params.get("large_code"):
        query["cond[gds_lclsf_cd::EQ]"] = params["large_code"]
    if params.get("mid_code"):
        query["cond[gds_mclsf_cd::EQ]"] = params["mid_code"]
    if params.get("small_code"):
        query["cond[gds_sclsf_cd::EQ]"] = params["small_code"]
    if params.get("auction_date"):
        query["cond[scsbd_dt::LIKE]"] = params["auction_date"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_BASE, params=query)
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}"}
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _format_item(item: dict) -> dict:
    """API 응답 아이템을 읽기 쉬운 형태로 변환"""
    price = float(item.get("scsbd_prc", 0))
    qty = float(item.get("qty", 0))
    unit_qty = float(item.get("unit_qty", 0))
    return {
        "경매시간": item.get("scsbd_dt", ""),
        "정산일": item.get("trd_clcln_ymd", ""),
        "시장": item.get("whsl_mrkt_nm", ""),
        "시장코드": item.get("whsl_mrkt_cd", ""),
        "법인": item.get("corp_nm", ""),
        "거래구분": item.get("trd_se", ""),
        "대분류": item.get("gds_lclsf_nm", ""),
        "품목": item.get("gds_mclsf_nm", ""),
        "품종": item.get("gds_sclsf_nm", ""),
        "단가(원)": int(price),
        "수량": int(qty) if qty == int(qty) else qty,
        "단위": item.get("unit_nm", ""),
        "단위중량": unit_qty,
        "포장": item.get("pkg_nm", ""),
        "산지": item.get("plor_nm", "").strip(),
    }


def _format_results(items: list[dict], header: str) -> str:
    """결과 목록을 문자열로 포맷팅"""
    if not items:
        return "조회 결과가 없습니다."

    lines = [header]
    for r in items:
        line = (f"  {r['경매시간']} | {r['시장']} {r['법인']} | "
                f"{r['품목']} {r['품종']} | "
                f"{r['단가(원)']:,}원/{r['단위중량']}{r['단위']} | "
                f"{r['수량']}건 | {r['포장']} | {r['산지']}")
        lines.append(line)

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 1: 실시간 경매 현황 조회
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_realtime_auction(
    market_code: str = "",
    category_code: str = "",
    date: str = "",
    num_results: int = 50,
) -> str:
    """전국 도매시장 실시간 경매 현황을 조회합니다.
    63,000건+ 전국 경매 데이터를 실시간으로 제공합니다.

    Args:
        market_code: 도매시장 코드 (예: "250003"=대전노은, "110001"=서울가락, "220001"=대구북부). 빈 문자열이면 전국.
        category_code: 대분류 코드 (예: "06"=과실류, "10"=엽경채류, "12"=조미채소류). 빈 문자열이면 전체.
        date: 정산일 (YYYY-MM-DD). 빈 문자열이면 오늘.
        num_results: 조회 건수 (기본 50, 최대 1000)

    Returns:
        실시간 경매 데이터 (품목, 가격, 수량, 규격, 시장, 법인, 산지 정보)
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    num_results = min(num_results, 1000)

    cache_key = f"realtime:{market_code}:{category_code}:{date}:{num_results}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {
        "date": date,
        "numOfRows": num_results,
    }
    if market_code:
        params["market_code"] = market_code
    if category_code:
        params["large_code"] = category_code

    data = await _fetch_auction(params)
    if "error" in data:
        return f"API 오류: {data['error']}"

    body = data.get("response", {}).get("body", {})
    total = body.get("totalCount", 0)
    items_raw = body.get("items", {}).get("item", [])

    if not items_raw:
        return f"{date} 경매 데이터가 없습니다. 경매 시간(새벽~오전)이 아니거나 해당 조건의 데이터가 없을 수 있습니다."

    if isinstance(items_raw, dict):
        items_raw = [items_raw]

    formatted = [_format_item(item) for item in items_raw]

    market_name = MARKETS.get(market_code, "전국") if market_code else "전국"
    cat_name = CATEGORIES.get(category_code, "전체") if category_code else "전체"
    header = f"[실시간 경매 현황] {date} / {market_name} / {cat_name} (조회 {len(formatted)}건 / 전체 {total:,}건)\n"

    result = _format_results(formatted, header)
    _cache_set(cache_key, result, "realtime")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 2: 품목별 가격 검색
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def search_product_price(
    product_keyword: str,
    market_code: str = "",
    date: str = "",
    num_results: int = 100,
) -> str:
    """품목 키워드로 전국 도매시장 경매 가격을 검색합니다.

    Args:
        product_keyword: 품목 키워드 (예: "사과", "딸기", "배추", "고추", "포도")
        market_code: 도매시장 코드 (빈 문자열이면 전국 검색)
        date: 정산일 (YYYY-MM-DD). 빈 문자열이면 오늘.
        num_results: 조회 건수 (기본 100, 최대 1000)

    Returns:
        품목별 가격 정보 + 시장별 평균/최고/최저가 요약
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    num_results = min(num_results, 1000)

    cache_key = f"search:{product_keyword}:{market_code}:{date}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # 넉넉하게 가져와서 키워드 필터
    params = {
        "date": date,
        "numOfRows": num_results,
    }
    if market_code:
        params["market_code"] = market_code

    data = await _fetch_auction(params)
    if "error" in data:
        return f"API 오류: {data['error']}"

    items_raw = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    if isinstance(items_raw, dict):
        items_raw = [items_raw]

    # 키워드 필터링
    matched = [
        item for item in items_raw
        if (product_keyword in item.get("gds_mclsf_nm", "")
            or product_keyword in item.get("gds_sclsf_nm", "")
            or product_keyword in item.get("gds_lclsf_nm", "")
            or product_keyword in item.get("corp_gds_item_nm", "")
            or product_keyword in item.get("corp_gds_vrty_nm", ""))
    ]

    if not matched:
        return (f"'{product_keyword}' 검색 결과가 없습니다. "
                f"다른 키워드를 시도하거나, 전체 경매 현황(get_realtime_auction)을 먼저 확인해보세요.")

    formatted = [_format_item(item) for item in matched]

    # 시장별 요약 통계
    market_stats: dict[str, list[int]] = {}
    for r in formatted:
        mkt = r["시장"]
        if mkt not in market_stats:
            market_stats[mkt] = []
        if r["단가(원)"] > 0:
            market_stats[mkt].append(r["단가(원)"])

    header = f"[품목 검색] '{product_keyword}' / {date} (총 {len(formatted)}건)\n"
    lines = [header]

    # 시장별 요약
    if market_stats:
        lines.append("  [시장별 요약]")
        for mkt, prices in sorted(market_stats.items()):
            if prices:
                avg = sum(prices) // len(prices)
                lines.append(
                    f"    {mkt}: 평균 {avg:,}원 "
                    f"(최저 {min(prices):,} ~ 최고 {max(prices):,}) "
                    f"| {len(prices)}건"
                )
        lines.append("")

    # 상세 데이터
    lines.append("  [상세 경매 데이터]")
    for r in formatted[:30]:
        line = (f"    {r['경매시간']} | {r['시장']} {r['법인']} | "
                f"{r['품목']} {r['품종']} | "
                f"{r['단가(원)']:,}원/{r['단위중량']}{r['단위']} | "
                f"{r['수량']}건 | {r['포장']} | {r['산지']}")
        lines.append(line)

    result = "\n".join(lines)
    _cache_set(cache_key, result, "realtime")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 3: 시장별 가격 비교
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def compare_market_prices(
    product_keyword: str,
    date: str = "",
) -> str:
    """특정 품목의 전국 도매시장 가격을 비교합니다.

    Args:
        product_keyword: 품목 키워드 (예: "사과", "딸기", "배추")
        date: 정산일 (YYYY-MM-DD). 빈 문자열이면 오늘.

    Returns:
        전국 시장별 가격 비교 (평균가, 최고가, 최저가, 거래량)
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"compare:{product_keyword}:{date}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # 전국 데이터를 최대한 가져옴
    params = {"date": date, "numOfRows": 1000}
    data = await _fetch_auction(params)
    if "error" in data:
        return f"API 오류: {data['error']}"

    items_raw = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    if isinstance(items_raw, dict):
        items_raw = [items_raw]

    # 키워드 필터
    matched = [
        item for item in items_raw
        if (product_keyword in item.get("gds_mclsf_nm", "")
            or product_keyword in item.get("gds_sclsf_nm", "")
            or product_keyword in item.get("corp_gds_item_nm", ""))
    ]

    if not matched:
        return f"'{product_keyword}' 비교 데이터가 없습니다."

    # 시장별 통계
    market_data: dict[str, dict] = {}
    for item in matched:
        mkt_name = item.get("whsl_mrkt_nm", "")
        price = float(item.get("scsbd_prc", 0))
        qty = float(item.get("qty", 0))
        if not mkt_name or price <= 0:
            continue

        if mkt_name not in market_data:
            market_data[mkt_name] = {
                "prices": [], "total_qty": 0,
                "varieties": set(), "origins": set()
            }
        market_data[mkt_name]["prices"].append(price)
        market_data[mkt_name]["total_qty"] += qty
        variety = item.get("gds_sclsf_nm", "")
        if variety:
            market_data[mkt_name]["varieties"].add(variety)
        origin = item.get("plor_nm", "").strip()
        if origin:
            market_data[mkt_name]["origins"].add(origin)

    if not market_data:
        return f"'{product_keyword}' 가격 데이터가 부족합니다."

    # 평균가 기준 정렬
    sorted_markets = sorted(
        market_data.items(),
        key=lambda x: sum(x[1]["prices"]) / len(x[1]["prices"])
    )

    lines = [f"[시장별 가격 비교] '{product_keyword}' / {date} ({len(sorted_markets)}개 시장)\n"]

    for mkt_name, info in sorted_markets:
        prices = info["prices"]
        avg = int(sum(prices) / len(prices))
        varieties = ", ".join(list(info["varieties"])[:3])
        origins = ", ".join(list(info["origins"])[:3])
        lines.append(
            f"  {mkt_name}: 평균 {avg:,}원 "
            f"(최저 {int(min(prices)):,} ~ 최고 {int(max(prices)):,}) "
            f"| {len(prices)}건 | 총수량 {int(info['total_qty'])}"
        )
        if varieties:
            lines.append(f"    품종: {varieties}")
        if origins:
            lines.append(f"    산지: {origins}")

    if len(sorted_markets) >= 2:
        cheapest = sorted_markets[0]
        expensive = sorted_markets[-1]
        cheap_avg = int(sum(cheapest[1]["prices"]) / len(cheapest[1]["prices"]))
        exp_avg = int(sum(expensive[1]["prices"]) / len(expensive[1]["prices"]))
        diff = exp_avg - cheap_avg

        lines.append(f"\n  -- 요약 --")
        lines.append(f"  가장 저렴: {cheapest[0]} (평균 {cheap_avg:,}원)")
        lines.append(f"  가장 비쌈: {expensive[0]} (평균 {exp_avg:,}원)")
        if cheap_avg > 0:
            lines.append(f"  시장 간 차이: {diff:,}원 ({diff/cheap_avg*100:.1f}%)")

    result = "\n".join(lines)
    _cache_set(cache_key, result, "realtime")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 4: 일별 가격 추이
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_price_trend(
    product_keyword: str,
    market_code: str = "",
    days: int = 7,
) -> str:
    """품목의 최근 N일간 가격 추이를 조회합니다.

    Args:
        product_keyword: 품목 키워드 (예: "사과", "딸기")
        market_code: 도매시장 코드 (빈 문자열이면 전국)
        days: 조회 기간 (기본 7일, 최대 30일)

    Returns:
        일별 평균가격 추이
    """
    days = min(days, 30)
    today = datetime.now()

    cache_key = f"trend:{product_keyword}:{market_code}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    daily_stats = []

    for i in range(days):
        target_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        params = {
            "date": target_date,
            "numOfRows": 500,
        }
        if market_code:
            params["market_code"] = market_code

        data = await _fetch_auction(params)
        if "error" in data:
            continue

        items_raw = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items_raw, dict):
            items_raw = [items_raw]

        matched = [
            item for item in items_raw
            if (product_keyword in item.get("gds_mclsf_nm", "")
                or product_keyword in item.get("gds_sclsf_nm", "")
                or product_keyword in item.get("corp_gds_item_nm", ""))
        ]

        if matched:
            prices = [float(item.get("scsbd_prc", 0)) for item in matched if float(item.get("scsbd_prc", 0)) > 0]
            qtys = [float(item.get("qty", 0)) for item in matched]
            if prices:
                daily_stats.append({
                    "날짜": target_date,
                    "평균가": int(sum(prices) / len(prices)),
                    "최고가": int(max(prices)),
                    "최저가": int(min(prices)),
                    "거래건수": len(prices),
                    "총수량": int(sum(qtys)),
                })

    if not daily_stats:
        return f"'{product_keyword}' 최근 {days}일간 데이터가 없습니다."

    market_name = MARKETS.get(market_code, "전국") if market_code else "전국"
    lines = [f"[가격 추이] '{product_keyword}' / {market_name} / 최근 {days}일\n"]
    lines.append(f"  {'날짜':12} {'평균가':>10} {'최저가':>10} {'최고가':>10} {'건수':>6} {'총수량':>8}")
    lines.append(f"  {'-'*60}")

    for stat in reversed(daily_stats):
        lines.append(
            f"  {stat['날짜']:12} {stat['평균가']:>10,}원 "
            f"{stat['최저가']:>10,}원 {stat['최고가']:>10,}원 "
            f"{stat['거래건수']:>6} {stat['총수량']:>8}"
        )

    # 등락 계산
    if len(daily_stats) >= 2:
        latest = daily_stats[0]["평균가"]
        oldest = daily_stats[-1]["평균가"]
        diff = latest - oldest
        pct = (diff / oldest * 100) if oldest > 0 else 0
        direction = "상승" if diff > 0 else "하락" if diff < 0 else "보합"
        lines.append(f"\n  {days}일간 {direction}: {abs(diff):,}원 ({pct:+.1f}%)")

    result = "\n".join(lines)
    _cache_set(cache_key, result, "daily")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 5: 도매시장 목록
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_market_list(
    region: str = "",
) -> str:
    """전국 공영 도매시장 목록과 부류(대분류) 코드를 조회합니다.

    Args:
        region: 지역 필터 (예: "대전", "서울", "부산"). 빈 문자열이면 전국.

    Returns:
        도매시장 코드 목록 및 부류 코드 목록
    """
    lines = ["[전국 공영 도매시장 목록]\n"]

    count = 0
    for code, name in sorted(MARKETS.items(), key=lambda x: x[1]):
        if region and region not in name:
            continue
        lines.append(f"  {code}: {name}")
        count += 1

    lines.append(f"\n총 {count}개 시장")
    lines.append("\n[부류(대분류) 코드]\n")
    for code, name in sorted(CATEGORIES.items(), key=lambda x: x[1]):
        lines.append(f"  {code}: {name}")

    return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 6: 경매 통계 요약
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_auction_summary(
    market_code: str = "",
    date: str = "",
) -> str:
    """도매시장 경매 데이터의 부류별/시장별 통계를 요약합니다.

    Args:
        market_code: 도매시장 코드. 빈 문자열이면 전국.
        date: 정산일 (YYYY-MM-DD). 빈 문자열이면 오늘.

    Returns:
        부류별 평균가, 거래건수, 시장별 거래 현황 요약
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    cache_key = f"summary:{market_code}:{date}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    params = {"date": date, "numOfRows": 1000}
    if market_code:
        params["market_code"] = market_code

    data = await _fetch_auction(params)
    if "error" in data:
        return f"API 오류: {data['error']}"

    body = data.get("response", {}).get("body", {})
    total = body.get("totalCount", 0)
    items_raw = body.get("items", {}).get("item", [])
    if isinstance(items_raw, dict):
        items_raw = [items_raw]

    if not items_raw:
        return f"{date} 경매 데이터가 없습니다."

    # 부류별 통계
    by_category: dict[str, dict] = {}
    by_market: dict[str, int] = {}

    for item in items_raw:
        cat = item.get("gds_mclsf_nm", "기타")
        price = float(item.get("scsbd_prc", 0))
        mkt = item.get("whsl_mrkt_nm", "")

        if cat not in by_category:
            by_category[cat] = {"prices": [], "count": 0}
        if price > 0:
            by_category[cat]["prices"].append(price)
        by_category[cat]["count"] += 1

        by_market[mkt] = by_market.get(mkt, 0) + 1

    market_name = MARKETS.get(market_code, "전국") if market_code else "전국"
    lines = [f"[경매 통계 요약] {date} / {market_name} (전체 {total:,}건, 조회 {len(items_raw)}건)\n"]

    # 부류별 요약
    lines.append("  [품목별 거래 현황]")
    sorted_cats = sorted(by_category.items(), key=lambda x: x[1]["count"], reverse=True)
    for cat, info in sorted_cats[:15]:
        if info["prices"]:
            avg = int(sum(info["prices"]) / len(info["prices"]))
            lines.append(f"    {cat}: {info['count']}건 | 평균 {avg:,}원")
        else:
            lines.append(f"    {cat}: {info['count']}건")

    # 시장별 요약
    if not market_code:
        lines.append("\n  [시장별 거래 현황]")
        sorted_mkts = sorted(by_market.items(), key=lambda x: x[1], reverse=True)
        for mkt, cnt in sorted_mkts[:10]:
            lines.append(f"    {mkt}: {cnt}건")

    result = "\n".join(lines)
    _cache_set(cache_key, result, "daily")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 서버 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "stdio":
        mcp.run()
    else:
        from mcp.server.transport_security import TransportSecuritySettings
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )
        mcp.run(transport=transport)
