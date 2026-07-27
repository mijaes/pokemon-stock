import os
import subprocess
import time
from bs4 import BeautifulSoup
import pandas as pd
from playwright.sync_api import sync_playwright
import streamlit as st

# --- 1. 웹 페이지 기본 설정 ---
st.set_page_config(
    page_title="포켓몬 스토어 실시간 재고 탐지기 V2",
    page_icon="⚡",
    layout="wide",
)


# --- 2. 클라우드 서버 구동 시 딱 1번 브라우저 엔진 자동 설치 ---
@st.cache_resource
def install_playwright():
    subprocess.run(["playwright", "install", "chromium"])


install_playwright()
# ------------------------------------------------------------------

st.title("⚡ 포켓몬 스토어 실시간 재고 조회 (딥-스크롤 V2)")
st.markdown(
    "화면을 강제로 스크롤하여 숨겨진 상품까지 모두 깨운 뒤, **실제 구매 가능한 재고**만 찾아냅니다."
)


# --- 3. 핵심 크롤링 (딥-스크롤 적용) 함수 ---
@st.cache_data(ttl=300)
def fetch_in_stock_products(category_url, max_pages=3):
    in_stock_list = []
    total_scanned = 0
    sold_out_count = 0

    with sync_playwright() as p:
        # 리눅스 서버 충돌 방지 필수 보안 옵션
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        page = browser.new_page()

        for page_num in range(1, max_pages + 1):
            target_url = f"{category_url}&page={page_num}"
            page.goto(target_url, timeout=30000)

            # 💡 [핵심 업그레이드] 페이지 맨 밑까지 3번에 걸쳐 강제 스크롤! (Lazy Loading 깨우기)
            for _ in range(3):
                page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                page.wait_for_timeout(1000)

            # 스크롤 후 최종 렌더링 대기
            page.wait_for_timeout(2000)

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # 포켓몬 스토어의 다양한 상품 리스트 태그 광범위 수집
            products = soup.select(
                "li[class*='item'], div[class*='item-list'] > div, ul > li"
            )

            if not products:
                break

            for prod in products:
                text_content = prod.get_text()

                # 상품 이름이나 가격 정보가 아예 없는 빈 태그는 제외
                if len(text_content.strip()) < 5:
                    continue

                total_scanned += 1

                # 💡 'SOLD OUT', '품절', '일시품절' 문구가 있으면 품절 카운트 증가 후 제외
                if any(
                    keyword in text_content
                    for keyword in ["SOLD OUT", "품절", "Sold Out"]
                ):
                    sold_out_count += 1
                    continue

                # 상품명 추출
                title_elem = prod.select_one(
                    "p[class*='name'], a[class*='title'], div[class*='name'], span[class*='name']"
                )
                title = (
                    title_elem.get_text(strip=True)
                    if title_elem
                    else "상품명 확인 불가"
                )

                # 가격 추출
                price_elem = prod.select_one(
                    "span[class*='price'], p[class*='price'], div[class*='price']"
                )
                price = (
                    price_elem.get_text(strip=True)
                    if price_elem
                    else "가격 확인 불가"
                )

                # 링크 추출
                link_elem = prod.select_one("a")
                link = ""
                if link_elem and "href" in link_elem.attrs:
                    link = link_elem["href"]
                    if not link.startswith("http"):
                        link = f"https://www.pokemonstore.co.kr{link}"

                # 이미지 추출
                img_elem = prod.select_one("img")
                img_url = ""
                if img_elem and "src" in img_elem.attrs:
                    img_url = img_elem["src"]
                    if not img_url.startswith("http"):
                        img_url = f"https:{img_url}"

                # 유효한 상품만 리스트에 저장
                if title != "상품명 확인 불가" and link and "원" in price:
                    in_stock_list.append(
                        {
                            "이미지": img_url,
                            "상품명": title,
                            "가격": price,
                            "구매링크": link,
                        }
                    )

        browser.close()

    return in_stock_list, total_scanned, sold_out_count


# --- 4. 사이드바 옵션 (페이지 범위 대폭 확장) ---
st.sidebar.header("🔍 조회 옵션 설정")
category_dict = {
    "전체 상품 (신상품 등)": "https://www.pokemonstore.co.kr/pages/product/product-list.html?categoryNo=488375",
    "봉제인형 / 마스코트": "https://www.pokemonstore.co.kr/pages/product/product-list.html?categoryNo=488376",
    "피규어": "https://www.pokemonstore.co.kr/pages/product/product-list.html?categoryNo=488377",
    "카드 게임 (TCG)": "https://www.pokemonstore.co.kr/pages/product/product-list.html?categoryNo=488383",
}

selected_cat_name = st.sidebar.selectbox(
    "카테고리 선택", list(category_dict.keys())
)
selected_url = category_dict[selected_cat_name]

# 💡 페이지 수를 10페이지까지 넓혀서 딥-스캔 가능하게 변경!
max_pages = st.sidebar.slider(
    "탐색할 최대 페이지 수 (높을수록 오래 걸림)",
    min_value=1,
    max_value=10,
    value=5,
)

# --- 5. 화면 출력 및 진단 결과 ---
if st.button("🔄 실시간 재고 딥-스캔 시작", type="primary"):
    with st.spinner(
        f"'{selected_cat_name}' {max_pages}개 페이지를 스크롤하며 숨은 재고를 찾는 중... (약 20~40초 소요)"
    ):
        results, total, sold_out = fetch_in_stock_products(
            selected_url, max_pages
        )

    # 💡 스크레이퍼가 실제로 몇 개를 읽었는지 투명하게 보여주는 진단 바
    st.info(
        f"🤖 **스캔 분석 결과:** 총 **{total}개**의 상품을 읽어들였으며, 그중 **{sold_out}개**의 품절 상품을 걸러냈습니다."
    )

    if not results:
        st.warning(
            "😭 스캔한 영역 내에 재고가 남아있는 상품이 없습니다. 사이드바에서 '탐색할 최대 페이지 수'를 10으로 늘려서 다시 시도해 보세요!"
        )
    else:
        st.success(f"🎉 총 **{len(results)}개**의 구매 가능한 보물(재고)을 발견했습니다!")

        for item in results:
            col1, col2 = st.columns([1, 4])
            with col1:
                if item["이미지"]:
                    st.image(item["이미지"], use_container_width=True)
                else:
                    st.write("이미지 없음")
            with col2:
                st.subheader(item["상품명"])
                st.write(f"**가격:** {item['가격']}")
                st.markdown(
                    f"[🛒 **공식 스토어에서 바로 구매하기**]({item['구매링크']})"
                )
            st.divider()
