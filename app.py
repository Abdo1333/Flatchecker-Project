from flask import Flask, request, jsonify
from flask_cors import CORS
import fitz  # PyMuPDF
import requests
from PIL import Image
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
import os
import traceback

app = Flask(__name__)
CORS(app)

@app.route("/generate-pdf", methods=["POST"])
def generate_pdf():
    try:
        # Lecture du body JSON
        data = request.get_json()
        if not data:
            raise ValueError("Le corps de la requête est vide ou mal formaté.")
        
        pdf_url = data.get("url")
        json_pieces = data.get("pieces")

        if not pdf_url or not json_pieces:
            raise ValueError("Le champ 'url' ou 'pieces' est manquant.")

        # Téléchargement du PDF
        pdf_path = "input.pdf"
        response = requests.get(pdf_url)
        response.raise_for_status()
        with open(pdf_path, "wb") as f:
            f.write(response.content)

        # Fonction d'extraction des images
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

        # Génération du nouveau PDF
        output_pdf_path = "static/output.pdf"
        os.makedirs("static", exist_ok=True)

        doc = SimpleDocTemplate(output_pdf_path, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        max_width = 400
        espace_vertical = 10
        total_images = 0

        for piece, infos in json_pieces.items():
            description = infos.get("description", "")
            pages = infos.get("pages", {})

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

        # URL publique vers le PDF généré
        public_url = request.host_url.rstrip("/") + "/static/output.pdf"

        return jsonify({
            "status": "success",
            "pdf_url": public_url,
            "images_total": total_images
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
