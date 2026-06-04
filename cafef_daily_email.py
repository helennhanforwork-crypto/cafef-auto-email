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


def extract_article_summary(article_url: str) -> str:
    """
    Mở từng bài CafeF để lấy sapo/mô tả ngắn.
    Nếu không lấy được thì trả về chuỗi rỗng.
    """
    try:
        soup = fetch_html(article_url)

        # Cách 1: lấy meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return clean_text(meta_desc.get("content"))[:280]

        # Cách 2: lấy og:description
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc and og_desc.get("content"):
            return clean_text(og_desc.get("content"))[:280]

        # Cách 3: fallback lấy đoạn văn đầu tiên đủ dài
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            text = clean_text(p.get_text(" ", strip=True))
            if len(text) > 80:
                return text[:280]

    except Exception:
        return ""

    return ""
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

        summary = extract_article_summary(full_url)

        articles.append({
            "title": title,
             "url": full_url,
             "summary": summary
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
                summary = extract_article_summary(full_url)

                candidates.append({
                    "title": title,
                    "url": full_url,
                    "summary": summary
                })
                if len(candidates) >= limit:
                    return candidates

            parent = parent.parent

    # fallback: nếu không tìm được block Đọc nhiều thì lấy 10 bài từ trang chủ
    if not candidates:
        candidates = extract_articles_from_page(PAGES["Đọc nhiều nhất"], limit=limit)

    return candidates[:limit]


from datetime import datetime

def build_email_html(data: dict) -> str:
    today = datetime.now().strftime("%d/%m/%Y")
    
    section_icons = {
        "5 bài Kinh tế vĩ mô - Đầu tư": "📊",
        "5 bài Tài chính quốc tế": "🌐",
        "10 bài Tin mới nhất": "⚡",
        "10 bài Đọc nhiều nhất": "⭐",
    }

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="
        margin: 0;
        padding: 0;
        background-color: #F3F4F6;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #1F2937;
        -webkit-font-smoothing: antialiased;
    ">
        <div style="
            max-width: 600px;
            margin: 0 auto;
            padding: 30px 15px;
        ">
            <div style="
                background-color: #0F172A;
                border-radius: 12px 12px 0 0;
                padding: 35px 30px;
                text-align: left;
            ">
                <div style="
                    font-size: 12px;
                    font-weight: 600;
                    letter-spacing: 1.5px;
                    text-transform: uppercase;
                    color: #94A3B8;
                    margin-bottom: 10px;
                ">
                    CafeF Daily Briefing • {today}
                </div>
                <h1 style="
                    margin: 0;
                    font-size: 26px;
                    line-height: 1.3;
                    color: #FFFFFF;
                    font-weight: 700;
                ">
                    Điểm báo Tài chính
                </h1>
            </div>

            <div style="
                background-color: #FFFFFF;
                padding: 25px 30px;
                border-left: 1px solid #E5E7EB;
                border-right: 1px solid #E5E7EB;
            ">
                <p style="
                    margin: 0;
                    font-size: 15px;
                    color: #4B5563;
                    line-height: 1.6;
                ">
                    <strong>Chào Hạnh Nhân,</strong><br><br>
                    Dưới đây là các tin tức vĩ mô, biến động thị trường và tài chính quốc tế đáng chú ý nhất được tổng hợp từ CafeF sáng nay.
                </p>
            </div>
    """

    for section, articles in data.items():
        icon = section_icons.get(section, "📌")

        html += f"""
            <div style="
                background-color: #FFFFFF;
                padding: 0 30px 20px 30px;
                border-left: 1px solid #E5E7EB;
                border-right: 1px solid #E5E7EB;
            ">
                <div style="
                    border-bottom: 2px solid #F3F4F6;
                    padding-bottom: 10px;
                    margin-bottom: 20px;
                    margin-top: 15px;
                ">
                    <h2 style="
                        margin: 0;
                        font-size: 17px;
                        color: #111827;
                        font-weight: 700;
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                    ">
                        {icon} {section}
                    </h2>
                </div>
        """

        if not articles:
            html += """
                <p style="font-size: 14px; color: #9CA3AF; font-style: italic; margin: 0;">
                    Không có bản tin nào trong mục này sáng nay.
                </p>
            """
        else:
            html += '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse: collapse;">'
            
            for idx, article in enumerate(articles, start=1):
                idx_str = f"{idx:02d}" 
                
                # CẬP NHẬT: Thêm phần summary vào ngay dưới title
                html += f"""
                    <tr>
                        <td valign="top" style="
                            width: 32px;
                            padding-bottom: 22px; /* Tăng khoảng cách giữa các bài một chút */
                            padding-top: 2px;
                        ">
                            <span style="
                                font-size: 14px;
                                font-weight: 700;
                                color: #CBD5E1;
                            ">{idx_str}.</span>
                        </td>
                        <td valign="top" style="padding-bottom: 22px;">
                            <a href="{article['url']}" target="_blank" style="
                                color: #1F2937;
                                text-decoration: none;
                                font-size: 15px;
                                font-weight: 600;
                                line-height: 1.5;
                                display: block;
                                margin-bottom: 6px; /* Khoảng cách giữa tiêu đề và tóm tắt */
                            ">
                                {article['title']}
                            </a>
                            <p style="
                                margin: 0;
                                color: #6B7280; /* Màu xám nhạt hơn tiêu đề để tạo phân cấp thị giác */
                                font-size: 13.5px;
                                line-height: 1.5;
                            ">
                                {article.get('summary', 'Chưa có mô tả ngắn cho bài này.')}
                            </p>
                        </td>
                    </tr>
                """
            html += '</table>'

        html += """
            </div>
        """

    html += """
            <div style="
                background-color: #F8FAFC;
                border: 1px solid #E5E7EB;
                border-top: none;
                border-radius: 0 0 12px 12px;
                padding: 20px 30px;
                text-align: center;
            ">
                <p style="
                    margin: 0;
                    color: #94A3B8;
                    font-size: 12px;
                    line-height: 1.6;
                ">
                    Chúc bạn một ngày tốt lành <br>
                    Data source: CafeF.vn
                </p>
            </div>
        </div>
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
        raise ValueError("Thiếu EMAIL_FROM, EMAIL_PASSWORD hoặc EMAIL_TO")

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
    subject = f"Điểm báo CafeF - {today}"

    html_body = build_email_html(data)
    send_email(subject, html_body)

    print("Đã gửi email điểm báo CafeF thành công.")


if __name__ == "__main__":
    main()
