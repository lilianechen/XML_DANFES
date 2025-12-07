import streamlit as st
import zipfile
import io
import re
import xml.etree.ElementTree as ET

st.set_page_config(page_title="Filtro XML/DANFE Profissional", page_icon="📦")

st.title("📦 Filtro Inteligente de XML + DANFE por Pedido e Intervalo de NF")

st.write("""
Sistema avançado:
- Upload opcional de XML e/ou DANFE
- Cancelamento detectado por NOME DO ARQUIVO
- Filtro por pedido, intervalo ou ambos
- Geração de ZIP + relatório completo
""")


# ---------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------

def get_pedido_from_xml(content):
    """Extrai 4 ou 5 dígitos iniciais do xPed."""
    try:
        root = ET.fromstring(content)
        node = root.find('.//{*}xPed')
        if node is None:
            return None
        raw = node.text.strip()
        match = re.match(r"(\d+)", raw)
        if not match:
            return None
        bloco = match.group(1)
        if len(bloco) in (4, 5):
            return bloco
        return bloco[:5]
    except:
        return None


def get_nf_from_xml(content):
    """Extrai número da NF do XML."""
    try:
        root = ET.fromstring(content)
        node = root.find('.//{*}nNF')
        if node is not None and node.text.isdigit():
            return int(node.text)
    except:
        return None
    return None


def is_cancelado_by_filename(filename):
    """Detecta se o arquivo contém '-cancelamento' no nome."""
    return "-cancelamento" in filename.lower()


def get_nf_from_filename(filename):
    """Extrai NF de PDF pelo nome."""
    nums = re.findall(r"\d+", filename)
    if nums:
        return int(nums[-1])
    return None


# ---------------------------------------------------------
# UPLOAD OPCIONAL
# ---------------------------------------------------------

xml_zip_file = st.file_uploader("📄 Envie XMLs (opcional)", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie DANFEs (opcional)", type="zip")

xml_zip = zipfile.ZipFile(xml_zip_file) if xml_zip_file else None
danfe_zip = zipfile.ZipFile(danfe_zip_file) if danfe_zip_file else None


# ---------------------------------------------------------
# MODO DE FILTRAGEM
# ---------------------------------------------------------

modo = st.radio(
    "Como deseja filtrar?",
    [
        "Filtrar por Pedido",
        "Filtrar por Intervalo de NF",
        "Filtrar por Pedido + Intervalo"
    ]
)

pedido_usuario = None
nf_inicio = None
nf_fim = None

if modo == "Filtrar por Pedido":
    pedido_usuario = st.text_input("Digite o pedido (4 ou 5 dígitos):")

elif modo == "Filtrar por Intervalo de NF":
    nf_inicio = st.number_input("NF Inicial:", min_value=0)
    nf_fim = st.number_input("NF Final:", min_value=0)

elif modo == "Filtrar por Pedido + Intervalo":
    pedido_usuario = st.text_input("Digite o pedido:")
    nf_inicio = st.number_input("NF Inicial:", min_value=0)
    nf_fim = st.number_input("NF Final:", min_value=0)


# ---------------------------------------------------------
# PROCESSAR
# ---------------------------------------------------------

if st.button("🔍 Processar"):

    if not xml_zip and not danfe_zip:
        st.error("Envie pelo menos um dos arquivos ZIP.")
        st.stop()

    notas_xml = {}
    xmls_filtrados = []
    danfes_filtradas = []

    # ---------------------------------------------------------
    # PROCESSAR XMLs (SE EXISTIREM)
    # ---------------------------------------------------------
    if xml_zip:

        for name in xml_zip.namelist():

            if not name.lower().endswith(".xml"):
                continue

            content = xml_zip.read(name)
            nf = get_nf_from_xml(content)
            pedido_xml = get_pedido_from_xml(content)

            if nf is None:
                continue

            # filtro por pedido
            if pedido_usuario and pedido_xml != pedido_usuario:
                continue

            # filtro por intervalo
            if nf_inicio is not None and nf_fim is not None and "Intervalo" in modo:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            xmls_filtrados.append(name)
            notas_xml.setdefault(nf, []).append((name, is_cancelado_by_filename(name)))

        # LÓGICA DE CANCELAMENTO POR NOME DO ARQUIVO
        status_notas = {}
        autorizadas = []
        canceladas = []

        for nf, lista_arquivos in notas_xml.items():

            tem_cancelado = any(is_cancel for _, is_cancel in lista_arquivos)

            if tem_cancelado:
                status_notas[nf] = "cancelada"
                canceladas.append(nf)
            else:
                status_notas[nf] = "autorizada"
                autorizadas.append(nf)


    # ---------------------------------------------------------
    # PROCESSAR DANFEs (SE EXISTIREM)
    # ---------------------------------------------------------
    if danfe_zip:

        for name in danfe_zip.namelist():

            if not name.lower().endswith(".pdf"):
                continue

            nf = get_nf_from_filename(name)
            if nf is None:
                continue

            # filtro por pedido (somente se XML foi enviado)
            if pedido_usuario and xml_zip and nf not in notas_xml:
                continue

            # filtro por intervalo
            if nf_inicio is not None and nf_fim is not None and "Intervalo" in modo:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            danfes_filtradas.append(name)


    # ---------------------------------------------------------
    # GERAR ZIP FINAL
    # ---------------------------------------------------------

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        if xml_zip:
            for xml in xmls_filtrados:
                new_zip.writestr(f"XMLs_filtrados/{xml}", xml_zip.read(xml))

        if danfe_zip:
            for pdf in danfes_filtradas:
                new_zip.writestr(f"DANFEs_filtrados/{pdf}", danfe_zip.read(pdf))

        rel = "RELATÓRIO DO PROCESSAMENTO\n\n"
        rel += f"Modo de filtragem: {modo}\n"

        if pedido_usuario:
            rel += f"Pedido filtrado: {pedido_usuario}\n"

        if nf_inicio is not None and "Intervalo" in modo:
            rel += f"Intervalo de NF: {nf_inicio} até {nf_fim}\n"

        rel += "\n"

        if xml_zip:
            rel += f"XMLs filtrados: {len(xmls_filtrados)}\n"
            rel += f"Notas encontradas: {list(notas_xml.keys())}\n"
            rel += f"Autorizadas: {autorizadas}\n"
            rel += f"Canceladas: {canceladas}\n\n"

        if danfe_zip:
            rel += f"DANFEs filtradas: {len(danfes_filtradas)}\n"
            rel += f"Arquivos DANFE: {danfes_filtradas}\n"

        new_zip.writestr("relatorio.txt", rel)

    st.success("Processamento concluído!")

    st.download_button(
        "⬇ Baixar ZIP Final",
        data=buffer.getvalue(),
        file_name="resultado_filtrado.zip",
        mime="application/zip"
    )

    st.code(rel)
