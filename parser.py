import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

BASE_URL = "https://newwind.net.ua"
# Використовуємо URL прямим списком усіх товарів сайту
CATALOG_URL = f"{BASE_URL}/ua/product_list?product_items_per_page=48"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
}

session = requests.Session()
session.headers.update(headers)

def get_soup(url):
    try:
        response = session.get(url, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
        else:
            print(f"Статус відповіді {response.status_code} для {url}")
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
    return None

def build_yml_feed():
    print("Розпочинаємо збір товарів з newwind.net.ua...")
    
    yml_catalog = ET.Element('yml_catalog', date=time.strftime("%Y-%m-%d %H:%M"))
    shop = ET.SubElement(yml_catalog, 'shop')
    
    ET.SubElement(shop, 'name').text = "NewWind"
    ET.SubElement(shop, 'company').text = "NewWind"
    ET.SubElement(shop, 'url').text = BASE_URL

    currencies = ET.SubElement(shop, 'currencies')
    ET.SubElement(currencies, 'currency', id="UAH", rate="1")

    categories = ET.SubElement(shop, 'categories')
    cat_elem = ET.SubElement(categories, 'category', id="1")
    cat_elem.text = "Вентиляція та кліматична техніка"

    offers = ET.SubElement(shop, 'offers')

    page = 1
    total_parsed = 0

    while page <= 100:
        page_url = f"{CATALOG_URL}&page={page}"
        print(f"Парсинг сторінки №{page}...")
        soup = get_soup(page_url)
        
        if not soup:
            print("Не вдалося завантажити сторінку або каталог завершено.")
            break

        # Шукаємо товари за різними селекторами платформи Prom
        product_cards = soup.find_all('li', {'data-qaid': 'product_presence'}) or \
                        soup.find_all('div', {'data-qaid': 'product_block'}) or \
                        soup.find_all('li', class_=re.compile(r'product')) or \
                        soup.find_all('div', class_=re.compile(r'b-product-gallery__item|b-product-tile'))
        
        # Якщо картки не знайдено за обгорткою, шукаємо за посиланнями на товари
        if not product_cards:
            product_cards = soup.find_all('a', {'data-qaid': 'product_link'})
            if product_cards:
                # Отримуємо батьківські контейнери для кожного посилання
                product_cards = [a.find_parent(['li', 'div', 'tr']) for a in product_cards if a.find_parent(['li', 'div', 'tr'])]

        if not product_cards:
            print(f"На сторінці {page} товарів не знайдено. Завершення парсингу.")
            break

        parsed_on_page = 0

        for card in product_cards:
            try:
                # Посилання та Назва
                link_elem = card.find('a', {'data-qaid': 'product_link'}) or card.find('a', class_=re.compile(r'title|name|link'))
                if not link_elem or not link_elem.get('href'):
                    continue

                prod_url = link_elem['href']
                if not prod_url.startswith('http'):
                    prod_url = BASE_URL + prod_url

                title = link_elem.text.strip()
                if not title:
                    title = link_elem.get('title', '').strip()

                if not title:
                    continue

                # Наявність
                available = "true"
                presence_elem = card.find(attrs={'data-qaid': 'product_presence'}) or card.find(class_=re.compile(r'presence|status'))
                if presence_elem:
                    presence_text = presence_elem.text.lower()
                    if 'немає' in presence_text or 'під замовлення' in presence_text or 'знято' in presence_text:
                        available = "false"

                # Ціна
                price_elem = card.find(attrs={'data-qaid': 'product_price'}) or card.find(class_=re.compile(r'price'))
                if not price_elem:
                    continue
                
                price_text = re.sub(r'[^\d]', '', price_elem.text)
                if not price_text:
                    continue
                price = int(price_text)

                # Артикул (SKU)
                sku_elem = card.find(attrs={'data-qaid': 'product_code'}) or card.find(class_=re.compile(r'code|sku'))
                sku = ""
                if sku_elem:
                    sku = re.sub(r'[^\w\d-]', '', sku_elem.text.replace('Код:', '').replace('Артикул:', '')).strip()
                
                if not sku:
                    # Пробуємо витягнути ID з посилання або атрибутів
                    sku_match = re.search(r'p(\d+)-', prod_url)
                    sku = sku_match.group(1) if sku_match else f"NW-{total_parsed + 1}"

                # Формування offer у YML
                offer = ET.SubElement(offers, 'offer', id=str(sku), available=available)
                ET.SubElement(offer, 'url').text = prod_url
                ET.SubElement(offer, 'price').text = str(price)
                ET.SubElement(offer, 'currencyId').text = 'UAH'
                ET.SubElement(offer, 'categoryId').text = '1'
                ET.SubElement(offer, 'name').text = title
                ET.SubElement(offer, 'vendorCode').text = str(sku)

                # Зображення
                img_elem = card.find('img', {'data-qaid': 'product_image'}) or card.find('img')
                if img_elem:
                    img_src = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('image-src')
                    if img_src:
                        if img_src.startswith('//'):
                            img_src = 'https:' + img_src
                        elif not img_src.startswith('http'):
                            img_src = BASE_URL + img_src
                        ET.SubElement(offer, 'picture').text = img_src

                ET.SubElement(offer, 'description').text = f"<![CDATA[{title} — оригінальний товар від інтернет-магазину NewWind.]]>"

                total_parsed += 1
                parsed_on_page += 1

            except Exception as e:
                continue

        print(f"Сторінка {page}: додано {parsed_on_page} товарів. Загалом: {total_parsed}")

        if parsed_on_page == 0:
            print("Більше товарів на наступних сторінках немає.")
            break

        page += 1

    # Збереження YML-файлу
    xml_str = minidom.parseString(ET.tostring(yml_catalog, encoding='utf-8')).toprettyxml(indent="  ")
    with open("newwind_feed.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"\nГОТОВО! Збережено у newwind_feed.xml товарів: {total_parsed}")

if __name__ == "__main__":
    build_yml_feed()
