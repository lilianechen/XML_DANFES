import streamlit as st
import zipfile
import io
import re
import xml.etree.ElementTree as ET
import pdfplumber
import pytesseract

st.set_page_config(page_title="Filtro por Pedido (Definitivo)", page_icon="📦")

st.title("📦 Filtro Automático DEFINITIVO de XML + DANFE por Número de Pedido (xPed)")

st.write("""
Sistema atualizado com detecção **CORRETA e DEFINITIVA** de notas canceladas.

Agora o cancelamento é identificado pelo **conteúdo do XML**, independentemente do nome do arquivo.
""")

xml_zip_file = st.file_uploader("📄 Envie o ZIP contendo XMLs", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie o ZIP contendo DANFEs (PDF)", type="zip")

pedido_usuario = st.text_input("Digite o número do pedido (4 ou 5 dígitos):")


# ---------------------------------------------------------
# Extrair o pedido real (4 ou 5 dígitos)
# ---------------------------------------------------------
def get_pedido_from_xml(content):
    try:
        root = ET.fromstring(content)
        xPed_node = root.find('.//{*}xPed')
        if xPed_node is None:
            return None

        raw = xPed_node.text.strip()

        # pegar somente os dígitos iniciais
        match = re.match(r"(\d+)", raw)
        if not match:
            return None

        bloco = match.group(1)

        # se o bloco tiver 4 ou 5 dígitos → OK
        if len(bloco) in (4, 5):
            return bloco

        # se vier maior, pegar os primeiros 5
        return bloco[:5]

    except:
        return None


# ---------------------------------------------------------
# Extrair número da NF do XML
# ---------------------------------------------------------
def get_nf_from_xml(content):
    try:
        root = ET.fromstring(content)
        node = root.find('.//{*}nNF')
        if node is not None and node.text.isdigit():
            return int(node.text)
    except:
        return None
    return None


# ---------------------------------------------------------
# EXTRATOR DEFINITIVO DE CANCELAMENTO — PELO CONTEÚDO
# ---------------------------------------------------------
def xml_esta_cancelado(content):

    try:
        root = ET.fromstring(content)

        # 1️⃣ Evento de cancelamento
        tpEvento = root.find('.//{*}tpEvento')
        if tpEvento is not None and tpEvento.text.strip() == "110111":
            return True

        # 2️⃣ Estrutura de evento de cancelamento
        if root.find('.//{*}procEventoNFe') is not None:
            return True

        # 3️⃣ cStat 101 = cancelado
        cStat = root.find('.//{*}cStat')
        if cStat is not None and cStat.text.strip() == "101":
            return True

        # 4️⃣ descrição do evento
        desc = root.find('.//{*}descEvento')
        if desc is not None and "cancel" in desc.text.lower():
            return True

        # 5️⃣ xMotivo contendo cancelamento
        xMotivo = root.find('.//{*}xMotivo')
        if xMotivo is not None and "cancel" in xMotivo.text.lower():
            return True

    except:
        return False

    return False


# ---------------------------------------------------------
# Extrair NF do PDF pelo nome
# ---------------------------------------------------------
def get_nf_from_filename(filename):
    nums = re.findall(r"\d+", filename)
    if nums:
        return int(nums[-1])
    return None


# ---------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# ---------------------------------------------------------
if st.button("🔍 Processar Pedido"):
    
    if not xml_zip_file or not danfe_zip_file:
        st.error("Envie os dois arquivos ZIP.")
        st.stop()

    if not pedido_usuario.strip():
        st.error("Digite o número do pedido.")
        st.stop()

    xml_zip = zipfile.ZipFile(xml_zip_file)
    danfe_zip = zipfile.ZipFile(danfe_zip_file)

    xmls_pedido = []
    notas_dict = {}

    # -------------------------------
    # 1️⃣ Encontrar XMLs do pedido
    # -------------------------------
    for name in xml_zip.namelist():
        if not name.lower().endswith(".xml"):
            continue

        content = xml_zip.read(name)
        pedido_xml = get_pedido_from_xml(content)

        if pedido_xml == pedido_usuario:
            xmls_pedido.append(name)

            nf = get_nf_from_xml(content)
            if nf:
                notas_dict.setdefault(nf, []).append(name)

    if not xmls_pedido:
        st.warning("Nenhum XML encontrado para esse pedido.")
        st.stop()

    # -------------------------------
    # 2️⃣ Determinar status da NF
    # -------------------------------
    status_notas = {}
    autorizadas = []
    canceladas = []

    for nf, arquivos in notas_dict.items():

        # Se QUALQUER XML contiver cancelamento → cancelada
        if any(xml_esta_cancelado(xml_zip.read(a)) for a in arquivos):
            status_notas[nf] = "cancelada"
            canceladas.append(nf)
        else:
            status_notas[nf] = "autorizada"
            autorizadas.append(nf)

    # -------------------------------
    # 3️⃣ Criar ZIP final
    # -------------------------------
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        # XMLs
        for nf, arquivos in notas_dict.items():
            for xml_name in arquivos:
                new_zip.writestr(f"XMLs/{xml_name}", xml_zip.read(xml_name))

        # DANFEs
        for name in danfe_zip.namelist():
            if name.lower().endswith(".pdf"):
                nf_pdf = get_nf_from_filename(name)
                if nf_pdf in status_notas:
                    new_zip.writestr(f"DANFEs/{name}", danfe_zip.read(name))

        # Relatório
        rel = f"Pedido analisado: {pedido_usuario}\n\n"
        rel += f"Total de notas: {len(status_notas)}\n"
        rel += f"Notas autorizadas: {autorizadas}\n"
        rel += f"Notas canceladas: {canceladas}\n"

        new_zip.writestr("relatorio.txt", rel)

    st.success("Processo concluído com sucesso!")

    st.download_button(
        label="⬇ Baixar ZIP Final",
        data=buffer.getvalue(),
        file_name=f"pedido_{pedido_usuario}_resultado.zip",
        mime="application/zip"
    )

    st.write("### Resultado:")
    st.code(rel)
