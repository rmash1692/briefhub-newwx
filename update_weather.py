import requests
from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from pdf2image import convert_from_path
import shutil
import os
from PIL import Image

# --- PDF編集用ライブラリ ---
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from email.utils import parsedate_to_datetime # HTTPヘッダーの日付解析用

# -----------------------------------
# 1. 保存先フォルダの定義
# -----------------------------------
dest_folder_path = "images"
os.makedirs(dest_folder_path, exist_ok=True)
print(f"Destination folder: {dest_folder_path}")

layer_folder_path = "layer"

# -----------------------------------
# PDFにレイヤー画像を合成する関数
# -----------------------------------
def overlay_japan_map(pdf_path, overlay_image_name):
    overlay_png_path = os.path.join(layer_folder_path, overlay_image_name)

    if not os.path.exists(pdf_path):
        return pdf_path
    if not os.path.exists(overlay_png_path):
        print(f"警告: レイヤー画像なし ({overlay_png_path}) -> 合成スキップ")
        return pdf_path

    print(f"カラー合成処理開始: {pdf_path} + {overlay_image_name}")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)

            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(width, height))
            can.drawImage(ImageReader(overlay_png_path), 0, 0, width=width, height=height, mask="auto")
            can.save()
            packet.seek(0)
            
            overlay_pdf = PdfReader(packet)
            page.merge_page(overlay_pdf.pages[0])
            writer.add_page(page)

        output_file = pdf_path.replace(".pdf", "_COLOR.pdf")
        with open(output_file, "wb") as f:
            writer.write(f)
        
        print(f"レイヤー合成完了: {output_file}")
        return output_file

    except Exception as e:
        print(f"合成エラー: {e} -> 元ファイルを使用します")
        return pdf_path

# -----------------------------------
# 2. PDF/画像 ダウンロード関数群
# -----------------------------------
def download_asas_pdf(target_time):
    yyyymm = target_time.strftime("%Y%m")
    yyyymmddhhmm = target_time.strftime("%Y%m%d%H%M")
    url = f"https://www.data.jma.go.jp/yoho/data/wxchart/quick/{yyyymm}/ASAS_COLOR_{yyyymmddhhmm}.pdf"
    filename = f"ASAS_{yyyymmddhhmm}.pdf"
    r = requests.get(url)
    if r.status_code == 200:
        with open(filename, "wb") as f:
            f.write(r.content)
        return filename
    return None

def download_fsas_pdf():
    url = "https://www.data.jma.go.jp/yoho/data/wxchart/quick/FSAS24_COLOR_ASIA.pdf"
    filename = "FSAS24_COLOR_ASIA.pdf"
    r = requests.get(url)
    if r.status_code == 200:
        with open(filename, "wb") as f:
            f.write(r.content)
        return filename
    return None

def download_jma_nwpmap_pdf(chart_type, target_time):
    hh = target_time.strftime("%H")
    url = f"https://www.jma.go.jp/bosai/numericmap/data/nwpmap/{chart_type}_{hh}.pdf"
    filename = f"{chart_type.upper()}_{target_time.strftime('%Y%m%d%H%M')}.pdf"
    r = requests.get(url)
    if r.status_code == 200:
        with open(filename, "wb") as f:
            f.write(r.content)
        return filename
    return None

def download_jma_png(url, chart_type_name):
    local_filename = f"{chart_type_name}.png"
    r = requests.get(url)
    if r.status_code == 200:
        with open(local_filename, "wb") as f:
            f.write(r.content)
        return local_filename
    return None

def download_jma_ashfall_pdf(chart_id, target_time_jst):
    target_time_utc = target_time_jst.astimezone(UTC)
    yyyymmddhhmm = target_time_utc.strftime("%Y%m%d%H%M")
    url = f"https://www.jma.go.jp/bosai/volcano/data/ashfall/pdf/Z__C_RJTD_{yyyymmddhhmm}00_EQV_CHT_JCIashfallr_{chart_id}_N1_image.pdf"
    filename = f"ASHFALL_{chart_id}_{yyyymmddhhmm}.pdf"
    r = requests.get(url)
    if r.status_code == 200:
        with open(filename, "wb") as f:
            f.write(r.content)
        if os.path.getsize(filename) < 10240:
            os.remove(filename)
            return None
        return filename
    return None

# -----------------------------------
# 3. 取得ロジック関数群
# -----------------------------------
def get_latest_two_pdfs():
    now_utc = datetime.now(UTC)
    hours = [0, 6, 12, 18]
    for i in range(2):
        day = now_utc - timedelta(days=i)
        candidate_hours = hours[::-1]
        for h in candidate_hours:
            target_time = day.replace(hour=h, minute=0, second=0, microsecond=0)
            latest_pdf = download_asas_pdf(target_time)
            if latest_pdf:
                idx = candidate_hours.index(h)
                if idx + 1 < len(candidate_hours):
                    prev_time = day.replace(hour=candidate_hours[idx + 1], minute=0, second=0, microsecond=0)
                else:
                    prev_day = day - timedelta(days=1)
                    prev_time = prev_day.replace(hour=18, minute=0, second=0, microsecond=0)
                prev_pdf = download_asas_pdf(prev_time)
                return latest_pdf, prev_pdf
    return None, None

def get_latest_jma_nwpmap_pdf(chart_type):
    now_utc = datetime.now(UTC)
    hours_nwpmap = [0, 12]
    for i in range(2):
        day = now_utc - timedelta(days=i)
        for h in sorted(hours_nwpmap, key=lambda x: abs(now_utc.hour - x)):
            target_time = day.replace(hour=h, minute=0, second=0, microsecond=0)
            if target_time > now_utc: continue
            pdf_file = download_jma_nwpmap_pdf(chart_type, target_time)
            if pdf_file: return pdf_file
    return None

def get_latest_jma_ashfall_pdf_stable(volcano_name, volcano_code):
    ash_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    now_utc = datetime.now(timezone.utc)
    candidates = [h for h in ash_hours if h <= now_utc.hour]
    if candidates:
        base_hour = max(candidates)
        base_day = now_utc
    else:
        base_hour = ash_hours[-1]
        base_day = now_utc - timedelta(days=1)
    idx = ash_hours.index(base_hour)
    candidate_hours = [ash_hours[(idx - i) % len(ash_hours)] for i in range(len(ash_hours))]
    for i in range(2):
        day = base_day - timedelta(days=i)
        for hh in candidate_hours:
            ash_time = day.replace(hour=hh, minute=0, second=0, microsecond=0)
            ts = ash_time.strftime("%Y%m%d%H%M%S")
            url = f"https://www.jma.go.jp/bosai/volcano/data/ashfall/pdf/Z__C_RJTD_{ts}_EQV_CHT_JCIashfallr_{volcano_code}_N1_image.pdf"
            filename = f"ASHFALL_{volcano_name}_{ts}.pdf"
            r = requests.get(url)
            if r.status_code == 200 and len(r.content) > 10240:
                with open(filename, "wb") as f:
                    f.write(r.content)
                return filename
    return None

def download_fxjp106_checked():
    now_utc = datetime.now(timezone.utc)
    base_hour = (now_utc.hour // 3) * 3
    for i in range(4):
        target_h = (base_hour - (i * 3)) % 24
        h_str = f"{target_h:02d}"
        url = f"https://www.data.jma.go.jp/airinfo/data/pict/nwp/fxjp106_{h_str}.png"
        filename = f"FXJP106_temp_{h_str}.png"
        try:
            head_req = requests.head(url, timeout=10)
            if head_req.status_code == 200:
                last_modified_str = head_req.headers.get('Last-Modified')
                if last_modified_str:
                    last_modified_dt = parsedate_to_datetime(last_modified_str)
                    time_diff = now_utc - last_modified_dt
                    if time_diff > timedelta(hours=12):
                        continue
                    r = requests.get(url, timeout=20)
                    if r.status_code == 200:
                        with open(filename, "wb") as f:
                            f.write(r.content)
                        return filename
                else:
                    continue
            else:
                continue
        except Exception as e:
            continue
    return None

# -----------------------------------
# 4. 保存・アップロード用関数
# -----------------------------------
def pdf_to_png_and_upload(pdf_file, final_drive_name):
    if pdf_file and os.path.exists(pdf_file):
        png_filename_local = pdf_file.replace(".pdf", ".png")
        pages = convert_from_path(pdf_file, dpi=200)
        pages[0].save(png_filename_local, "PNG")

        shutil.copy(png_filename_local, os.path.join(dest_folder_path, final_drive_name))
        print(f"Copied {png_filename_local} to {os.path.join(dest_folder_path, final_drive_name)}")
        os.remove(png_filename_local)
        return True
    return False

def direct_png_upload(local_png_file, final_drive_name):
    if local_png_file and os.path.exists(local_png_file):
        shutil.copy(local_png_file, os.path.join(dest_folder_path, final_drive_name))
        print(f"Copied {local_png_file} to {os.path.join(dest_folder_path, final_drive_name)}")
        os.remove(local_png_file)
        return True
    return False

# -----------------------------------
# 5. メイン実行ブロック
# -----------------------------------

# --- ASAS / FSAS (合成不要) ---
latest_asas_pdf_local, prev_asas_pdf_local = get_latest_two_pdfs()
pdf_to_png_and_upload(latest_asas_pdf_local, "ASAS_Latest.png")
pdf_to_png_and_upload(prev_asas_pdf_local, "ASAS_Prior.png")
if latest_asas_pdf_local and os.path.exists(latest_asas_pdf_local): os.remove(latest_asas_pdf_local)
if prev_asas_pdf_local and os.path.exists(prev_asas_pdf_local): os.remove(prev_asas_pdf_local)

fsas_pdf_local = download_fsas_pdf()
if fsas_pdf_local:
    pdf_to_png_and_upload(fsas_pdf_local, "FSAS_Latest.png")
    if os.path.exists(fsas_pdf_local): os.remove(fsas_pdf_local)

# --- AUPQ / FXFE / FXJP (合成対象) ---
charts_to_process = [
    ('aupq35', 'japan_overlay_aupq.png', 'AUPQ35_Latest.png'),
    ('aupq78', 'japan_overlay_aupq.png', 'AUPQ78_Latest.png'),
    ('fxfe502', 'japan_overlay_fxfe.png', 'FXFE502_Latest.png'),
    ('fxfe5782', 'japan_overlay_fxfe.png', 'FXFE5782_Latest.png'),
    ('fxjp854', 'japan_overlay_fxjp.png', 'FXJP854_Latest.png')
]

for code, overlay, out_name in charts_to_process:
    raw_pdf = get_latest_jma_nwpmap_pdf(code)
    if raw_pdf:
        color_pdf = overlay_japan_map(raw_pdf, overlay)
        pdf_to_png_and_upload(color_pdf, out_name)
        if os.path.exists(raw_pdf): os.remove(raw_pdf)
        if color_pdf != raw_pdf and os.path.exists(color_pdf): os.remove(color_pdf)

# --- FXJP106 / FBJP ---
fxjp106_png = download_fxjp106_checked()
if fxjp106_png: direct_png_upload(fxjp106_png, "FXJP106_Latest.png")

fbjp_png = download_jma_png("https://www.data.jma.go.jp/airinfo/data/pict/fbjp/fbjp.png", "FBJP_Latest")
if fbjp_png: direct_png_upload(fbjp_png, "FBJP_Latest.png")

# ---------------------------------------------------------
# 新機能: 全国分の FBOS (SIGWX) を網羅してダウンロード
# ---------------------------------------------------------
fbos_regions = {
    "01": "Hokkaido",
    "02": "Tohoku",
    "03": "East",
    "04": "West",
    "05": "Okinawa",
    "06": "Amami",
    "39": "West_Kyushu"
}
for code, name in fbos_regions.items():
    url = f"https://www.data.jma.go.jp/airinfo/data/pict/low-level_sigwx/fbos{code}.png"
    png = download_jma_png(url, f"temp_fbos_{code}")
    if png:
        direct_png_upload(png, f"FBOS_{name}_Latest.png")

# --- 降灰予報図 (合成不要) ---
ash_volcanoes = [
    ("Sakurajima", "JR506X"),
    ("Kirishimayama", "JR551X")
]
for name, code in ash_volcanoes:
    pdf_file = get_latest_jma_ashfall_pdf_stable(name, code)
    if pdf_file:
        pdf_to_png_and_upload(pdf_file, f"Ashfall_{name}_Latest.png")
        os.remove(pdf_file)

# -----------------------------------
# 6. 【変更】共通画像のPDF化 (Common_Briefing.pdf)
# 個別空港情報(QMC等)は含めず、全国共通の画像のみを結合
# -----------------------------------
def create_common_pdf(image_folder):
    # 全国で共通して使用する画像リスト
    target_images = [
        "ASAS_Prior.png", "ASAS_Latest.png", "FSAS_Latest.png",
        "AUPQ35_Latest.png", "AUPQ78_Latest.png",
        "FXFE502_Latest.png", "FXFE5782_Latest.png",
        "FXJP854_Latest.png", "FXJP106_Latest.png",
        "FBJP_Latest.png"
    ]

    A4_PORTRAIT_PX = (2480, 3508)
    A4_LANDSCAPE_PX = (3508, 2480)
    pdf_pages = []
    print("--- 共通PDF (Common_Briefing.pdf) の作成開始 ---")

    for img_name in target_images:
        img_path = os.path.join(image_folder, img_name)
        if os.path.exists(img_path):
            try:
                img = Image.open(img_path).convert("RGB")
                w, h = img.size
                page_size = A4_LANDSCAPE_PX if w >= h else A4_PORTRAIT_PX
                img_ratio = w / h
                page_ratio = page_size[0] / page_size[1]

                if img_ratio > page_ratio:
                    new_w = page_size[0]
                    new_h = int(new_w / img_ratio)
                else:
                    new_h = page_size[1]
                    new_w = int(new_h * img_ratio)

                resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", page_size, (255, 255, 255))
                offset = ((page_size[0] - new_w) // 2, (page_size[1] - new_h) // 2)
                canvas.paste(resized_img, offset)
                
                pdf_pages.append(canvas)
            except Exception as e:
                print(f"エラー: {img_name} -> {e}")

    if pdf_pages:
        output_path = os.path.join(image_folder, "Common_Briefing.pdf")
        pdf_pages[0].save(
            output_path, 
            save_all=True, 
            append_images=pdf_pages[1:],
            resolution=300.0,
            quality=85,
            subsampling=0,
            optimize=True
        )
        print(f"共通PDF作成完了: {output_path}")
    else:
        print("作成対象の共通画像が見つかりませんでした。")

# 実行
create_common_pdf(dest_folder_path)
