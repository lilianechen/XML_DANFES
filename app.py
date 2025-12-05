import streamlit as st
import zipfile
import io
import re
import xml.etree.ElementTree as ET
import pdfplumber
import pytesseract

st.set_page_config(page_title="Filtro por Pedido", page_icon="📦")

st.title("📦 Filtro Automático de XML + DANFE por Número de Pedido (xPed)")

st.write("""
Envie dois arquivos ZIP:
- Um contendo os **XMLs da NF-e**
- Outro contendo as **DANFEs em PDF**

Informe o **número do pedido (xPed)** e o sistema irá:
1. Encontrar todos os XMLs vinculados ao pedido
2. Identificar todas as NF-es relacionadas
3. Determinar automaticamente quais notas estão **autorizadas** ou **canceladas**
4. Filtrar as DANFEs correspondentes
5. Gerar um **ZIP final**
6. Criar um **relatório completo**
""")

xml_zip_file = st.file_uploader("📄 Envie o ZIP contendo XMLs", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie o ZIP contendo DANFEs (PDF)", type="zip")

pedido_desejado = st.text_input("Digite o número do pedido (xPed):")

# ---------------------------------------------------------
# Função para ler o pedido (xPed) dentro do XML
# ---------------------------------------------------------
def get_pedido_from_xml(content):
    try:
        root = ET.fromstring(content)
        xPed = root.find('.//{*}xPed')
        if xPed is not None:
            return xPed.text.strip()
    except:
        return None
    return None

# ---------------------------------------------------------
# Extrair número da NF dentro do XML
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
# Extrai número da NF do nome do arquivo PDF
# ---------------------------------------------------------
def get_nf_from_filename(filename):
    nums = re.findall(r"\d+", filename)
    if nums:
        return int(nums[-1])
    return None

# ---------------------------------------------------------
# Identifica cancelamento pelo nome do XML
# ---------------------------------------------------------
def is_xml_cancelado(filename):
    return "cancel" in filename.lower()

# ---------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# ---------------------------------------------------------
if st.button("🔍 Filtrar e Gerar ZIP"):
    if not xml_zip_file or not danfe_zip_file:
        st.error("Envie ambos os arquivos ZIP antes de continuar.")
        st.stop()

    if not pedido_desejado.strip():
        st.error("Digite o número do pedido (xPed).")
        st.stop()

    xml_zip = zipfile.ZipFile(xml_zip_file)
    danfe_zip = zipfile.ZipFile(danfe_zip_file)

    # Agrupar XMLs encontrados pelo número do pedido
    xmls_encontrados = []
    notas_por_xml = {}

    for name in xml_zip.namelist():
        if not name.lower().endswith(".xml"):
            continue

        content = xml_zip.read(name)
        pedido_xml = get_pedido_from_xml(content)

        if pedido_xml == pedido_desejado:
            xmls_encontrados.append(name)

            nf = get_nf_from_xml(content)
            if nf:
                notas_por_xml.setdefault(nf, []).append(name)

    if not xmls_encontrados:
        st.warning("Nenhum XML com este pedido foi encontrado.")
        st.stop()

    st.success(f"XMLs encontrados para o pedido {pedido_desejado}: {len(xmls_encontrados)}")

    # Determinar status das notas (autorizada/cancelada)
    notas_status = {}
    canceladas = []
    autorizadas = []

    for nf, arquivos in notas_por_xml.items():
        # Se existir arquivo com "-cancelado" → nota cancelada
        if any(is_xml_cancelado(a) for a in arquivos):
            notas_status[nf] = "cancelada"
            canceladas.append(nf)
        else:
            notas_status[nf] = "autorizada"
            autorizadas.append(nf)

    # Criar ZIP final
    output_zip_buffer = io.BytesIO()

    with zipfile.ZipFile(output_zip_buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        # Inserir apenas os XMLs relevantes
        for nf, arquivos in notas_por_xml.items():
            for xml_name in arquivos:
                xml_bytes = xml_zip.read(xml_name)
                new_zip.writestr(f"XMLs/{xml_name}", xml_bytes)

        # Filtrar DANFEs por NF
        for name in danfe_zip.namelist():
            if not name.lower().endswith(".pdf"):
                continue

            nf_pdf = get_nf_from_filename(name)

            if nf_pdf in notas_status:
                pdf_bytes = danfe_zip.read(name)
                new_zip.writestr(f"DANFEs/{name}", pdf_bytes)

        # Adicionar relatório
        relatorio = "RELATÓRIO DO PROCESSAMENTO\n\n"
        relatorio += f"Pedido analisado: {pedido_desejado}\n"
        relatorio += f"Total de notas encontradas: {len(notas_status)}\n"
        relatorio += f"Notas autorizadas: {len(autorizadas)} -> {autorizadas}\n"
        relatorio += f"Notas canceladas: {len(canceladas)} -> {canceladas}\n"

        new_zip.writestr("relatorio.txt", relatorio)

    st.success("Processo concluído!")

    st.download_button(
        label="⬇ Baixar ZIP Filtrado",
        data=output_zip_buffer.getvalue(),
        file_name=f"Pedido_{pedido_desejado}_filtrado.zip",
        mime="application/zip"
    )

    st.write("### Resultado:")
    st.write(relatorio.replace("\n", "<br>"), unsafe_allow_html=True)
