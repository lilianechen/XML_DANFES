import streamlit as st
import zipfile
import io
import re
import xml.etree.ElementTree as ET

st.set_page_config(page_title="Filtro por Pedido e Intervalo NF", page_icon="📦")

st.title("📦 Filtro Inteligente de XML + DANFE por Pedido / Intervalo de NF")

st.write("""
Sistema profissional com:
- Upload opcional de XML e/ou DANFE
- Cancelamento detectado por lógica DEFINITIVA
- Filtro por pedido, intervalo ou ambos
- Geração de ZIP + relatório completo
""")


# ---------------------------------------------------------
# 🔵 Funções auxiliares
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
    """Extrai número da NF."""
    try:
        root = ET.fromstring(content)
        node = root.find('.//{*}nNF')
        if node is not None and node.text.isdigit():
            return int(node.text)
    except:
        return None
    return None


def xml_esta_cancelado(content):
    """Detecta cancelamento pelo CONTEÚDO."""
    try:
        root = ET.fromstring(content)

        if root.find('.//{*}tpEvento') is not None:
            if root.find('.//{*}tpEvento').text.strip() == "110111":
                return True

        if root.find('.//{*}procEventoNFe') is not None:
            return True

        cStat = root.find('.//{*}cStat')
        if cStat is not None and cStat.text.strip() == "101":
            return True

        desc = root.find('.//{*}descEvento')
        if desc is not None and "cancel" in desc.text.lower():
            return True

        motivo = root.find('.//{*}xMotivo')
        if motivo is not None and "cancel" in motivo.text.lower():
            return True

    except:
        return False

    return False


def get_nf_from_filename(filename):
    """Extrai NF de PDF pelo nome."""
    nums = re.findall(r"\d+", filename)
    if nums:
        return int(nums[-1])
    return None


# ---------------------------------------------------------
# 🔵 Upload dos arquivos (opcional)
# ---------------------------------------------------------

xml_zip_file = st.file_uploader("📄 Envie o ZIP com XMLs (opcional)", type="zip")
danfe_zip_file = st.file_uploader("📑 Envie o ZIP com DANFEs (opcional)", type="zip")

# ---------------------------------------------------------
# 🔵 Seleção do modo de filtragem
# ---------------------------------------------------------

modo = st.radio(
    "Como deseja filtrar?",
    ["Filtrar por Pedido", "Filtrar por Intervalo de NF", "Filtrar por Pedido + Intervalo"]
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
    pedido_usuario = st.text_input("Digite o pedido (4 ou 5 dígitos):")
    nf_inicio = st.number_input("NF Inicial:", min_value=0)
    nf_fim = st.number_input("NF Final:", min_value=0)


# ---------------------------------------------------------
# 🔵 Botão de processamento
# ---------------------------------------------------------

if st.button("🔍 Processar"):

    if not xml_zip_file and not danfe_zip_file:
        st.error("Envie pelo menos um arquivo ZIP (XML ou DANFE).")
        st.stop()

    xml_zip = zipfile.ZipFile(xml_zip_file) if xml_zip_file else None
    danfe_zip = zipfile.ZipFile(danfe_zip_file) if danfe_zip_file else None

    notas_xml = {}
    xmls_filtrados = []
    notas_filtradas_intervalo = []

    # ---------------------------------------------------------
    # 🔵 PROCESSAR XMLs SE EXISTIREM
    # ---------------------------------------------------------

    if xml_zip:

        # 1️⃣ Identificar XMLs do pedido (ou todos, se filtro for por NF)
        for name in xml_zip.namelist():
            if not name.lower().endswith(".xml"):
                continue

            content = xml_zip.read(name)
            pedido_xml = get_pedido_from_xml(content)
            nf = get_nf_from_xml(content)

            if nf is None:
                continue

            # Filtragem por pedido
            if pedido_usuario and pedido_xml != pedido_usuario:
                continue

            # Filtragem por intervalo (caso exista)
            if nf_inicio is not None and nf_fim is not None:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            xmls_filtrados.append(name)
            notas_xml.setdefault(nf, []).append(name)

        # 2️⃣ Determinar status das notas
        notas_autorizadas = []
        notas_canceladas = []
        status_notas = {}

        for nf, arquivos in notas_xml.items():
            if len(arquivos) >= 2:
                # regra definitiva
                status_notas[nf] = "cancelada"
                notas_canceladas.append(nf)
                continue

            unico = xml_zip.read(arquivos[0])
            if xml_esta_cancelado(unico):
                status_notas[nf] = "cancelada"
                notas_canceladas.append(nf)
            else:
                status_notas[nf] = "autorizada"
                notas_autorizadas.append(nf)

    # ---------------------------------------------------------
    # 🔵 PROCESSAR DANFEs SE EXISTIREM
    # ---------------------------------------------------------

    danfes_filtradas = []

    if danfe_zip:

        for name in danfe_zip.namelist():
            if not name.lower().endswith(".pdf"):
                continue

            nf = get_nf_from_filename(name)
            if nf is None:
                continue

            # Se filtrando por pedido sem XML → impossível
            if modo in ("Filtrar por Pedido", "Filtrar por Pedido + Intervalo") and not xml_zip:
                st.error("Para filtrar por pedido você deve enviar XMLs.")
                st.stop()

            # Se filtrando por pedido + xml existente
            if pedido_usuario and xml_zip:
                if nf not in notas_xml:
                    continue

            # Filtrar por intervalo
            if nf_inicio is not None and nf_fim is not None:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            danfes_filtradas.append(name)

    # ---------------------------------------------------------
    # 🔵 Criar ZIP final
    # ---------------------------------------------------------

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        # XMLs filtrados
        if xml_zip:
            for xml_name in xmls_filtrados:
                new_zip.writestr(f"XMLs_filtrados/{xml_name}", xml_zip.read(xml_name))

        # DANFEs filtradas
        if danfe_zip:
            for pdf in danfes_filtradas:
                new_zip.writestr(f"DANFEs_filtradas/{pdf}", danfe_zip.read(pdf))

        # Relatório
        rel = "RELATÓRIO DO PROCESSAMENTO\n\n"
        rel += f"Modo de filtragem: {modo}\n"
        if pedido_usuario:
            rel += f"Pedido filtrado: {pedido_usuario}\n"
        if nf_inicio is not None:
            rel += f"Intervalo de NF: {nf_inicio} a {nf_fim}\n"
        rel += "\n"

        # XML summary
        if xml_zip:
            rel += f"XMLs filtrados: {len(xmls_filtrados)}\n"
            rel += f"Notas encontradas: {list(notas_xml.keys())}\n"
            rel += f"Autorizadas: {notas_autorizadas}\n"
            rel += f"Canceladas: {notas_canceladas}\n\n"

        # DANFE summary
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

    st.write("### Resultado:")
    st.code(rel)
