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

Digite o **número do pedido (4 ou 5 dígitos)**.

O sistema irá:
1. Encontrar todos os XMLs vinculados ao pedido (campo xPed)
2. Identificar todas as NF-es relacionadas
3. Detectar automaticamente XMLs **cancelados**
4. Filtrar as DANFEs correspondentes
5. Gerar um **ZIP final com XMLs, DANFEs e relatório**
""")

xml_zip_file = st.file_uploader("📄 Envie o ZIP contendo XMLs", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie o ZIP contendo DANFEs (PDF)", type="zip")

pedido_usuario = st.text_input("Digite o número do pedido (4 ou 5 dígitos):")


# ---------------------------------------------------------
# Extrair o pedido real do XML: primeiros 4 ou 5 dígitos
# ---------------------------------------------------------
def get_pedido_from_xml(content):
    try:
        root = ET.fromstring(content)
        xPed_node = root.find('.//{*}xPed')
        if xPed_node is None:
            return None

        raw_value = xPed_node.text.strip()

        # Pega somente os dígitos iniciais
        match = re.match(r"(\d+)", raw_value)
        if not match:
            return None

        bloco = match.group(1)

        # Se bloco tiver 4 ou 5 dígitos → OK
        if len(bloco) in (4, 5):
            return bloco

        # Se tiver mais dígitos (caso raro), pegar só os primeiros 5
        return bloco[:5]

    except:
        return None


# ---------------------------------------------------------
# Extrair número da NF do XML
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
# Extrair NF do nome do PDF
# ---------------------------------------------------------
def get_nf_from_filename(filename):
    nums = re.findall(r"\d+", filename)
    if nums:
        return int(nums[-1])
    return None


# ---------------------------------------------------------
# Verifica se um XML é cancelado pelo nome do arquivo
# ---------------------------------------------------------
def is_xml_cancelado(filename):
    return "cancel" in filename.lower()


# ---------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# ---------------------------------------------------------
if st.button("🔍 Processar Pedido"):
    if not xml_zip_file or not danfe_zip_file:
        st.error("Envie ambos os arquivos ZIP.")
        st.stop()

    if not pedido_usuario.strip():
        st.error("Digite o número do pedido.")
        st.stop()

    xml_zip = zipfile.ZipFile(xml_zip_file)
    danfe_zip = zipfile.ZipFile(danfe_zip_file)

    xmls_do_pedido = []
    notas_xml = {}

    # -----------------------------
    # Filtrar XMLs pelo pedido
    # -----------------------------
    for name in xml_zip.namelist():
        if not name.lower().endswith(".xml"):
            continue

        content = xml_zip.read(name)
        pedido_xml = get_pedido_from_xml(content)

        if pedido_xml and pedido_xml == pedido_usuario:
            xmls_do_pedido.append(name)

            nf = get_nf_from_xml(content)
            if nf:
                notas_xml.setdefault(nf, []).append(name)

    if not xmls_do_pedido:
        st.warning("Nenhum XML encontrado para esse pedido.")
        st.stop()

    st.success(f"XMLs encontrados para o pedido {pedido_usuario}: {len(xmls_do_pedido)}")


    # -----------------------------
    # Determinar status das notas
    # -----------------------------
    status_notas = {}
    canceladas = []
    autorizadas = []

    for nf, arquivos in notas_xml.items():
        if any(is_xml_cancelado(arq) for arq in arquivos):
            status_notas[nf] = "cancelada"
            canceladas.append(nf)
        else:
            status_notas[nf] = "autorizada"
            autorizadas.append(nf)


    # -----------------------------
    # Criar ZIP final
    # -----------------------------
    output_zip_buffer = io.BytesIO()

    with zipfile.ZipFile(output_zip_buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        # XMLs
        for nf, arquivos in notas_xml.items():
            for xml_name in arquivos:
                xml_bytes = xml_zip.read(xml_name)
                new_zip.writestr(f"XMLs/{xml_name}", xml_bytes)

        # DANFEs
        for name in danfe_zip.namelist():
            if not name.lower().endswith(".pdf"):
                continue

            nf_pdf = get_nf_from_filename(name)
            if nf_pdf in status_notas:
                new_zip.writestr(f"DANFEs/{name}", danfe_zip.read(name))

        # Relatório
        rel = f"Pedido analisado: {pedido_usuario}\n\n"
        rel += f"Total de notas encontradas: {len(status_notas)}\n"
        rel += f"Autorizadas: {autorizadas}\n"
        rel += f"Canceladas: {canceladas}\n"

        new_zip.writestr("relatorio.txt", rel)


    st.success("Processo concluído com sucesso!")

    st.download_button(
        label="⬇ Baixar ZIP Final",
        data=output_zip_buffer.getvalue(),
        file_name=f"pedido_{pedido_usuario}_resultado.zip",
        mime="application/zip"
    )

    st.write("### Resultado:")
    st.code(rel)
