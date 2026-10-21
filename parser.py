import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from xml.dom import minidom
import time
import re

BASE_URL = "https://newwind.net.ua"
CATALOG_URL = f"{BASE_URL}/ua/product_list"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_soup(url):
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Помилка завантаження {url}: {e}")
    return None

def parse_product_details(product_url):
    soup = get_soup(product_url)
    if not soup:
        return {}, []

    details = {
        'description': '',
        'images': [],
        'params': {}
    }

    # Опис
    desc_elem = soup.find('div', {'data-qaid': 'product_description'}) or soup.find('div', class_='b-user-content')
    if desc_elem:
        details['description'] = desc_elem.decode_contents().strip()

    # Додаткові зображення
    img_elems = soup.find_all('img', {'data-qaid': 'product_image'})
    for img in img_elems:
        src = img.get('src') or img.get('data-src')
        if src:
            if not src.startswith('http'):
                src = BASE_URL + src
            if src not in details['images']:
                details['images'].append(src)

    # Характеристики (таблиця параметрів)
    param_rows = soup.find_all('tr', {'data-qaid': 'product_attribute'}) or soup.find_all('tr', class_='b-product-info__row')
    for row in param_rows:
        cols = row.find_all(['td', 'th'])
        if len(cols) >= 2:
            name = cols[0].text.strip().rstrip(':')
            value = cols[1].text.strip()
            if name and value:
                details['params'][name] = value

    return details

def build_yml_feed():
    print("Початок збору даних з newwind.net.ua...")
    
    # Створення структури YML
    yml_catalog = ET.Element('yml_catalog', date=time.strftime("%Y-%m-%d %H:%M"))
    shop = ET.SubElement(yml_catalog, 'shop')
    
    ET.SubElement(shop, 'name').text = "NewWind Import"
    ET.SubElement(shop, 'company').text = "NewWind"
    ET.SubElement(shop, 'url').text = BASE_URL

    # Валюти
    currencies = ET.SubElement(shop, 'currencies')
    ET.SubElement(currencies, 'currency', id="UAH", rate="1")

    # Категорії
    categories = ET.SubElement(shop, 'categories')
    cat_elem = ET.SubElement(categories, 'category', id="1")
    cat_elem.text = "Вентиляція та кліматична техніка"

    offers = ET.SubElement(shop, 'offers')

    page = 1
    total_parsed = 0

    while True:
        page_url = f"{CATALOG_URL}?page={page}"
        print(f"Парсинг сторінки каталогу №{page}...")
        soup = get_soup(page_url)
        
        if not soup:
            break

        product_cards = soup.find_all('div', {'data-qaid': 'product_block'}) or soup.find_all('li', class_='b-product-gallery__item')
        
        if not product_cards:
            print("Більше товарів не знайдено.")
            break

        for card in product_cards:
            try:
                # Посилання на товар
                link_elem = card.find('a', {'data-qaid': 'product_link'}) or card.find('a', class_='b-product-gallery__title')
                if not link_elem or not link_elem.get('href'):
                    continue
                
                prod_url = link_elem['href']
                if not prod_url.startswith('http'):
                    prod_url = BASE_URL + prod_url

                # Назва
                title = link_elem.text.strip()

                # Наявність
                available = "true"
                status_elem = card.find('span', {'data-qaid': 'product_presence'})
                if status_elem and ('немає' in status_elem.text.lower() or 'під замовлення' in status_elem.text.lower()):
                    available = "false"

                # Ціна
                price_elem = card.find('span', {'data-qaid': 'product_price'}) or card.find('span', class_='b-product-gallery__price')
                if not price_elem:
                    continue
                
                price_text = re.sub(r'[^\d]', '', price_elem.text)
                if not price_text:
                    continue
                price = int(price_text)

                # Артикул (SKU)
                sku_elem = card.find('span', {'data-qaid': 'product_code'})
                sku = sku_elem.text.replace('Код:', '').strip() if sku_elem else f"NW-{total_parsed+1}"

                # Збираємо деталі (опис, додаткові фото, характеристики)
                details = parse_product_details(prod_url)

                # Формуємо тег offer у YML
                offer = ET.SubElement(offers, 'offer', id=sku, available=available)
                ET.SubElement(offer, 'url').text = prod_url
                ET.SubElement(offer, 'price').text = str(price)
                ET.SubElement(offer, 'currencyId').text = 'UAH'
                ET.SubElement(offer, 'categoryId').text = '1'
                ET.SubElement(offer, 'name').text = title
                ET.SubElement(offer, 'vendorCode').text = sku

                # Фотографії
                for img_url in details['images']:
                    ET.SubElement(offer, 'picture').text = img_url

                # Опис
                if details['description']:
                    ET.SubElement(offer, 'description').text = f"<![CDATA[{details['description']}]]>"

                # ХАРАКТЕРИСТИКИ ДЛЯ PROM.UA
                for param_name, param_val in details['params'].items():
                    param_tag = ET.SubElement(offer, 'param', name=param_name)
                    param_tag.text = param_val

                total_parsed += 1
                print(f"Успішно додано товар [{sku}]: {title}")

            except Exception as e:
                print(f"Помилка при опрацюванні товару: {e}")

        page += 1
        time.sleep(1) # Затримка, щоб не перевантажувати сайт

    # Збереження у красивий XML
    xml_str = minidom.parseString(ET.tostring(yml_catalog, encoding='utf-8')).toprettyxml(indent="  ")
    with open("newwind_feed.xml", "w", encoding="utf-8") as f:
        f.write(xml_str)

    print(f"\nГОТОВО! Всього збережено товарів: {total_parsed}")

if __name__ == "__main__":
    build_yml_feed()
