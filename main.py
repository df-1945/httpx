from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
import time
from enum import Enum
import psutil
from typing import List, Dict, Optional

app = FastAPI()


origins = [
    "https://kikisan.pages.dev",
    "https://kikisan.site",
    "https://www.kikisan.site",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Status(str, Enum):
    def __str__(self):
        return str(self.value)

    BARU = "baru"
    LAMA = "lama"


class Hasil(BaseModel):
    keyword: str
    pages: int
    status: Status
    upload: str
    download: str
    time: float
    cpu_max_percent: Optional[float] = None
    ram_max_percent: Optional[float] = None
    jumlah: int
    hasil: Optional[List[Dict]] = None


class DataRequest(BaseModel):
    keyword: str
    pages: int


data_httpx = []


@app.post("/httpx")
def input_httpx(request: Request, input: DataRequest):
    try:
        sent_bytes_start, received_bytes_start = get_network_usage()

        base_url = "https://www.tokopedia.com/search"
        headers = {"User-Agent": request.headers.get("User-Agent")}

        # process = psutil.Process()  # Mendapatkan objek proses saat ini
        # cpu_percent_max = 0  # Penggunaan CPU tertinggi selama eksekusi
        # ram_percent_max = 0  # Penggunaan RAM tertinggi selama eksekusi

        start_time = time.time()
        hasil = main(base_url, headers, input.keyword, input.pages)
        end_time = time.time()

        # Mengukur penggunaan CPU dan RAM selama eksekusi
        # interval = 0.1  # Interval pemantauan (detik)
        # duration = end_time - start_time  # Durasi eksekusi (detik)
        # num_intervals = int(duration / interval) + 1

        # for _ in range(num_intervals):
        #     cpu_percent = psutil.cpu_percent(interval=interval)
        #     print("cpu", cpu_percent)
        #     ram_percent = psutil.virtual_memory().percent
        #     print("ram", ram_percent)

        #     if cpu_percent > cpu_percent_max:
        #         cpu_percent_max = cpu_percent

        #     if ram_percent > ram_percent_max:
        #         ram_percent_max = ram_percent

        sent_bytes_end, received_bytes_end = get_network_usage()

        sent_bytes_total = sent_bytes_end - sent_bytes_start
        received_bytes_total = received_bytes_end - received_bytes_start

        print("Total Penggunaan Internet:")
        print("Upload:", format_bytes(sent_bytes_total))
        print("Download:", format_bytes(received_bytes_total))
        # print("cpu", cpu_percent_max)
        # print("ram", ram_percent_max)

        print(
            f"Berhasil mengambil {len(hasil)} produk dalam {end_time - start_time} detik."
        )
        data = {
            "keyword": input.keyword,
            "pages": input.pages,
            "status": "baru",
            "upload": format_bytes(sent_bytes_total),
            "download": format_bytes(received_bytes_total),
            "time": end_time - start_time,
            # "cpu_max_percent": cpu_percent_max,
            # "ram_max_percent": ram_percent_max,
            "jumlah": len(hasil),
            "hasil": hasil,
        }
        data_httpx.append(data)
        return data_httpx
    except Exception as e:
        return e


def main(base_url, headers, keyword, pages):
    product_soup = []
    with httpx.Client() as session:
        for page in range(1, pages + 1):
            soup_produk = scrape(base_url, headers, keyword, page, session)
            product_soup.extend(soup_produk)

        results = []
        for soup in product_soup:
            href = soup.find("a")["href"]
            link_parts = href.split("r=")
            r_part = link_parts[-1]
            link_part = r_part.split("&")
            r_part = link_part[0]
            new_link = f"{r_part.replace('%3A', ':').replace('%2F', '/')}"
            new_link = new_link.split("%3FextParam")[0]
            new_link = new_link.split("%3Fsrc")[0]
            new_link = new_link.split("?extParam")[0]
            result = {}
            result.update(data_product(soup, new_link, session, headers))
            result.update(
                data_shop("/".join(new_link.split("/")[:-1]), session, headers)
            )
            results.append(result)
        return results


def scrape(base_url, headers, keyword, page, session):
    params = {"q": keyword, "page": page}
    try_count = 0
    while try_count < 5:
        try:
            response = session.get(
                base_url, headers=headers, params=params, timeout=1800000
            )
            response.raise_for_status()
            soup_produk = []
            soup = BeautifulSoup(response.content, "html.parser")
            products_data = soup.find_all("div", {"class": "css-llwpbs"})
            for i in products_data:
                if i.find("a", {"class": "pcv3__info-content css-gwkf0u"}) is not None:
                    soup_produk.append(i)
            print(f"Berhasil scrape data dari halaman {page}.")
            return soup_produk
        except (httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError):
            try_count += 1
            print(f"Koneksi ke halaman {page} timeout. Mencoba lagi...")
    else:
        print(
            f"Gagal melakukan koneksi ke halaman {page} setelah mencoba beberapa kali."
        )
        return []


def data_product(soup_produk, product_link, session, headers):
    try_count = 0
    while try_count < 5:
        try:
            response = session.get(product_link, headers=headers, timeout=1800000)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            data_to_scrape = {
                "link_product": "",
                "product_name": ("h1", {"class": "css-1os9jjn"}),
                "product_price": ("div", {"class": "price"}),
                "product_terjual": (
                    "span",
                    {"class": "prd_label-integrity css-1duhs3e"},
                ),
                "product_rating": (
                    "span",
                    {"class": "prd_rating-average-text css-t70v7i"},
                ),
                "product_diskon": (
                    "div",
                    {"class": "prd_badge-product-discount css-1qtulwh"},
                ),
                "price_ori": (
                    "div",
                    {"class": "prd_label-product-slash-price css-1u1z2kp"},
                ),
                "product_items": ("div", {"class": "css-1b2d3hk"}),
                "product_detail": ("li", {"class": "css-bwcbiv"}),
                "product_keterangan": ("span", {"class": "css-168ydy0 eytdjj01"}),
            }

            results = {}

            for key, value in data_to_scrape.items():
                if key == "product_detail":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    results[key] = [element.text.strip() for element in elements]
                elif key == "product_items":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    if elements:
                        for key_element in elements:
                            items = key_element.find_all(
                                "div", {"class": "css-1y1bj62"}
                            )
                            kunci = (
                                key_element.find(
                                    "p", {"class": "css-x7tz35-unf-heading e1qvo2ff8"}
                                )
                                .text.strip()
                                .split(":")[0]
                            )
                            results[kunci] = [
                                item.text.strip()
                                for item in items
                                if item.text.strip()
                                != ".css-1y1bj62{padding:4px 2px;display:-webkit-inline-box;display:-webkit-inline-flex;display:-ms-inline-flexbox;display:inline-flex;}"
                            ]
                    else:
                        results[key] = None
                elif key == "link_product":
                    results[key] = product_link
                elif (
                    key == "product_terjual"
                    or key == "product_rating"
                    or key == "product_diskon"
                    or key == "price_ori"
                ):
                    tag, attrs = value
                    element = soup_produk.find(tag, attrs)
                    if element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
                else:
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    if element:
                        text = element.get_text(
                            separator="<br>"
                        )  # Gunakan separator '\n' untuk menambahkan baris baru
                        results[key] = text.strip()
                    else:
                        results[key] = None
            print(f"Berhasil scrape data produk dari halaman {product_link}.")
            return results

        except (httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError):
            try_count += 1
            print(f"Koneksi ke halaman {product_link} timeout. Mencoba lagi...")
    else:
        print(
            f"Gagal melakukan koneksi ke halaman {product_link} setelah mencoba beberapa kali."
        )
        return None


def data_shop(shop_link, session, headers):
    try_count = 0
    while try_count < 5:
        try:
            response = session.get(shop_link, headers=headers, timeout=1800000)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            data_to_scrape = {
                "link_shop": "",
                "shop_name": ("h1", {"class": "css-1g675hl"}),
                "shop_status": ("span", {"data-testid": "shopSellerStatusHeader"}),
                "shop_location": ("span", {"data-testid": "shopLocationHeader"}),
                "shop_info": ("div", {"class": "css-6x4cyu e1wfhb0y1"}),
            }

            results = {}

            for key, value in data_to_scrape.items():
                if key == "link_shop":
                    results[key] = shop_link
                elif key == "shop_status":
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    time = soup.find("strong", {"class": "time"})
                    if time:
                        waktu = time.text.strip()
                        status = element.text.strip()
                        results[key] = status + " " + waktu
                    elif element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
                elif key == "shop_info":
                    tag, attrs = value
                    elements = soup.find_all(tag, attrs)
                    key = ["rating_toko", "respon_toko", "open_toko"]
                    ket = soup.find_all(
                        "p", {"class": "css-1dzsr7-unf-heading e1qvo2ff8"}
                    )
                    i = 0
                    for item, keterangan in zip(elements, ket):
                        if item and keterangan:
                            results[key[i]] = (
                                item.text.replace("\u00b1", "").strip()
                                + " "
                                + keterangan.text.strip()
                            )
                        else:
                            results[key[i]] = None
                        i += 1
                else:
                    tag, attrs = value
                    element = soup.find(tag, attrs)
                    if element:
                        results[key] = element.text.strip()
                    else:
                        results[key] = None
            print(f"Berhasil scrape data toko dari halaman {shop_link}.")
            return results

        except (httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError):
            try_count += 1
            print(f"Koneksi ke halaman {shop_link} timeout. Mencoba lagi...")
    else:
        print(
            f"Gagal melakukan koneksi ke halaman {shop_link} setelah mencoba beberapa kali."
        )
        return None


def get_network_usage():
    network_stats = psutil.net_io_counters()
    sent_bytes = network_stats.bytes_sent
    received_bytes = network_stats.bytes_recv

    return sent_bytes, received_bytes


def format_bytes(bytes):
    # Fungsi ini mengubah ukuran byte menjadi format yang lebih mudah dibaca
    sizes = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while bytes >= 1024 and i < len(sizes) - 1:
        bytes /= 1024
        i += 1
    return "{:.2f} {}".format(bytes, sizes[i])


@app.get("/data")
def ambil_data(
    keyword: Optional[str] = None,
    pages: Optional[int] = None,
    status: Optional[Status] = None,
):
    if status is not None or keyword is not None or pages is not None:
        result_filter = []
        for data in data_httpx:
            data = Hasil.parse_obj(data)
            if (
                status == data.status
                and data.keyword == keyword
                and data.pages == pages
            ):
                result_filter.append(data)
    else:
        result_filter = data_httpx
    return result_filter


@app.put("/monitoring")
def ambil_data(input: DataRequest):
    for data in data_httpx:
        if (
            data["status"] == "baru"
            and data["keyword"] == input.keyword
            and data["pages"] == input.pages
        ):
            cpu_percent_max = 0  # Highest CPU usage during execution
            ram_percent_max = 0  # Highest RAM usage during execution

            interval = 0.1  # Interval for monitoring (seconds)
            duration = data["time"]
            num_intervals = int(duration / interval) + 1

            for _ in range(num_intervals):
                cpu_percent = psutil.cpu_percent(interval=interval)
                print("cpu", cpu_percent)
                ram_percent = psutil.virtual_memory().percent
                print("ram", ram_percent)

                if cpu_percent > cpu_percent_max:
                    cpu_percent_max = cpu_percent

                if ram_percent > ram_percent_max:
                    ram_percent_max = ram_percent

            data["cpu_max_percent"] = cpu_percent_max
            data["ram_max_percent"] = ram_percent_max
            data["status"] = "lama"

        else:
            data = None

    return data
