import os
import re
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urljoin


BASE_URL = "https://cafef.vn"

PAGES = {
    "Kinh tế vĩ mô - Đầu tư": "https://cafef.vn/vi-mo-dau-tu.chn",
    "Tài chính quốc tế": "https://cafef.vn/tai-chinh-quoc-te.chn",
    "Tin mới nhất": "https://cafef.vn/tin-moi.chn",
    "Đọc nhiều nhất": "https://cafef.vn/"
}


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def fetch_html(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def extract_articles_from_page(url: str, limit: int = 10):
    """
    Lấy danh sách bài viết từ một trang CafeF.
    Code cố gắng bắt các thẻ <a> dẫn tới bài viết .chn.
    """
    soup = fetch_html(url)

    articles = []
    seen_links = set()

    for a in soup.find_all("a", href=True):
        title = clean_text(a.get_text(" ", strip=True))
        href = a["href"]

        if not title:
            continue

        full_url = urljoin(BASE_URL, href)

        # CafeF article thường là link .chn, loại bớt các trang category/list
        if ".chn" not in full_url:
            continue

        excluded = [
            "tin-moi.chn",
            "vi-mo-dau-tu.chn",
            "tai-chinh-quoc-te.chn",
            "thi-truong.chn",
            "du-lieu.chn",
            "song.chn",
            "lifestyle.chn",
            "bat-dong-san.chn",
            "thi-truong-chung-khoan.chn",
        ]

        if any(x in full_url for x in excluded):
            continue

        if full_url in seen_links:
            continue

        # tránh lấy menu quá ngắn
        if len(title) < 20:
            continue

        seen_links.add(full_url)
        articles.append({
            "title": title,
            "url": full_url
        })

        if len(articles) >= limit:
            break

    return articles


def extract_most_read(limit: int = 10):
    """
    Lấy mục Đọc nhiều từ trang chủ hoặc category.
    Vì CafeF có thể đổi class HTML, dùng cách linh hoạt:
    tìm vùng có chữ 'Đọc nhiều', sau đó lấy link bài viết gần đó.
    """
    soup = fetch_html(PAGES["Đọc nhiều nhất"])

    text_blocks = soup.find_all(string=re.compile("Đọc nhiều", re.IGNORECASE))

    candidates = []
    seen = set()

    for text_node in text_blocks:
        parent = text_node.parent

        # leo lên vài cấp để tìm khu vực chứa list đọc nhiều
        for _ in range(5):
            if parent is None:
                break

            links = parent.find_all("a", href=True)

            for a in links:
                title = clean_text(a.get_text(" ", strip=True))
                full_url = urljoin(BASE_URL, a["href"])

                if ".chn" not in full_url:
                    continue
                if len(title) < 20:
                    continue
                if full_url in seen:
                    continue

                seen.add(full_url)
                candidates.append({
                    "title": title,
                    "url": full_url
                })

                if len(candidates) >= limit:
                    return candidates

            parent = parent.parent

    # fallback: nếu không tìm được block Đọc nhiều thì lấy 10 bài từ trang chủ
    if not candidates:
        candidates = extract_articles_from_page(PAGES["Đọc nhiều nhất"], limit=limit)

    return candidates[:limit]


def build_email_html(data: dict) -> str:
    today = datetime.now().strftime("%d/%m/%Y")

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2>Điểm báo CafeF sáng {today}</h2>
        <p>Tổng hợp tự động các mục: Kinh tế vĩ mô - Đầu tư, Tài chính quốc tế, Tin mới nhất và Đọc nhiều nhất.</p>
    """

    for section, articles in data.items():
        html += f"<h3>{section}</h3>"

        if not articles:
            html += "<p><i>Không lấy được dữ liệu cho mục này.</i></p>"
            continue

        html += "<ol>"
        for article in articles:
            html += f"""
            <li>
                <a href="{article['url']}">{article['title']}</a>
            </li>
            """
        html += "</ol>"

    html += """
        <hr>
        <p style="font-size: 12px; color: gray;">
            Email này được gửi tự động bằng Python.
        </p>
    </body>
    </html>
    """

    return html


def send_email(subject: str, html_body: str):
    load_dotenv()

    email_from = os.getenv("EMAIL_FROM")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_to = os.getenv("EMAIL_TO")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not all([email_from, email_password, email_to]):
        raise ValueError("Thiếu EMAIL_FROM, EMAIL_PASSWORD hoặc EMAIL_TO trong file .env")

    message = MIMEMultipart("alternative")
    message["From"] = email_from
    message["To"] = email_to
    message["Subject"] = subject

    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(email_from, email_password)
        server.sendmail(email_from, email_to, message.as_string())


def main():
    data = {
        "5 bài Kinh tế vĩ mô - Đầu tư": extract_articles_from_page(
            PAGES["Kinh tế vĩ mô - Đầu tư"],
            limit=5
        ),
        "5 bài Tài chính quốc tế": extract_articles_from_page(
            PAGES["Tài chính quốc tế"],
            limit=5
        ),
        "10 bài Tin mới nhất": extract_articles_from_page(
            PAGES["Tin mới nhất"],
            limit=10
        ),
        "10 bài Đọc nhiều nhất": extract_most_read(
            limit=10
        )
    }

    today = datetime.now().strftime("%d/%m/%Y")
    subject = f"Điểm báo CafeF sáng {today}"

    html_body = build_email_html(data)
    send_email(subject, html_body)

    print("Đã gửi email điểm báo CafeF thành công.")


if __name__ == "__main__":
    main()