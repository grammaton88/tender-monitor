import os
import re
import time

import requests
from bs4 import BeautifulSoup

from tender_pipeline import ProcessingError, run_monitor

IT_BASECODES = {
    "18936": "32400000 - ქსელები",
    "18937": "32500000 - სატელეკომუნიკაციო მოწყობილობები და აქსესუარები",
    "19006": "48100000 - პროგრამული უზრუნველყოფის სამრეწველო პაკეტები",
    "19012": "48200000 - ქსელების, ინტერნეტისა და ინტრანეტის პროგრამული პაკეტები",
    "19013": "48300000 - დოკუმენტების, გრაფიკული გამოსახულებების შექმნის პროგრამული პაკეტები",
    "19014": "48400000 - საქმიანი გარიგებებისა და პირადი საქმეების მართვის პროგრამული პაკეტები",
    "19015": "48500000 - საკომუნიკაციო და მულტიმედიის პროგრამული პაკეტები",
    "19017": "48700000 - პროგრამული პაკეტების მომსახურე პროგრამები",
    "19009": "48900000 - სხვადასხვა სახის პროგრამული პაკეტები და კომპიუტერული სისტემები",
    "19027": "51600000 - კომპიუტერებისა და საოფისე მოწყობილობების დამონტაჟება",
    "19070": "72100000 - აპარატურულ უზრუნველყოფასთან დაკავშირებული საკონსულტაციო მომსახურებები",
    "19083": "72300000 - მონაცემთა მომსახურება",
    "19072": "72500000 - კომპიუტერთან დაკავშირებული მომსახურებები",
    "19073": "72600000 - კომპიუტერული უზრუნველყოფა და საკონსულტაციო მომსახურებები",
    "19074": "72700000 - კომპიუტერული ქსელის მომსახურება",
    "19075": "72800000 - კომპიუტერის შემოწმება და ტესტირება",
    "19076": "72900000 - კომპიუტერის მონაცემების სარეზერვო დუბლირება",
}

BASE_URL = "https://tenders.procurement.gov.ge/public"
CONTROLLER = f"{BASE_URL}/library/controller.php"
APP_TYPE_CODES = {
    "0": "0",
    "ALL": "0",
    "NAT": "9",
    "SPA": "2",
    "CON": "4",
    "GEO": "3",
    "NAT_SIMPLIFIED": "8",
    "SPA_SIMPLIFIED": "1",
    "MEP": "11",
    "DAP": "15",
    "TEP": "16",
    "DEP": "5",
    "GRA": "7",
    "PPP": "22",
    "B2B": "20",
    "CNT": "6",
}


def normalize_app_type(app_type: str | int | None = None) -> str:
    if app_type is None:
        app_type = os.getenv("APP_TYPE")
        if app_type is None:
            app_type = os.getenv("APP_TYPE_FILTER", "0")
    if app_type in ("", None):
        return "0"
    if isinstance(app_type, (list, tuple, set)):
        for item in app_type:
            candidate = normalize_app_type(item)
            if candidate != "0":
                return candidate
        return "0"
    value = str(app_type).strip().upper()
    if "," in value:
        for item in value.split(","):
            candidate = normalize_app_type(item)
            if candidate != "0":
                return candidate
        return "0"
    if value in APP_TYPE_CODES:
        return APP_TYPE_CODES[value]
    if value.isdigit():
        return value
    aliases = {
        "NAT-STD": "NAT",
        "NAT_STANDARD": "NAT",
        "NAT-REGULAR": "NAT",
        "SPA-STD": "SPA",
        "SPA_STANDARD": "SPA",
        "SPA-REGULAR": "SPA",
        "CONSOLIDATED": "CON",
        "GEO-STD": "GEO",
        "GEO_STANDARD": "GEO",
        "GEO-REGULAR": "GEO",
    }
    candidate = aliases.get(value)
    if candidate:
        return APP_TYPE_CODES[candidate]
    raise ValueError(f"Unsupported procurement type filter: {app_type!r}")


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ka,en-US;q=0.9,en;q=0.8",
    })
    session.get(f"{BASE_URL}/?go=", timeout=30).raise_for_status()
    return session


def search_tenders(session, basecode: str, app_type: str | int | None = None) -> list[dict]:
    payload = {
        "action": "search_app",
        "app_t": "0",
        "search": "",
        "app_reg_id": "",
        "app_shems_id": "0",
        "org_a": "",
        "app_monac_id": "0",
        "org_b": "",
        "app_particip_status_id": "0",
        "app_donor_id": "0",
        "app_status": "10",          # მხოლოდ გამოცხადებულია
        "app_agr_status": "0",
        "app_type": normalize_app_type(app_type),
        "app_basecode": basecode,
        "app_codes": "",
        "app_date_type": "1",
        "app_date_from": "",
        "app_date_tlll": "",
        "app_amount_from": "",
        "app_amount_to": "",
        "app_currency": "2",
        "app_pricelist": "0",
    }

    headers = {
        "Referer": f"{BASE_URL}/?go=",
    }

    r = session.get(CONTROLLER, params=payload, headers=headers, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"

    soup = BeautifulSoup(r.text, "html.parser")
    pager = soup.select_one(".pager")
    match = re.search(r"(\d+)\s*/\s*(\d+)", pager.get_text(" ", strip=True)) if pager else None
    if not match:
        raise ProcessingError(f"Unrecognized search response for CPV {basecode}; missing pagination")
    pages = int(match[2])
    if pages > 200:
        raise ProcessingError(f"Unexpected page count {pages} for CPV {basecode}; manual review needed")
    results = parse_search_results(soup, basecode)
    if pages and not results:
        raise ProcessingError(f"Search reports results but returned no tender rows for CPV {basecode}")
    for page in range(2, pages + 1):
        response = session.get(
            CONTROLLER, params={"action": "search_app", "page": page},
            headers={"Referer": f"{BASE_URL}/?go="}, timeout=30,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        page_soup = BeautifulSoup(response.text, "html.parser")
        page_pager = page_soup.select_one(".pager")
        position = re.search(r"(\d+)\s*/\s*(\d+)", page_pager.get_text(" ", strip=True)) if page_pager else None
        if not position or int(position[1]) != page:
            raise ProcessingError(f"Pagination/session mismatch for CPV {basecode}, page {page}")
        page_results = parse_search_results(page_soup, basecode)
        if not page_results:
            raise ProcessingError(f"Empty result page for CPV {basecode}, page {page}")
        results.extend(page_results)
    return results


def parse_search_results(soup: BeautifulSoup, basecode: str) -> list[dict]:
    results = []

    for tr in soup.select("tr[id^='A']"):
        try:
            tender_id = tr.get("id", "").lstrip("A")
            status_el = tr.select_one("p.status")
            status_text = status_el.get_text(strip=True) if status_el else ""

            reg_num = buyer = category = amount = announce_date = deadline = ""

            for p in tr.select("p"):
                txt = p.get_text(" ", strip=True)
                if "განცხადების ნომერი" in txt:
                    strong = p.find("strong")
                    reg_num = strong.get_text(strip=True) if strong else txt
                elif "შემსყიდველი" in txt:
                    strong = p.find("strong")
                    buyer = strong.get_text(strip=True) if strong else txt
                elif "შესყიდვის კატეგორია" in txt:
                    category = txt.replace("შესყიდვის კატეგორია:", "").strip()
                elif "სავარაუდო ღირებულება" in txt:
                    amount = txt
                elif "გამოცხადების თარიღი" in txt:
                    announce_date = txt
                elif "მიღების ვადა" in txt:
                    deadline = txt

            link = f"{BASE_URL}/?go={tender_id}" if tender_id else ""

            results.append({
                "id": tender_id,
                "reg_num": reg_num,
                "status": status_text,
                "buyer": buyer,
                "category": category,
                "amount": amount,
                "announce_date": announce_date,
                "deadline": deadline,
                "link": link,
            })
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProcessingError(f"Invalid tender row in CPV {basecode}: {exc}") from exc

    return results


def main():
    print("=" * 60)
    print("Starting IT Tender Monitor")
    print("=" * 60)

    from monitor_settings import apply_config_to_environment, load_config

    config = load_config()
    if not config["enabled"]:
        print("Tender monitoring is disabled in monitor-config.json")
        return
    apply_config_to_environment(config)

    def search_with_retries(session, basecode: str, app_type: str) -> list[dict]:
        # The portal occasionally drops connections; a restarted search is safe.
        for delay in (5, 20, None):
            try:
                return search_tenders(session, basecode, app_type)
            except (requests.ConnectionError, requests.Timeout):
                if delay is None:
                    raise
                print(f"CPV {basecode}: portal connection dropped; retrying in {delay}s")
                time.sleep(delay)

    def search_selected_types(session, basecode: str) -> list[dict]:
        results = {}
        for app_type in config["app_types"]:
            for tender in search_with_retries(session, basecode, app_type):
                if tender["id"]:
                    results[tender["id"]] = tender
            time.sleep(1.3)
        return list(results.values())

    with create_session() as session:
        selected_basecodes = {
            code: IT_BASECODES[code] for code in config["cpv_codes"]
        }
        run_monitor(session, search_selected_types, selected_basecodes)


if __name__ == "__main__":
    main()