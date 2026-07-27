import time
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- 1. 웹 페이지 기본 설정 ---
st.set_page_config(
    page_title="포켓몬 스토어 실시간 재고 탐지기",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ 포켓몬 스토어 실시간 재고 조회 웹사이트")
st.markdown("공식 스토어의 수많은 품절(SOLD OUT) 상품을 제외하고, **현재 구매 가능한 상품만** 실시간으로 추출합니다.")


# --- 2. 핵심 크롤링 및 필터링 함수 ---
@st.cache_data(ttl=300)  # 5분 동안 데이터 캐시 (서버 과부하 방지)
def fetch_in_stock_products(category_url, max_pages=3):
    in_stock_list = []

    with sync_playwright() as p:
        # headless=True로 설정하면 창을 띄우지 않고 백그라운드에서 빠르게 동작합니다.
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for page_num in range(1, max_pages + 1):
            # 페이지 번호를 추가하여 URL 이동 (쇼핑몰 구조에 맞게 쿼리스트링 조정)
            target_url = f"{category_url}&page={page_num}"
            page.goto(target_url, timeout=30000)

            # 상품 리스트가 로딩될 때까지 잠시 대기 (SPA 쇼핑몰 동적 렌더링 대기)
            page.wait_for_timeout(2500)

            # 렌더링된 HTML 소스코드 가져오기
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            # 상품 리스트 아이템 찾기 (쇼핑몰 HTML 구조에 따른 선택자)
            # 보통 포켓몬스토어는 상품 목록이 li나 div 형태의 리스트로 구성됩니다.
            products = soup.select(
                "li[class*='item'], div[class*='product-item'], div[class*='item-list'] > div"
            )

            if not products:
                # 더 이상 상품이 없으면 크롤링 종료
                break

            for prod in products:
                text_content = prod.get_text()

                # 💡 [핵심 필터링] 'SOLD OUT', '품절' 문구가 포함된 상품은 가차 없이 제외
                if "SOLD OUT" in text_content or "품절" in text_content:
                    continue

                # 상품명 추출
                title_elem = prod.select_one(
                    "p[class*='name'], a[class*='title'], div[class*='name']"
                )
                title = (
                    title_elem.get_text(strip=True) if title_elem else "상품명 확인 불가"
                )

                # 가격 추출
                price_elem = prod.select_one(
                    "span[class*='price'], p[class*='price'], div[class*='price']"
                )
                price = (
                    price_elem.get_text(strip=True) if price_elem else "가격 확인 불가"
                )

                # 상품 상세 링크 추출
                link_elem = prod.select_one("a")
                link = ""
                if link_elem and "href" in link_elem.attrs:
                    link = link_elem["href"]
                    if not link.startswith("http"):
                        link = f"https://www.pokemonstore.co.kr{link}"

                # 이미지 URL 추출
                img_elem = prod.select_one("img")
                img_url = ""
                if img_elem and "src" in img_elem.attrs:
                    img_url = img_elem["src"]
                    if not img_url.startswith("http"):
                        img_url = f"https:{img_url}"

                # 유효한 상품 데이터만 리스트에 추가
                if title != "상품명 확인 불가" and link:
                    in_stock_list.append(
                        {
                            "이미지": img_url,
                            "상품명": title,
                            "가격": price,
                            "구매링크": link,
                        }
                    )

        browser.close()

    return in_stock_list


# --- 3. 사이드바 메뉴 및 옵션 설정 ---
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
max_pages = st.sidebar.slider("탐색할 최대 페이지 수", min_value=1, max_value=5, value=2)

# --- 4. 화면 출력 로직 ---
if st.button("🔄 실시간 재고 조회 시작", type="primary"):
    with st.spinner(
        f"'{selected_cat_name}' 카테고리에서 품절 상품을 걸러내는 중... (약 10~20초 소요)"
    ):
        results = fetch_in_stock_products(selected_url, max_pages)

    if not results:
        st.warning("😭 현재 조회한 페이지 내에 재고가 있는 상품이 없습니다.")
    else:
        st.success(
            f"🎉 총 **{len(results)}개**의 구매 가능한 상품을 발견했습니다!"
        )

        # 데이터프레임 변환 및 카드 형태로 시각화
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
                    f"[🛒 **공식 스토어에서 구매하기**]({item['구매링크']})"
                )
            st.divider()
