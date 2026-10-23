import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

BASE_URL = "https://newwind.net.ua"
# Переходимо на загальний пошук або виводимо всі товари через параметри каталогу Prom.ua
CATALOG_URL = f"{BASE_URL}/ua/product_list?product_items_per_page=48"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

session = requests.Session()
session.headers.update(headers)

def get_soup(url):
    try:
        response = session.get(url, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
    return None

def build_yml_feed():
    print("Розпочинаємо збір товарів...")
    
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
    seen_urls = set()

    while page <= 50:
        page_url = f"{CATALOG_URL}&page={page}"
        print(f"Перевірка сторінки №{page}...")
        soup = get_soup(page_url)
        
        if not soup:
            break

        # Знаходимо всі посилання на товари безпосередньо за атрибутом Prom.ua
        product_links = soup.find_all('a', {'data-qaid': 'product_link'})
        
        if not product_links:
            # Альтернативний пошук посилань у галереї
            product_links = soup.find_all('a', class_=re.compile(r'b-product-gallery__title|title|link'))

        if not product_links:
            print(f"На сторінці {page} посилань на товари не знайдено.")
            break

        parsed_on_page = 0

        for link in product_links:
            try:
                prod_url = link.get('href')
                if not prod_url:
                    continue
                
                if not prod_url.startswith('http'):
                    prod_url = BASE_URL + prod_url

                if prod_url in seen_urls:
                    continue
                seen_urls.add(prod_url)

                title = link.text.strip()
                if not title:
                    title = link.get('title', '').strip()
                if not title:
                    continue

                # Шукаємо батьківський блок товару, щоб витягнути ціну та фото
                card = link.find_parent(['li', 'div', 'tr'])
                
                price = 1000  # Дефолтна ціна на випадок відсутності
                available = "true"
                sku = f"NW-{total_parsed + 1}"
                img_src = ""

                if card:
                    # Ціна
                    price_elem = card.find(attrs={'data-qaid': 'product_price'}) or card.find(class_=re.compile(r'price'))
                    if price_elem:
                        price_text = re.sub(r'[^\d]', '', price_elem.text)
                        if price_text:
                            price = int(price_text)

                    # Наявність
                    presence_elem = card.find(attrs={'data-qaid': 'product_presence'}) or card.find(class_=re.compile(r'presence|status'))
                    if presence_elem and ('немає' in presence_elem.text.lower() or 'під замовлення' in presence_elem.text.lower()):
                        available = "false"

                    # Код
                    sku_elem = card.find(attrs={'data-qaid': 'product_code'}) or card.find(class_=re.compile(r'code|sku'))
                    if sku_elem:
                        sku = re.sub(r'[^\w\d-]', '', sku_elem.text.replace('Код:', '').replace('Артикул:', '')).strip()

                    # Фото
                    img_elem = card.find('img', {'data-qaid': 'product_image'}) or card.find('img')
                    if img_elem:
                        img_src = img_elem.get('src') or img_elem.get('data-src') or ''
                        if img_src.startswith('//'):
                            img_src = 'https:' + img_src
                        elif not img_src.startswith('http') and img_src:
                            img_src = BASE_URL + img_src

                # Формуємо offer
                offer = ET.SubElement(offers, 'offer', id=str(sku), available=available)
                ET.SubElement(offer, 'url').text = prod_url
                ET.SubElement(offer, 'price').text = str(price)
                ET.SubElement(offer, 'currencyId').text = 'UAH'
                ET.SubElement(offer, 'categoryId').text = '1'
                ET.SubElement(offer, 'name').text = title
                ET.SubElement(offer, 'vendorCode').text = str(sku)

                if img_src:
                    ET.SubElement(offer, 'picture').text = img_src

                ET.SubElement(offer, 'description').text = f"<![CDATA[{title} — купити в інтернет-магазині NewWind.]]>"

                total_parsed += 1
                parsed_on_page += 1

            except Exception as e:
                continue

        print(f"Сторінка {page}: знайдено товарів: {parsed_on_page}")
        
        if parsed_on_page == 0:
            break

        page += 1

    xml_str = minidom.parseString(ET.tostring(yml_catalog, encoding='utf-8')).toprettyxml(indent="  ")
    with open("newwind_feed.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"\nГОТОВО! Збережено товарів: {total_parsed}")

if __name__ == "__main__":
    build_yml_feed()
