from flask import Flask, request, jsonify
import fitz
import requests
import os
import io
from PIL import Image
import imagehash
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
import matplotlib.pyplot as plt

app = Flask(__name__)


def extraire_images_avec_infos(pdf_path):
    doc = fitz.open(pdf_path)
    images_info = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_hash = imagehash.phash(pil_image)
            images_info.append({
                "page_index": page_index,
                "xref": xref,
                "hash": img_hash,
                "image": pil_image
            })
    return doc, images_info


def detecter_logos(images_info, seuil_repetition=2):
    hash_counts = {}
    for info in images_info:
        h = str(info["hash"])
        hash_counts[h] = hash_counts.get(h, 0) + 1
    return {h for h, count in hash_counts.items() if count >= seuil_repetition}


def supprimer_logos(doc, images_info, logos_detectes):
    for info in images_info:
        if str(info["hash"]) in logos_detectes:
            doc[info["page_index"]].delete_image(info["xref"])
    return doc


def extraire_images_vers_pdf(source_pdf, output_pdf):
    doc = fitz.open(source_pdf)
    images = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            images.append(pil_image)

    if images:
        pdf_images = [img.convert("RGB") for img in images]
        pdf_images[0].save(output_pdf, save_all=True, append_images=pdf_images[1:])
        return len(images)
    return 0


@app.route("/remove-logos", methods=["POST"])
def remove_logos():
    print(">>> /remove-logos endpoint hit")
    try:
        data = request.get_json()
        pdf_url = data["url"]

        input_pdf = "input.pdf"
        response = requests.get(pdf_url)
        with open(input_pdf, "wb") as f:
            f.write(response.content)

        output_pdf = "static/pdf-sans-logos.pdf"
        os.makedirs("static", exist_ok=True)

        doc, images_info = extraire_images_avec_infos(input_pdf)
        logos = detecter_logos(images_info)
        doc = supprimer_logos(doc, images_info, logos)
        doc.save(output_pdf)

        extracted_pdf = "static/extrait-images.pdf"
        images_extracted = extraire_images_vers_pdf(output_pdf, extracted_pdf)

        return jsonify({
            "status": "success",
            "logos_detected": len(logos),
            "clean_pdf": request.host_url + "static/pdf-sans-logos.pdf",
            "images_pdf": request.host_url + "static/extrait-images.pdf",
            "images_extracted": images_extracted
        })

    except Exception as e:
        print(f"Erreur : {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    try:
        data = request.get_json()
        pdf_url = data["url"]
        json_pieces = data["pieces"]

        pdf_path = "input.pdf"
        response = requests.get(pdf_url)
        with open(pdf_path, "wb") as f:
            f.write(response.content)

        def extraire_images_par_page(pdf_path):
            doc = fitz.open(pdf_path)
            images_par_page = {}
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                images = []
                for img in page.get_images(full=True):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    img_pil = Image.open(BytesIO(image_bytes)).convert("RGB")
                    images.append(img_pil)
                images_par_page[page_num] = images
            return images_par_page

        images_par_page = extraire_images_par_page(pdf_path)

        output_pdf_path = "static/output.pdf"
        os.makedirs("static", exist_ok=True)

        doc = SimpleDocTemplate(output_pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        max_width = 400
        espace_vertical = 10
        total_images = 0

        for piece, infos in json_pieces.items():
            description = infos["description"]
            pages = infos["pages"]

            elements.append(Paragraph(f"<b>{piece.capitalize()}</b>", styles["Title"]))
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(description, styles["Normal"]))
            elements.append(Spacer(1, 12))

            for page_str, image_indices in pages.items():
                page_num = int(page_str) - 1
                images = images_par_page.get(page_num, [])
                for idx in image_indices:
                    image_index = idx - 1
                    if 0 <= image_index < len(images):
                        img = images[image_index]
                        ratio = min(max_width / img.width, 1)
                        resized_img = img.resize((int(img.width * ratio), int(img.height * ratio)))
                        buffer = BytesIO()
                        resized_img.save(buffer, format="PNG")
                        buffer.seek(0)
                        rl_img = RLImage(buffer, width=resized_img.width, height=resized_img.height)
                        elements.append(rl_img)
                        elements.append(Spacer(1, espace_vertical))
                        total_images += 1

            elements.append(PageBreak())

        doc.build(elements)

        public_url = request.host_url + "static/output.pdf"

        return jsonify({
            "status": "success",
            "pdf_url": public_url,
            "images_total": total_images
        })

    except Exception as e:
        print(f"Erreur : {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
