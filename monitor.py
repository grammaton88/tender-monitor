import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import time

# ================== Environment Variables (Secrets) ==================
EMAIL_TO = os.environ.get("EMAIL_TO", "kakabadzemisha@gmail.com")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

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
    session.get(f"{BASE_URL}/?go=", timeout=30)
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

    try:
        r = session.post(CONTROLLER, data=payload, headers=headers, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
    except Exception as e:
        print(f"Request error {basecode}: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
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
        except Exception:
            continue

    return results


def send_email(tenders: list[dict]):
    if not tenders:
        print("No tenders found — email not sent")
        return

    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("EMAIL_FROM or EMAIL_PASSWORD missing")
        return

    subject = f"[ტენდერის შეტყობინება] {len(tenders)} აქტიური IT ტენდერი – {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    body_lines = [
        "საიტზე tenders.procurement.gov.ge აღმოჩენილია აქტიური IT ტენდერები (სტატუსი: გამოცხადებულია):\n",
        "=" * 60,
    ]

    for i, t in enumerate(tenders, 1):
        body_lines.extend([
            f"\n#{i}",
            f"განცხადების ნომერი : {t['reg_num']}",
            f"სტატუსი            : {t['status']}",
            f"შემსყიდველი         : {t['buyer']}",
            f"კატეგორია          : {t['category']}",
            f"სავარაუდო ღირებულება: {t['amount']}",
            f"გამოცხადების თარიღი : {t['announce_date']}",
            f"წინადადებების ვადა  : {t['deadline']}",
            f"ბმული              : {t['link']}",
            "-" * 50,
        ])

    body_lines.append("\nეს არის ავტომატური შეტყობინება (GitHub Actions).")
    body = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"✅ Email sent successfully with {len(tenders)} tenders")
    except Exception as e:
        print(f"❌ Email failed: {e}")


def main():
    print("=" * 60)
    print("Starting IT Tender Monitor")
    print("=" * 60)

    session = create_session()
    all_tenders = []

    for basecode, desc in IT_BASECODES.items():
        print(f"Searching: {basecode} → {desc}")
        found = search_tenders(session, basecode)
        print(f"  → Found {len(found)}")
        all_tenders.extend(found)
        time.sleep(1.3)

    # უნიკალური ტენდერები
    unique = {}
    for t in all_tenders:
        if t["id"]:
            unique[t["id"]] = t
    tenders = list(unique.values())

    print(f"\nTotal unique active IT tenders: {len(tenders)}")
    send_email(tenders)


if __name__ == "__main__":
    main()