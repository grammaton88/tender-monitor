import requests
from bs4 import BeautifulSoup
import re
from tender_pipeline import ProcessingError, run_monitor

IT_BASECODES = {
    "18924": "30200000 - კომპიუტერული მოწყობილობები და აქსესუარები",
    "18936": "32400000 - ქსელები",
    "18937": "32500000 - სატელეკომუნიკაციო მოწყობილობები და აქსესუარები",
    "19006": "48100000 - პროგრამული უზრუნველყოფის სამრეწველო პაკეტები",
    "19012": "48200000 - ქსელების, ინტერნეტისა და ინტრანეტის პროგრამული პაკეტები",
    "19013": "48300000 - დოკუმენტების, გრაფიკული გამოსახულებების შექმნის პროგრამული პაკეტები",
    "19014": "48400000 - საქმიანი გარიგებებისა და პირადი საქმეების მართვის პროგრამული პაკეტები",
    "19015": "48500000 - საკომუნიკაციო და მულტიმედიის პროგრამული პაკეტები",
    "19016": "48600000 - მონაცემთა ბაზისა და ოპერაციული პროგრამული პაკეტები",
    "19017": "48700000 - პროგრამული პაკეტების მომსახურე პროგრამები",
    "19008": "48800000 - საინფორმაციო სისტემები და სერვერები",
    "19009": "48900000 - სხვადასხვა სახის პროგრამული პაკეტები და კომპიუტერული სისტემები",
    "19025": "50300000 - პერსონალური კომპიუტერების, საოფისე აპარატურის შეკეთება",
    "19027": "51600000 - კომპიუტერებისა და საოფისე მოწყობილობების დამონტაჟება",
    "19056": "64200000 - სატელეკომუნიკაციო მომსახურებები",
    "19070": "72100000 - აპარატურულ უზრუნველყოფასთან დაკავშირებული საკონსულტაციო მომსახურებები",
    "19071": "72200000 - პროგრამული უზრუნველყოფის შემუშავება და საკონსულტაციო მომსახურებები",
    "19083": "72300000 - მონაცემთა მომსახურება",
    "19084": "72400000 - ინტერნეტმომსახურებები",
    "19072": "72500000 - კომპიუტერთან დაკავშირებული მომსახურებები",
    "19073": "72600000 - კომპიუტერული უზრუნველყოფა და საკონსულტაციო მომსახურებები",
    "19074": "72700000 - კომპიუტერული ქსელის მომსახურება",
    "19075": "72800000 - კომპიუტერის შემოწმება და ტესტირება",
    "19076": "72900000 - კომპიუტერის მონაცემების სარეზერვო დუბლირება",
}

BASE_URL = "https://tenders.procurement.gov.ge/public"
CONTROLLER = f"{BASE_URL}/library/controller.php"


def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ka,en-US;q=0.9,en;q=0.8",
    })
    session.get(f"{BASE_URL}/?go=", timeout=30).raise_for_status()
    return session


def search_tenders(session, basecode: str) -> list[dict]:
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
        "app_type": "0",
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
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{BASE_URL}/?go=",
        "Origin": "https://tenders.procurement.gov.ge",
    }

    r = session.post(CONTROLLER, data=payload, headers=headers, timeout=30)
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

    with create_session() as session:
        run_monitor(session, search_tenders, IT_BASECODES)


if __name__ == "__main__":
    main()