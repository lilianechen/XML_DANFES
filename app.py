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
- Separação automática de Remessa e Venda
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


def get_tipo_nf_from_xml(content):
    """
    Identifica se a NF é de Remessa ou Venda.
    Verifica o campo finNFe:
    - 1 = NF Normal (Venda)
    - 2 = NF Complementar (Venda)
    - 3 = NF de Ajuste (Venda)
    - 4 = Devolução/Retorno (Remessa)
    
    Também verifica CFOP para confirmar:
    - 6923 = Remessa (mais comum)
    - 5949, 6949 = Remessa
    - 5.XXX, 6.XXX (outros) = Venda
    """
    try:
        root = ET.fromstring(content)
        
        # Verifica CFOP primeiro (critério mais confiável)
        cfop = root.find('.//{*}CFOP')
        if cfop is not None:
            cfop_value = cfop.text.strip()
            # CFOPs de remessa: 6923 (mais comum), 5949, 6949, 5923
            if cfop_value in ['6923', '5923', '5949', '6949']:
                return "remessa"
        
        # Verifica finNFe como segunda checagem
        fin_nfe = root.find('.//{*}finNFe')
        if fin_nfe is not None:
            fin_value = fin_nfe.text.strip()
            # Se for 4, é devolução/remessa
            if fin_value == '4':
                return "remessa"
        
        # Se não identificou como remessa, considera venda
        return "venda"
    except:
        return "venda"  # Padrão em caso de erro


def get_nf_from_cancelamento(content):
    """Extrai número da NF do XML de cancelamento (procEventoNFe)."""
    try:
        root = ET.fromstring(content)
        chNFe = root.find('.//{*}chNFe')
        if chNFe is not None:
            nfe_str = chNFe.text.strip()
            if len(nfe_str) >= 34:
                nf_part = nfe_str[30:34]
                if nf_part.isdigit():
                    return int(nf_part)
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

pedidos_usuario = []
nf_inicio = None
nf_fim = None

if modo == "Filtrar por Pedido":
    pedidos_input = st.text_input("Digite os pedidos separados por vírgula (ex: 7373, 7374, 7375):")
    if pedidos_input:
        pedidos_usuario = [p.strip() for p in pedidos_input.split(",")]

elif modo == "Filtrar por Intervalo de NF":
    nf_inicio = st.number_input("NF Inicial:", min_value=0)
    nf_fim = st.number_input("NF Final:", min_value=0)

elif modo == "Filtrar por Pedido + Intervalo":
    pedidos_input = st.text_input("Digite os pedidos separados por vírgula (ex: 7373, 7374, 7375):")
    if pedidos_input:
        pedidos_usuario = [p.strip() for p in pedidos_input.split(",")]
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
    xmls_venda = []
    xmls_remessa = []
    danfes_venda = []
    danfes_remessa = []
    tipo_por_nf = {}  # Mapeia NF -> tipo (venda/remessa)

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
            tipo_nf = get_tipo_nf_from_xml(content)

            if nf is None:
                continue

            # filtro por pedido
            if len(pedidos_usuario) > 0 and pedido_xml not in pedidos_usuario:
                continue

            # filtro por intervalo
            if nf_inicio is not None and nf_fim is not None and "Intervalo" in modo:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            # Armazena o tipo da nota
            tipo_por_nf[nf] = tipo_nf
            
            # Separa por tipo
            if tipo_nf == "remessa":
                xmls_remessa.append(name)
            else:
                xmls_venda.append(name)
            
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
        
        # Verificar também arquivos de cancelamento não vinculados
        for name in xml_zip.namelist():
            if "-cancelamento" in name.lower() and name.lower().endswith(".xml"):
                content = xml_zip.read(name)
                nf = get_nf_from_cancelamento(content)
                if nf and nf in notas_xml:
                    if nf not in canceladas:
                        status_notas[nf] = "cancelada"
                        canceladas.append(nf)
                        if nf in autorizadas:
                            autorizadas.remove(nf)


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
            if pedidos_usuario and xml_zip and nf not in notas_xml:
                continue

            # filtro por intervalo
            if nf_inicio is not None and nf_fim is not None and "Intervalo" in modo:
                if not (nf_inicio <= nf <= nf_fim):
                    continue

            # NÃO incluir DANFEs de notas canceladas
            if xml_zip and nf in canceladas:
                continue

            # Separa DANFE por tipo (se XML foi processado)
            if nf in tipo_por_nf:
                if tipo_por_nf[nf] == "remessa":
                    danfes_remessa.append(name)
                else:
                    danfes_venda.append(name)
            else:
                # Se não tem XML, considera como venda por padrão
                danfes_venda.append(name)


    # ---------------------------------------------------------
    # GERAR ZIP FINAL
    # ---------------------------------------------------------

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as new_zip:

        if xml_zip:
            # XMLs de Venda (não cancelados)
            for xml in xmls_venda:
                content = xml_zip.read(xml)
                nf = get_nf_from_xml(content)
                if nf not in canceladas:
                    new_zip.writestr(f"XMLs_Venda/{xml}", content)
            
            # XMLs de Remessa (não cancelados)
            for xml in xmls_remessa:
                content = xml_zip.read(xml)
                nf = get_nf_from_xml(content)
                if nf not in canceladas:
                    new_zip.writestr(f"XMLs_Remessa/{xml}", content)

        if danfe_zip:
            # DANFEs de Venda
            for pdf in danfes_venda:
                new_zip.writestr(f"DANFEs_Venda/{pdf}", danfe_zip.read(pdf))
            
            # DANFEs de Remessa
            for pdf in danfes_remessa:
                new_zip.writestr(f"DANFEs_Remessa/{pdf}", danfe_zip.read(pdf))

        # Relatório detalhado
        rel = "=" * 60 + "\n"
        rel += "RELATÓRIO DO PROCESSAMENTO\n"
        rel += "=" * 60 + "\n\n"
        
        rel += f"Modo de filtragem: {modo}\n"

        if pedidos_usuario:
            rel += f"Pedidos filtrados: {', '.join(pedidos_usuario)}\n"

        if nf_inicio is not None and "Intervalo" in modo:
            rel += f"Intervalo de NF: {nf_inicio} até {nf_fim}\n"

        rel += "\n" + "-" * 60 + "\n"
        rel += "RESUMO GERAL\n"
        rel += "-" * 60 + "\n"

        if xml_zip:
            xmls_venda_ok = [x for x in xmls_venda if get_nf_from_xml(xml_zip.read(x)) not in canceladas]
            xmls_remessa_ok = [x for x in xmls_remessa if get_nf_from_xml(xml_zip.read(x)) not in canceladas]
            
            rel += f"Total de XMLs processados: {len(xmls_venda) + len(xmls_remessa)}\n"
            rel += f"  - XMLs de Venda: {len(xmls_venda_ok)}\n"
            rel += f"  - XMLs de Remessa: {len(xmls_remessa_ok)}\n"
            rel += f"\nNotas Autorizadas: {len(autorizadas)}\n"
            rel += f"Notas Canceladas: {len(canceladas)}\n"

        if danfe_zip:
            rel += f"\nTotal de DANFEs processadas: {len(danfes_venda) + len(danfes_remessa)}\n"
            rel += f"  - DANFEs de Venda: {len(danfes_venda)}\n"
            rel += f"  - DANFEs de Remessa: {len(danfes_remessa)}\n"

        rel += "\n" + "-" * 60 + "\n"
        rel += "DETALHAMENTO POR TIPO\n"
        rel += "-" * 60 + "\n"

        if xml_zip:
            nfs_venda = sorted([get_nf_from_xml(xml_zip.read(x)) for x in xmls_venda_ok])
            nfs_remessa = sorted([get_nf_from_xml(xml_zip.read(x)) for x in xmls_remessa_ok])
            
            rel += f"\nNotas de VENDA: {nfs_venda}\n"
            rel += f"Notas de REMESSA: {nfs_remessa}\n"
            
            if canceladas:
                rel += f"\nNotas CANCELADAS (excluídas): {sorted(canceladas)}\n"

        new_zip.writestr("relatorio.txt", rel)

    st.success("✅ Processamento concluído!")

    # Exibe resumo visual
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("XMLs de Venda", len([x for x in xmls_venda if get_nf_from_xml(xml_zip.read(x)) not in canceladas]) if xml_zip else 0)
        st.metric("DANFEs de Venda", len(danfes_venda))
    
    with col2:
        st.metric("XMLs de Remessa", len([x for x in xmls_remessa if get_nf_from_xml(xml_zip.read(x)) not in canceladas]) if xml_zip else 0)
        st.metric("DANFEs de Remessa", len(danfes_remessa))

    st.download_button(
        "⬇ Baixar ZIP Final",
        data=buffer.getvalue(),
        file_name="resultado_filtrado.zip",
        mime="application/zip"
    )

    with st.expander("📋 Ver Relatório Completo"):
        st.code(rel)
