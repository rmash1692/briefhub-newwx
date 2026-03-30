import os
import requests
import shutil
from datetime import datetime, timedelta, timezone
from PIL import Image
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# 設定
UTC = timezone.utc
DEST_FOLDER = "images"
LAYER_FOLDER = "layer" # 透過レイヤー画像(PNG)を入れておくフォルダ
os.makedirs(DEST_FOLDER, exist_ok=True)

# -----------------------------------
# ユーティリティ関数
# -----------------------------------
def download_file(url, filename):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            with open(filename, "wb") as f:
                f.write(r.content)
            return filename
    except:
        pass
    return None

def overlay_map(pdf_path, layer_name):
    overlay_path = os.path.join(LAYER_FOLDER, layer_name)
    if not os.path.exists(pdf_path) or not os.path.exists(overlay_path):
        return pdf_path
    
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for page in reader.pages:
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=(page.mediabox.width, page.mediabox.height))
        can.drawImage(ImageReader(overlay_path), 0, 0, width=float(page.mediabox.width), height=float(page.mediabox.height), mask="auto")
        can.save()
        packet.seek(0)
        page.merge_page(PdfReader(packet).pages[0])
        writer.add_page(page)
    
    out_path = pdf_path.replace(".pdf", "_COLOR.pdf")
    with open(out_path, "wb") as f:
        writer.write(f)
    return out_path

# -----------------------------------
# メイン処理: 共通PDFの作成
# -----------------------------------
def create_common_pdf():
    print("--- 共通PDFの作成開始 ---")
    pdf_list = []
    
    # 1. ASAS (最新と1つ前)
    now = datetime.now(UTC)
    for i in range(2):
        target = (now - timedelta(hours=i*6)).replace(minute=0, second=0, microsecond=0)
        # 実際にはJMAの更新タイミングに合わせたループが必要ですが、ここでは簡略化
        url = f"https://www.data.jma.go.jp/yoho/data/wxchart/quick/{target.strftime('%Y%m')}/ASAS_COLOR_{target.strftime('%Y%m%d%H%M')}.pdf"
        f = download_file(url, f"temp_asas_{i}.pdf")
        if f: pdf_list.append(f)

    # 2. AUPQ / FXFE (合成あり)
    charts = [('aupq35', 'japan_overlay_aupq.png'), ('fxfe502', 'japan_overlay_fxfe.png')]
    for code, layer in charts:
        raw_pdf = download_file(f"https://www.jma.go.jp/bosai/numericmap/data/nwpmap/{code}_00.pdf", f"temp_{code}.pdf")
        if raw_pdf:
            color_pdf = overlay_map(raw_pdf, layer)
            pdf_list.append(color_pdf)

    # まとめて1つのPDFにする
    if pdf_list:
        writer = PdfWriter()
        for p in pdf_list:
            reader = PdfReader(p)
            for page in reader.pages:
                writer.add_page(page)
        with open(os.path.join(DEST_FOLDER, "Common_Briefing.pdf"), "wb") as f:
            writer.write(f)
        print("Common_Briefing.pdf 作成完了")

# -----------------------------------
# メイン処理: 地方別画像の保存
# -----------------------------------
def download_regional_images():
    print("--- 地方別画像の取得開始 ---")
    # FBOS (SIGWX) 全国分
    fbos_list = {
        "FBOS_Hokkaido": "fbos01", "FBOS_Tohoku": "fbos02", 
        "FBOS_East": "fbos03", "FBOS_West": "fbos04"
    }
    for name, code in fbos_list.items():
        download_file(f"https://www.data.jma.go.jp/airinfo/data/pict/low-level_sigwx/{code}.png", os.path.join(DEST_FOLDER, f"{name}.png"))

    # 降灰予報 (Sakurajimaなど)
    # 実際には最新時刻をループで探すロジックが必要（前回のコードを流用可能）
    # ここでは例として直近を保存
    download_file("https://www.jma.go.jp/bosai/volcano/data/ashfall/pdf/Z__C_RJTD_20260329120000_EQV_CHT_JCIashfallr_JR506X_N1_image.pdf", "temp_ash.pdf")
    # PDFをPNGに変換して保存 (pdf2image使用)
    from pdf2image import convert_from_path
    if os.path.exists("temp_ash.pdf"):
        images = convert_from_path("temp_ash.pdf")
        images[0].save(os.path.join(DEST_FOLDER, "Ashfall_Sakurajima.png"), "PNG")

if __name__ == "__main__":
    create_common_pdf()
    download_regional_images()
    # 一時ファイルの削除
    for f in os.listdir():
        if f.startswith("temp_") and f.endswith(".pdf"): os.remove(f)
