
import asyncio
import json
import logging
import os
import re
from playwright.async_api import async_playwright

BASE_URL = "https://webscraper.io/test-sites/e-commerce/allinone/computers/laptops"
OUTPUT_FILE = "output.json"

def setup_logger():
    logging.basicConfig(
        filename="scraper.log",
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    return logging.getLogger("scraper")

async def scrape():
    logger = setup_logger()
    logger.info("Script started.")
    logger.info("Starting Playwright context...")
    results = []
    try:
        async with async_playwright() as p:
            logger.info("Playwright started.")
            logger.info("Launching Chromium browser...")
            browser = await p.chromium.launch(headless=True)
            logger.info("Browser launched.")
            page = await browser.new_page()
            logger.info("New page created.")
            logger.info(f"Navigating to {BASE_URL}")
            await page.goto(BASE_URL)
            logger.info("Page navigation complete.")
            await page.wait_for_load_state('networkidle')
            logger.info("Page load state 'networkidle' reached.")
            page_num = 1
            while True:
                await page.wait_for_timeout(1000)
                logger.info(f"Scraping page {page_num}")
                html = await page.content()
                logger.debug(f"DEBUG: Page HTML:\n{html[:1000]}")
                try:
                    laptops = await page.query_selector_all('div.card.thumbnail')
                    logger.info(f"Found {len(laptops)} laptop cards with selector 'div.card.thumbnail'")
                except Exception as sel_e:
                    logger.error(f"Error querying selector 'div.card.thumbnail': {sel_e}")
                    laptops = []
                if not laptops:
                    logger.warning("No laptop cards found on this page!")
                else:
                    logger.info("Attempting to extract laptop data...")
                    
                for idx, laptop in enumerate(laptops):
                    try:
                        logger.info(f"Processing laptop card {idx+1}")
                        title_elem = await laptop.query_selector('a.title')
                        title = await title_elem.get_attribute('title') if title_elem else ""
                        logger.info(f"title: {title}")
                        price_elem = await laptop.query_selector('h4.price span[itemprop="price"]')
                        price_raw = await price_elem.text_content() if price_elem else ""
                        # Remove any non-numeric characters except dot
                        price_num = re.sub(r'[^\d.]', '', price_raw)
                        try:
                            price_float = float(price_num)
                            price = f"${price_float:,.2f}"
                        except Exception:
                            price = price_raw
                        logger.info(f"price: {price}")
                        # Try multiple selectors for description
                        description = ""
                        desc_elem = await laptop.query_selector('p.description')
                        if not desc_elem:
                            desc_elem = await laptop.query_selector('div.description')
                        if not desc_elem:
                            desc_elem = await laptop.query_selector('div.tab-content')
                        if not desc_elem:
                            desc_elem = await laptop.query_selector('div.card-block')
                        if desc_elem:
                            description = await desc_elem.text_content()
                        logger.info(f"description: {description}")
                        reviews_elem = await laptop.query_selector('div.ratings p.review-count span[itemprop=\"reviewCount\"]')
                        reviews_count = int(await reviews_elem.text_content()) if reviews_elem else 0
                        logger.info(f"reviews_count: {reviews_count}")
                        rating_elem = await laptop.query_selector('div.ratings p[data-rating]')
                        rating = int(await rating_elem.get_attribute('data-rating')) if rating_elem else 0
                        logger.info(f"rating: {rating}")
                        product_url = await title_elem.get_attribute('href') if title_elem else ""
                        # Always use base domain for product_url
                        if product_url:
                            if product_url.startswith("http"):
                                full_product_url = product_url
                            else:
                                full_product_url = "https://webscraper.io" + product_url
                        else:
                            full_product_url = ""
                        logger.info(f"product_url: {full_product_url}")
                    except Exception as e:
                        logger.error(f"Error extracting laptop {idx+1}: {e}")
                        continue
                    
                    # Always extract description from detail page
                    description = ""
                    try:
                        if full_product_url:
                            detail_page = await browser.new_page()
                            logger.info(f"Opened detail page for {title}")
                            await detail_page.goto(full_product_url)
                            logger.info(f"Navigated to detail page: {full_product_url}")
                            await detail_page.wait_for_load_state('networkidle')
                            logger.info("Detail page load state 'networkidle' reached.")
                            # Log HTML for diagnosis (only for first product)
                            if idx == 0 and page_num == 1:
                                detail_html = await detail_page.content()
                                logger.info(f"DETAIL PAGE HTML FOR {title} (first product):\n{detail_html[:2000]}")
                            # Use the exact selector from provided HTML for description
                            desc_elem = await detail_page.query_selector('p.description.card-text[itemprop="description"]')
                            if not desc_elem:
                                desc_elem = await detail_page.query_selector('p.description')
                            if desc_elem:
                                description = await desc_elem.text_content()
                            await detail_page.close()
                            logger.info(f"description: {description}")                                
                            logger.info("Detail page closed.")
                    except Exception as e:
                        logger.error(f"Error extracting description for {title}: {e}")
                        description = ""
                        
                    results.append({
                        "title": title.strip(),
                        "price": price.strip(),
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "product_url": full_product_url,
                        "description": description.strip() if description else ""
                    })
                    
                next_btn = await page.query_selector('ul.pagination li.next a')
                
                if next_btn and await next_btn.is_enabled():
                    await next_btn.click()
                    logger.info("Clicked next page button.")
                    await page.wait_for_timeout(1000)
                    await page.wait_for_load_state('networkidle')
                    logger.info("Next page load state 'networkidle' reached.")
                    page_num += 1
                else:
                    logger.info("No more pages. Scraping finished.")
                    break
            await browser.close()
            logger.info("Browser closed.")
    except Exception as e:
        logger.error(f"Fatal error in scrape: {e}")
        
        
    # Clear output.json before writing new data
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Scraping complete. {len(results)} products saved to {OUTPUT_FILE}.")
    except Exception as file_e:
        logger.error(f"Error writing {OUTPUT_FILE}: {file_e}")

if __name__ == "__main__":
    asyncio.run(scrape())