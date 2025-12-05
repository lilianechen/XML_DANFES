import streamlit as st
import zipfile
import io
import re
import xml.etree.ElementTree as ET
import pdfplumber
from PIL import Image
import pytesseract

st.set_page_config(page_title="Filtro de NFs", page_icon="📦")

st.title("📦 Filtro Automático de Notas Fiscais (XML + DANFE PDF)")

st.write("""
Envie dois arquivos ZIP:
- Um contendo **XMLs de NF-e**
- Outro contendo **DANFEs em PDF**
- Informe o intervalo de nota fiscal que deseja filtrar  
O sistema criará um **novo ZIP filtrado** contendo apenas as NF dentro do intervalo informado.
""")

# Uploads
xml_zip_file = st.file_uploader("📄 Envie o ZIP contendo XMLs", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie o ZIP contendo DANFEs (PDF)", type="zip")

nf_inicio = st.number_input("NF Inicial", min_value=0, step=1)
nf_fim = st.number_input("NF Final", min_value=0, step=1)

# ---------------------------------------------------------
# FUNÇÃO PARA PEGAR NF DO XML LENDO TAG <nNF>
# ---------------------------------------------------------
def get_nf_from_xml(content):
    try:
        root = ET.fromstring(content)
        nNF = root.find('.//{*}nNF')
        if nNF is not None and nNF.text.isdigit():
            return int(nNF.text)
    except:
        return None
    return None

# ---------------------------------------------------------
# PEGAR NF PELO NOME DO ARQUIVO DANFE
# Formato: NFe_001-000000106.pdf → NF = 106
# ---------------------------------------------------------
def get_nf_from_filename(filename):
    match = re.findall(r"\d+", filename)
    if match:
        return int(match[-1])  # o último número geralmente é o da NF
    return None

# ---------------------------------------------------------
# OCR PARA DANFE (CASO nome falhe)
# Procura padrões como: "Nº 106", "Nota Fiscal 106"
# ---------------------------------------------------------
def get_nf_from_pdf(pdf_bytes):
    # Tentar extrair texto do PDF
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text

        patterns = [
            r"Nota Fiscal\s*No?\s*(\d+)",
            r"N\.?F\.?\s*(\d+)",
            r"NF\s*(\d+)",
            r"Nº\s*(\d+)",
            r"No\s*(\d+)"
        ]

        for p in patterns:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                return int(match.group(1))

    except:
        pass

    # Se falhar, tentar OCR (para PDFs em imagem)
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=200).original
                ocr_text = pytesseract.image_to_string(img, lang="por")
                match = re.search(r"\bNF\s*(\d+)\b", ocr_text)
                if match:
                    return int(match.group(1))
    except:
        pass

    return None


# ---------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# ---------------------------------------------------------
if st.button("🔍 Filtrar e Gerar ZIP"):
    if not xml_zip_file or not danfe_zip_file:
        st.error("Envie os dois arquivos ZIP.")
        st.stop()

    if nf_inicio > nf_fim:
        st.error("NF Inicial não pode ser maior que NF Final.")
        st.stop()

    xml_zip = zipfile.ZipFile(xml_zip_file)
    danfe_zip = zipfile.ZipFile(danfe_zip_file)

    output_zip_buffer = io.BytesIO()

    with zipfile.ZipFile(output_zip_buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        st.subheader("🧾 XMLs filtrados:")

        for name in xml_zip.namelist():
            content = xml_zip.read(name)
            nf = get_nf_from_xml(content)

            if nf and nf_inicio <= nf <= nf_fim:
                st.write(f"✔ XML {name} → NF {nf}")
                new_zip.writestr(f"XMLs/{name}", content)

        st.subheader("📑 DANFEs filtradas:")

        for name in danfe_zip.namelist():
            if not name.lower().endswith(".pdf"):
                continue

            file_bytes = danfe_zip.read(name)

            # 1) Tentar pelo nome
            nf = get_nf_from_filename(name)

            # 2) Se falhar, tentar OCR
            if not nf:
                nf = get_nf_from_pdf(file_bytes)

            if nf and nf_inicio <= nf <= nf_fim:
                st.write(f"✔ DANFE {name} → NF {nf}")
                new_zip.writestr(f"DANFEs/{name}", file_bytes)

    st.success("Processo concluído com sucesso!")

    st.download_button(
        label="⬇ Baixar ZIP Filtrado",
        data=output_zip_buffer.getvalue(),
        file_name="NFs_filtradas.zip",
        mime="application/zip"
    )
