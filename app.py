import streamlit as st
import pandas as pd
import numpy as np
import re
from datetime import datetime
import pytz
from simple_salesforce import Salesforce
import plotly.express as px
import plotly.graph_objects as go
import io
import os

# ==========================================
# 0. CONSTANTES (evita strings mágicas espalhadas)
# ==========================================
class StatusMP:
    EM_DIA = 'EM DIA'
    PROGRAMADO = 'PROGRAMADO P/ ZERAR MP'
    CRITICO = 'EM ATRASO (Crítico)'
    DESCONSIDERADO = 'DESCONSIDERADO (Desinstalação)'

class AtrasoBase:
    EM_DIA = 'EM DIA'
    ATRASADO = 'ATRASADO'
    ISENTO = 'ISENTO (Desinstalação)'

class StatusFin:
    ADIMPLENTE = 'Adimplente'
    INADIMPLENTE = 'Inadimplente'

ARQUIVO_FUNIL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'historico_funil.csv')
FUSO_BR = pytz.timezone('America/Sao_Paulo')
CARENCIA_ATRASO_DIAS = 30  # dias de carencia: o contrato so entra em ATRASO N dias apos o vencimento da MP

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS
# ==========================================
st.set_page_config(
    page_title="Manutenção Preventiva", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- FUNÇÃO DE ESTILO PARA GRÁFICOS ---
def aplicar_tema_moderno(fig, cores_azuis=None):
    if cores_azuis is None:
        cores_azuis = ['#0A2A66', '#1E5FCC', '#3B82F6', '#60A5FA', '#93C5FD', '#1E40AF', '#2563EB']

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter, sans-serif", size=12, color='#16233F'),
        title_font=dict(family="Inter, sans-serif", size=16, color='#0A2A66'),
        colorway=cores_azuis,
        legend=dict(font=dict(color='#16233F')),
        hoverlabel=dict(font=dict(family="Inter, sans-serif"), bgcolor='#0A2A66'),
        margin=dict(t=48, l=10, r=10, b=10),
    )
    if fig.layout.title.text is None:
        fig.update_layout(title_text="")
    fig.update_traces(marker_cornerradius=8, selector=dict(type='bar'))
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#E4EBF6', zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root{
        --navy:#0A2A66; --blue:#1E5FCC; --blue2:#3B82F6; --blue-soft:#EAF1FB;
        --ink:#16233F; --muted:#647393; --line:#E4EBF6; --bg:#F4F7FD; --card:#FFFFFF;
    }
    html{ font-size:13px; }
    html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] * { font-family:'Inter', sans-serif; }
    [data-testid="stAppViewContainer"]{ background:var(--bg); }
    [data-testid="stHeader"]{ background:rgba(0,0,0,0); height:0; }
    .block-container{ padding-top:1.6rem; padding-bottom:2rem; max-width:1600px; }
    h1,h2,h3,h4{ color:var(--navy); font-weight:700; letter-spacing:-0.01em; }
    h2{ font-size:1.22rem !important; }
    h3{ font-size:1.0rem !important; }
    [data-testid="stMarkdownContainer"] p{ font-size:0.9rem; }

    /* Sidebar */
    [data-testid="stSidebar"]{ background:var(--card); border-right:1px solid var(--line); }
    [data-testid="stSidebar"] .block-container{ padding-top:1rem; }
    [data-testid="stSidebar"] h1{ font-size:1.3rem; color:var(--navy); font-weight:800; text-align:center; margin:.3rem 0 .2rem; }
    [data-testid="stSidebar"] h2{ font-size:.9rem !important; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; }
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span{ color:var(--ink); }
    [data-testid="stSidebar"] img{ border-radius:8px; }

    /* KPI cards (compactos) */
    .kpi-container{
        background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:11px 8px 9px; text-align:center;
        box-shadow:0 1px 2px rgba(16,40,90,.04), 0 8px 20px rgba(16,40,90,.05);
        transition:transform .2s ease, box-shadow .2s ease;
        height:102px; display:flex; flex-direction:column; justify-content:center;
        position:relative; overflow:hidden; margin-bottom: 1rem;
    }
    .kpi-container::before{ content:""; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg,var(--navy),var(--blue2)); }
    .kpi-container:hover{ transform:translateY(-3px); box-shadow:0 2px 4px rgba(16,40,90,.06), 0 14px 28px rgba(16,40,90,.10); }
    .kpi-title{ font-size:.62rem; color:var(--muted); font-weight:600; text-transform:uppercase; letter-spacing:.04em; margin-bottom:5px; line-height:1.15; }
    .kpi-value{ font-size:1.25rem; color:var(--navy); font-weight:800; line-height:1.05; }
    .kpi-sub-value{ font-size:.62rem; color:var(--muted); margin-top:4px; }
    .kpi-delta{ font-size:.64rem; font-weight:700; }
    .kpi-value.positive, .kpi-delta.positive{ color:#0E9F6E; }
    .kpi-value.negative, .kpi-delta.negative{ color:#E02424; }

    /* Tabs */
    [data-baseweb="tab-list"]{ gap:3px; border-bottom:1px solid var(--line); }
    [data-baseweb="tab-list"] button{ border-radius:9px 9px 0 0; padding:7px 13px; color:var(--muted); font-weight:600; font-size:.85rem; }
    [data-baseweb="tab-list"] button:hover{ background:var(--blue-soft); color:var(--navy); }
    [data-baseweb="tab-list"] button[aria-selected="true"]{ background:var(--blue-soft); color:var(--navy); border-bottom:3px solid var(--blue); font-weight:700; }

    /* Dataframe */
    [data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:10px; overflow:hidden; box-shadow:0 5px 14px rgba(16,40,90,.05); }

    /* Metric widget (fallback) */
    [data-testid="stMetric"]{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 14px; box-shadow:0 5px 14px rgba(16,40,90,.05); }
    [data-testid="stMetricLabel"] p{ color:var(--muted); font-weight:600; font-size:.8rem; }
    [data-testid="stMetricValue"]{ color:var(--navy); font-weight:800; font-size:1.4rem; }

    /* Buttons & inputs */
    .stButton>button, .stDownloadButton>button{ background:var(--navy); color:#fff; border:none; border-radius:9px; padding:.45rem .9rem; font-weight:600; }
    .stButton>button:hover{ background:var(--blue); color:#fff; }
    hr{ border-color:var(--line); }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. FUNÇÕES DE TRATAMENTO E UI
# ==========================================
def manter_apenas_numeros(documento):
    if pd.isna(documento) or str(documento).strip().lower() in ['nan', 'none', '']: return np.nan
    apenas_numeros = re.sub(r'\D', '', str(documento))
    if apenas_numeros: return apenas_numeros.zfill(14) if len(apenas_numeros) > 11 else apenas_numeros.zfill(11)
    return np.nan

def tratar_data_segura(val):
    if pd.isna(val) or val is None or str(val).strip() == '': return None
    try:
        data_obj = pd.to_datetime(val).tz_localize(None)
        return data_obj.strftime('%d/%m/%Y')
    except: return str(val).split('T')[0]

def ler_csv_seguro(caminho):
    """
    Lê um arquivo CSV tentando vários encodings E separadores. A heurística é:
    testa todas as combinações e fica com aquela que produz MAIS COLUNAS — é o sinal
    de que o separador correto foi detectado (separador errado junta tudo em poucas colunas).
    Em último caso, tenta novamente ignorando linhas mal-formadas.
    """
    # Pre-check: detecta arquivo XLSX disfarçado de CSV (assinatura PK no início)
    try:
        with open(caminho, 'rb') as f:
            primeiros_bytes = f.read(4)
        if primeiros_bytes.startswith(b'PK\x03\x04') or primeiros_bytes.startswith(b'PK!'):
            raise ValueError(
                f"O arquivo '{os.path.basename(caminho)}' é um arquivo Excel (.xlsx) "
                f"renomeado para .csv — eles têm formatos internos diferentes e não são "
                f"compatíveis. Use o botão '📸 Capturar Atrasos do Dia 01' para gerar um "
                f"CSV de verdade (via download OU via Copiar e Colar)."
            )
    except (OSError, IOError):
        pass  # se não conseguir ler para checar, segue o fluxo normal
    
    encodings_para_tentar = ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1', 'iso-8859-1']
    separadores_para_tentar = [',', ';', '\t']
    melhor_df = None
    melhor_num_colunas = 1
    ultimo_erro = None
    
    # Primeira passada: testa todas as combinações e fica com a que tem MAIS colunas
    for enc in encodings_para_tentar:
        for sep in separadores_para_tentar:
            try:
                df = pd.read_csv(caminho, encoding=enc, sep=sep)
                if len(df.columns) > melhor_num_colunas:
                    melhor_df = df
                    melhor_num_colunas = len(df.columns)
            except (UnicodeDecodeError, UnicodeError, pd.errors.ParserError) as e:
                ultimo_erro = e
                continue
    
    if melhor_df is not None:
        return melhor_df
    
    # Segunda passada (último recurso): ignora linhas mal-formadas
    for enc in encodings_para_tentar:
        for sep in separadores_para_tentar:
            try:
                df = pd.read_csv(caminho, encoding=enc, sep=sep, on_bad_lines='skip', engine='python')
                if len(df.columns) > melhor_num_colunas and len(df) > 0:
                    melhor_df = df
                    melhor_num_colunas = len(df.columns)
            except Exception as e:
                ultimo_erro = e
                continue
    
    if melhor_df is not None:
        return melhor_df
    
    raise ValueError(
        f"Não foi possível ler o arquivo {caminho}. "
        f"Verifique se o arquivo está intacto e usa vírgula ou ponto-e-vírgula como separador. "
        f"Último erro: {ultimo_erro}"
    )

def df_para_excel_bytes(df, sheet_name='Dados'):
    """Converte DataFrame em bytes Excel para download_button."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()

def exibir_extrato_resumido(df_alvo, key_download=None):
    if df_alvo.empty:
        st.info("Nenhum contrato encontrado para este filtro.")
        return
    df_ex = df_alvo.copy()
    df_ex['Data_Vencimento_MP'] = df_ex['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
    colunas = ['FOZ_CodigoItem__c', 'Account.Name', 'Status_MP_Real', 'Data_Vencimento_MP', 'AGING_MP', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento']
    
    if 'Prestador_CEP' in df_ex.columns:
        colunas.insert(2, 'Prestador_CEP')
        
    df_show = df_ex[colunas].rename(columns={
        'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente', 'Status_MP_Real': 'Status da Ação',
        'Data_Vencimento_MP': 'Vencimento MP', 'AGING_MP': 'Aging', 'Numero_Caso': 'Nº OS',
        'Tipo_Servico': 'Tipo de Serviço', 'Data_Agendamento': 'Data OS (Agendada)', 'Prestador_CEP': 'Grade/Franquia'
    }).fillna({'Nº OS': '-', 'Tipo de Serviço': '-', 'Data OS (Agendada)': '-', 'Grade/Franquia': 'Não Mapeado'})
    
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    
    if key_download:
        st.download_button(
            label="📥 Baixar extrato (Excel)",
            data=df_para_excel_bytes(df_show, 'Extrato'),
            file_name=f"extrato_{key_download}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            key=f"dl_{key_download}"
        )

def selecionar_woli(wolis):
    """Regra da OS (mesma do casosporitem): ignora WOLIs Canceladas/Reagendadas e
    retorna a valida mais recente (a subquery ja vem ORDER BY CreatedDate DESC).
    Fallback: a mais recente de qualquer status. Retorna None se nao houver WOLI."""
    if not wolis:
        return None
    status_ignorados = ('Cancelado', 'Reagendado')
    validas = [w for w in wolis if w.get('Status') not in status_ignorados]
    return validas[0] if validas else wolis[0]


# ==========================================
# 3. CONEXÃO E PROCESSAMENTO
# ==========================================
# IMPORTANTE: cache_resource (não cache_data) — assim a base do Salesforce é UMA SÓ
# para todos os usuários do app. Reduz drasticamente o consumo de memória quando
# múltiplas pessoas usam o painel ao mesmo tempo.
@st.cache_resource(ttl=21600, show_spinner=False)
def carregar_dados_completos():
    sf = Salesforce(
        username=st.secrets["salesforce"]["username"], 
        password=st.secrets["salesforce"]["password"],           
        security_token=st.secrets["salesforce"]["security_token"]      
    )
    
    query_ativos = """
    SELECT 
        FOZ_CodigoItem__c, FOZ_PlanoManutencao__c, Status, SerialNumber, Name, InstallDate, 
        FOZ_Contrato_Anterior__c, FOZ_DataUltimaMP__c, FOZ_DataProximaMP__c, 
        FOZ_ValorTotal__c, AccountId, Account.Name, Account.FOZ_StatusPosicaoFinanceira__c, 
        Account.CNPJ__c, Account.FOZ_Classificacao__c,
        FOZ_EndFranquiaForm__c, FOZ_EnderecoEntrega__r.FOZ_CEP__c
    FROM Asset
    WHERE Status = 'Ativo-Em Operação'
    """
    query_contatos = "SELECT AccountId, Account.FOZ_CNPJ__c FROM Contact WHERE Account.FOZ_CNPJ__c != null"
    query_os = """
    SELECT Case.FOZ_Asset__r.FOZ_CodigoItem__c, Case.CaseNumber, Case.Status,
           Case.FOZ_TipoSolicitacao__c, FOZ_Agendado_Data_Periodo__c, FOZ_Tipo_de_Servico__c,
           (SELECT LineItemNumber, toLabel(Status) FROM WorkOrderLineItems ORDER BY CreatedDate DESC LIMIT 200)
    FROM WorkOrder WHERE Case.Type = 'OS' AND Case.Status != 'Cancelado' AND Case.Status != 'Fechado' AND Status != 'Cancelado' AND Status != 'Fechado'
    """
    # LGPD: as queries de telefones (Contact / AccountContactRelation) foram REMOVIDAS
    # do painel online. Dados pessoais de contato não trafegam para o Streamlit Cloud.
    # O mailing completo com telefones é gerado LOCALMENTE via gerar_mailing_local.py.
    # OS de Manutenção Preventiva — usada para o Funil de Conversão Mensal.
    # A MP é um CASE (Type='OS', FOZ_TipoSolicitacao__c='MANUTENÇÃO PREVENTIVA').
    # Consultamos direto do Case porque o Asset está no campo customizado FOZ_Asset__c
    # (o AssetId padrão do WorkOrder vem vazio). O código do item vem de FOZ_Asset__r.FOZ_CodigoItem__c.
    # ATENÇÃO: LAST_N_MONTHS:12 NÃO inclui o mês corrente no Salesforce — ele vai até o
    # último dia do mês passado. Por isso adicionamos OR CreatedDate = THIS_MONTH, senão
    # o funil do mês atual fica sempre zerado (as OS recém-criadas ficam de fora).
    query_os_mp = """
    SELECT 
        FOZ_Asset__r.FOZ_CodigoItem__c, Status, CreatedDate
    FROM Case 
    WHERE Type = 'OS' 
      AND FOZ_TipoSolicitacao__c = 'MANUTENÇÃO PREVENTIVA'
      AND FOZ_Asset__c != null
      AND (CreatedDate = LAST_N_MONTHS:12 OR CreatedDate = THIS_MONTH)
    """
    
    registros_ativos = sf.query_all(query_ativos).get('records', [])
    registros_contatos = sf.query_all(query_contatos).get('records', [])
    registros_os = sf.query_all(query_os).get('records', [])
    registros_os_mp = sf.query_all(query_os_mp).get('records', [])
    
    df_ativos = pd.json_normalize(registros_ativos)
    df_contatos = pd.json_normalize(registros_contatos)
    
    # Libera as listas de dicts já que viraram DataFrames (cada lista de ~50k items
    # de dicts Python ocupa centenas de MB; o DataFrame equivalente ocupa muito menos).
    # Mantemos apenas registros_os, que ainda é iterado abaixo.
    del registros_ativos, registros_contatos
    
    hoje = datetime.now(FUSO_BR)
    mes_atual = hoje.month
    ano_atual = hoje.year
    hoje_data = hoje.date()

    # Contagem de falhas de parse para diagnóstico
    falhas_parse_data = 0

    lista_os = []
    for reg in registros_os:
        caso = reg.get('Case') or {}; asset = caso.get('FOZ_Asset__r') or {}
        data_agendamento_raw = reg.get('FOZ_Agendado_Data_Periodo__c')
        tipo_servico = reg.get('FOZ_Tipo_de_Servico__c')
        agendado_mes_atual = False; agendado_hoje = False; tem_data = 1 if data_agendamento_raw else 0
        data_obj = None

        if data_agendamento_raw:
            try:
                data_limpa = str(data_agendamento_raw).split(' -')[0].strip()
                data_obj = pd.to_datetime(data_limpa, format='%d/%m/%Y').date()
                if data_obj.month == mes_atual and data_obj.year == ano_atual and data_obj >= hoje_data: agendado_mes_atual = True
                if data_obj == hoje_data: agendado_hoje = True
            except Exception:
                falhas_parse_data += 1
                data_obj = None

        # Regra de WOLI aplicada a OS: status do item de servico valido mais recente
        woli_sel = selecionar_woli((reg.get('WorkOrderLineItems') or {}).get('records'))
        status_item_servico = woli_sel.get('Status') if woli_sel else None
        mes_ag = data_obj.month if data_obj else None
        ano_ag = data_obj.year if data_obj else None

        lista_os.append({
            'CodigoItem': asset.get('FOZ_CodigoItem__c'), 'Tem_OS_Aberta': True,
            'Agendado_Mes_Atual': agendado_mes_atual, 'Agendado_Hoje': agendado_hoje,
            'Tem_Data': tem_data, 'Numero_Caso': caso.get('CaseNumber'),
            'Tipo_Servico': tipo_servico, 'Data_Agendamento_Raw': data_agendamento_raw,
            'Tipo_Solicitacao': caso.get('FOZ_TipoSolicitacao__c'),
            'Status_Item_Servico': status_item_servico,
            'Data_Agendamento_Obj': data_obj,
            'Mes_Agendamento': mes_ag, 'Ano_Agendamento': ano_ag
        })
    
    df_os = pd.DataFrame(lista_os)

    # OS de MP com data agendada (alimenta a aba 'MP Agendado' — quebra por mês da visita).
    # Construído a partir da lista COMPLETA (antes do dedup por item).
    if not df_os.empty and 'Tipo_Solicitacao' in df_os.columns:
        df_os_mp_agendado = df_os[
            (df_os['Tipo_Solicitacao'] == 'MANUTENÇÃO PREVENTIVA') &
            (df_os['Data_Agendamento_Obj'].notna())
        ].copy()
    else:
        df_os_mp_agendado = pd.DataFrame()
    if not df_os_mp_agendado.empty:
        _dt_ag = pd.to_datetime(df_os_mp_agendado['Data_Agendamento_Obj'], errors='coerce')
        df_os_mp_agendado['Data_Agendamento'] = _dt_ag.dt.strftime('%d/%m/%Y')
        df_os_mp_agendado['Mes_Agendamento'] = _dt_ag.dt.month
        df_os_mp_agendado['Ano_Agendamento'] = _dt_ag.dt.year
        df_os_mp_agendado = df_os_mp_agendado[[
            'CodigoItem', 'Numero_Caso', 'Tipo_Servico', 'Status_Item_Servico',
            'Data_Agendamento', 'Mes_Agendamento', 'Ano_Agendamento'
        ]]
    del lista_os, registros_os  # libera memória das listas iteradas
    if not df_os.empty:
        df_os = df_os.sort_values(by=['Agendado_Mes_Atual', 'Tem_Data'], ascending=[False, False]).drop_duplicates(subset=['CodigoItem'])
    
    col_cnpj_ativos = 'Account.CNPJ__c'; col_cnpj_contatos = 'Account.FOZ_CNPJ__c'
    df_ativos[col_cnpj_ativos] = df_ativos[col_cnpj_ativos].apply(manter_apenas_numeros)
    df_contatos[col_cnpj_contatos] = df_contatos[col_cnpj_contatos].apply(manter_apenas_numeros)
    df_contatos_unicos = df_contatos.drop_duplicates(subset=[col_cnpj_contatos], keep='first')
    
    df = pd.merge(df_ativos, df_contatos_unicos, left_on=col_cnpj_ativos, right_on=col_cnpj_contatos, how='left')
    
    if not df_os.empty:
        df = pd.merge(df, df_os, left_on='FOZ_CodigoItem__c', right_on='CodigoItem', how='left')
        df['Tem_OS_Aberta'] = df['Tem_OS_Aberta'].fillna(False); df['Agendado_Mes_Atual'] = df['Agendado_Mes_Atual'].fillna(False)
        df['Agendado_Hoje'] = df['Agendado_Hoje'].fillna(False); df['Data_Agendamento'] = df['Data_Agendamento_Raw'].apply(tratar_data_segura)
    else:
        df['Tem_OS_Aberta'] = False; df['Agendado_Mes_Atual'] = False; df['Agendado_Hoje'] = False
        df['Numero_Caso'] = None; df['Tipo_Servico'] = None; df['Data_Agendamento'] = None
    
    df['FOZ_DataProximaMP__c'] = pd.to_datetime(df['FOZ_DataProximaMP__c'], errors='coerce').dt.tz_localize(None)
    df['Ano_MP'] = df['FOZ_DataProximaMP__c'].dt.year; df['Mes_MP'] = df['FOZ_DataProximaMP__c'].dt.month
    
    # Usar o "hoje" no fuso de SP (consistente com o cálculo de Agendado_Mes_Atual/Agendado_Hoje)
    hoje_limpo = pd.Timestamp(hoje.replace(tzinfo=None))
    mask_notnull = df['FOZ_DataProximaMP__c'].notnull()
    df['Meses_Diff'] = np.nan
    df.loc[mask_notnull, 'Meses_Diff'] = (hoje_limpo.year - df.loc[mask_notnull, 'Ano_MP']) * 12 + (hoje_limpo.month - df.loc[mask_notnull, 'Mes_MP'])
    
    # -----------------------------------------------------------------
    # REGRA DE NEGÓCIO:
    # Um contrato é "ATRASADO" assim que a próxima MP passa da data de vencimento.
    # Carência de 30 dias após o vencimento (regra restaurada): venceu dia 15, fica EM DIA até o dia 15 do mês seguinte.
    # No PRÓPRIO dia do vencimento (dia 15) o contrato ainda está EM DIA.
    # Equivale ao SQL: (FOZ_DataProximaMP__c + 30 dias) < TODAY()
    #
    # Comparação feita por DATA pura (sem hora): normalizamos o vencimento para
    # meia-noite e comparamos com a data de hoje (também à meia-noite). Sem isso,
    # um contrato que vence hoje seria marcado como atrasado já no meio do dia.
    # -----------------------------------------------------------------
    hoje_data_ts = pd.Timestamp(hoje.date())  # hoje à meia-noite, no fuso de SP
    # Carencia de 30 dias restaurada: o contrato so fica ATRASADO 30 dias APOS o
    # vencimento. Ex.: venceu 15/06 -> em 15/07 ainda EM DIA -> em 16/07 ATRASADO.
    _prazo_atraso = df['FOZ_DataProximaMP__c'].dt.normalize() + pd.Timedelta(days=CARENCIA_ATRASO_DIAS)
    df['Atraso_Base'] = np.where(
        _prazo_atraso < hoje_data_ts,
        AtrasoBase.ATRASADO,
        AtrasoBase.EM_DIA
    )
    
    mask_desinstalacao = (df['Atraso_Base'] == AtrasoBase.ATRASADO) & (df['Tipo_Servico'].str.contains('DESINSTALA', case=False, na=False))
    df.loc[mask_desinstalacao, 'Atraso_Base'] = AtrasoBase.ISENTO
    
    # ----- Vetorização de definir_status_final (substitui df.apply linha-a-linha) -----
    # Mesma regra de negócio: EM DIA -> EM DIA / ISENTO -> DESCONSIDERADO / 
    # ATRASADO + Agendado_Mes_Atual -> PROGRAMADO / senão CRÍTICO
    cond_status = [
        df['Atraso_Base'] == AtrasoBase.EM_DIA,
        df['Atraso_Base'] == AtrasoBase.ISENTO,
        (df['Atraso_Base'] == AtrasoBase.ATRASADO) & (df['Agendado_Mes_Atual'] == True),
    ]
    valores_status = [StatusMP.EM_DIA, StatusMP.DESCONSIDERADO, StatusMP.PROGRAMADO]
    df['Status_MP_Real'] = np.select(cond_status, valores_status, default=StatusMP.CRITICO)
    
    df['Dias_Atraso'] = (hoje_data_ts - df['FOZ_DataProximaMP__c'].dt.normalize()).dt.days
    
    # ----- Vetorização de classificar_aging (substitui df.apply linha-a-linha) -----
    # Mesmas faixas: 0-30 / 30-60 / 60-90 / 90-120 / 120-150 / 150+ / EM DIA
    dias = df['Dias_Atraso']
    cond_aging = [
        (df['Atraso_Base'] == AtrasoBase.EM_DIA) | dias.isna(),
        dias <= 30,
        dias <= 60,
        dias <= 90,
        dias <= 120,
        dias <= 150,
    ]
    valores_aging = ['G) EM DIA', 'A) 0-30', 'B) 30-60', 'C) 60-90', 'D) 90-120', 'E) 120-150']
    df['AGING_MP'] = np.select(cond_aging, valores_aging, default='F) 150+')
    
    col_financeira = 'Account.FOZ_StatusPosicaoFinanceira__c'
    if col_financeira in df.columns:
        df['Status_Financeiro'] = df[col_financeira].fillna('Não Informado')
        df['Status_Financeiro'] = df['Status_Financeiro'].apply(
            lambda x: StatusFin.ADIMPLENTE if 'Adimplente' in str(x) else (StatusFin.INADIMPLENTE if 'Inadimplente' in str(x) else str(x))
        )
    else:
        df['Status_Financeiro'] = 'Não Informado'
        
    df['FOZ_EndFranquiaForm__c'] = df['FOZ_EndFranquiaForm__c'].fillna('NÃO INFORMADA')
    
    # Classificação do contrato (utilizada como filtro global na UI).
    # O campo vive no objeto Account no Salesforce, então o pd.json_normalize achata como
    # 'Account.FOZ_Classificacao__c'. Mantemos uma lista de fallback para robustez caso
    # o modelo de dados mude no futuro.
    candidatos_classificacao = [
        'Account.FOZ_Classificacao__c',
        'FOZ_Classificacao__c',
        'FOZ_Classificacao_Contrato__c',
        'FOZ_ClassificacaoContrato__c',
        'FOZ_Tipo_Contrato__c',
        'FOZ_TipoContrato__c',
    ]
    coluna_classif_encontrada = next((c for c in candidatos_classificacao if c in df.columns), None)
    
    if coluna_classif_encontrada:
        df['Classificacao'] = df[coluna_classif_encontrada].fillna('Não Classificado').astype(str).str.strip()
        df.loc[df['Classificacao'] == '', 'Classificacao'] = 'Não Classificado'
        df.attrs['classif_origem'] = coluna_classif_encontrada
    else:
        # Campo de classificação não encontrado: cria vazio para o app continuar funcionando
        df['Classificacao'] = 'Não Classificado'
        df.attrs['classif_origem'] = None
    
    # CEP preservado como string (mantém zeros à esquerda) e numérico apenas para comparação de range
    df['CEP_Limpo'] = df['FOZ_EnderecoEntrega__r.FOZ_CEP__c'].astype(str).str.replace(r'\D', '', regex=True)
    df['CEP_Num'] = pd.to_numeric(df['CEP_Limpo'], errors='coerce')
    
    # Quantidade de contratos (ativos) que cada cliente possui — útil para o mailing
    # e para qualquer extrato. Aparece como nova coluna em cada linha da base.
    qtd_contratos_por_cnpj = df.groupby('Account.CNPJ__c')['FOZ_CodigoItem__c'].count()
    df['Qtd_Contratos_Cliente'] = df['Account.CNPJ__c'].map(qtd_contratos_por_cnpj).fillna(1).astype(int)
    
    # ----------------------------------------------------------
    # OTIMIZAÇÃO DE MEMÓRIA: converte colunas categóricas (poucos valores únicos
    # repetidos milhares de vezes) para o tipo 'category', que reduz drasticamente
    # o footprint na RAM. Importante quando o painel hospeda vários usuários.
    # ----------------------------------------------------------
    cols_categoricas = [
        'Status_MP_Real', 'Atraso_Base', 'AGING_MP', 'Status_Financeiro',
        'Classificacao', 'FOZ_EndFranquiaForm__c', 'Status'
    ]
    for col in cols_categoricas:
        if col in df.columns:
            df[col] = df[col].astype('category')
    
    # LGPD: a montagem da tabela de telefones foi removida do painel online.
    # Telefones de clientes são tratados apenas no gerador local de mailing.
    
    # ==========================================
    # OS DE MP (para o Funil mensal)
    # ==========================================
    # Monta um DataFrame com as OS de manutenção preventiva, normalizando a data de
    # criação (CreatedDate) para identificar em qual mês a OS foi agendada, e o status
    # do caso para identificar baixas com sucesso. Vetorizado via json_normalize (mais
    # rápido que loop Python para milhares de registros).
    if registros_os_mp:
        df_os_mp = pd.json_normalize(registros_os_mp)
        # Renomeia colunas para nomes simples. Como agora consultamos direto da tabela Case,
        # o código do asset vem como 'FOZ_Asset__r.FOZ_CodigoItem__c' (sem prefixo 'Case.').
        rename_os = {
            'FOZ_Asset__r.FOZ_CodigoItem__c': 'CodigoItem',
            'Status': 'Status_Caso',
            'CreatedDate': 'CreatedDate',
        }
        df_os_mp = df_os_mp.rename(columns=rename_os)
        # Mantém só o necessário
        cols_keep = [c for c in ['CodigoItem', 'Status_Caso', 'CreatedDate'] if c in df_os_mp.columns]
        df_os_mp = df_os_mp[cols_keep]
        # CreatedDate vem do Salesforce em UTC (ex: 2026-06-05T14:41:24.000+0000).
        # Converte para o fuso de Brasília e depois remove o tz, para comparar de forma
        # consistente com a data do snapshot (que está em horário de Brasília tz-naive).
        # IMPORTANTE: usar utc=True no parse evita o erro de tz_localize em série já tz-aware,
        # que estava resultando em datas nulas (NaT) e zerando o filtro de período.
        dt_utc = pd.to_datetime(df_os_mp['CreatedDate'], errors='coerce', utc=True)
        df_os_mp['CreatedDate'] = dt_utc.dt.tz_convert(FUSO_BR).dt.tz_localize(None)
    else:
        df_os_mp = pd.DataFrame(columns=['CodigoItem', 'Status_Caso', 'CreatedDate'])
    del registros_os_mp
    
    # Metadados úteis para a UI
    df.attrs['timestamp_carga'] = hoje.strftime('%d/%m/%Y %H:%M:%S')
    df.attrs['falhas_parse_data'] = falhas_parse_data
    df.attrs['total_registros'] = len(df)
    df.attrs['os_mp'] = df_os_mp
    df.attrs['os_mp_agendado'] = df_os_mp_agendado
        
    return df

@st.cache_resource(show_spinner=False)
def processar_arquivos_estaveis(bytes_range_cep, bytes_depara):
    """
    Processa os arquivos de cadastro estáveis (Range CEP e De-Para). Esses arquivos
    mudam pouco e ficam na pasta do app. Cacheado por hash dos bytes.
    """
    df_ranges = pd.read_excel(io.BytesIO(bytes_range_cep), sheet_name=0)
    df_ranges.columns = df_ranges.columns.str.strip()
    
    df_depara = pd.read_excel(io.BytesIO(bytes_depara), sheet_name=0)
    df_depara.columns = df_depara.columns.str.strip()
    
    df_ranges['Cep_De_Num'] = df_ranges['Cep "De"'].astype(str).str.replace(r'\D', '', regex=True).astype(int)
    df_ranges['Cep_Ate_Num'] = df_ranges['Cep "Até"'].astype(str).str.replace(r'\D', '', regex=True).astype(int)
    
    df_depara['Grade_Match'] = df_depara['Franquia Relatório Capacidade'].str.extract(r'(R\d{2})')
    
    # Diagnóstico: detecta chaves duplicadas no DE-PARA que estariam sendo
    # silenciosamente sobrescritas (a segunda ocorrência substitui a primeira).
    duplicatas_depara = []
    dict_depara = {}
    for _, row in df_depara.iterrows():
        chave = (str(row['Franquia Range CEP']).strip(), str(row['Grade_Match']).strip())
        valor_atual = str(row['Franquia Relatório Capacidade']).strip()
        if chave in dict_depara and dict_depara[chave] != valor_atual:
            duplicatas_depara.append({
                'Franquia Range CEP': chave[0],
                'Grade': chave[1],
                'Mapeamento Anterior (perdido)': dict_depara[chave],
                'Mapeamento Atual (vencedor)': valor_atual
            })
        dict_depara[chave] = valor_atual
    
    return df_ranges, dict_depara, duplicatas_depara

@st.cache_resource(show_spinner=False)
def processar_capacidade(bytes_capacidade):
    """
    Processa o arquivo de Capacidade (foto operacional que muda toda hora — vem
    de upload manual em cada aba que precisa dele). Cacheado por hash dos bytes
    para que o mesmo arquivo subido em abas diferentes seja reaproveitado.
    """
    df_cap = pd.read_excel(io.BytesIO(bytes_capacidade), sheet_name=0)
    df_cap.columns = df_cap.columns.str.strip()
    
    df_cap['Data do Registro'] = pd.to_datetime(df_cap['Data do Registro'], format='%d/%m/%Y', errors='coerce')
    hoje_limpo = pd.to_datetime(datetime.now(FUSO_BR).date())
    df_cap_futuro = df_cap[df_cap['Data do Registro'] >= hoje_limpo].copy()
    df_cap_mp = df_cap_futuro[df_cap_futuro['Serviços'].astype(str).str.contains('MP', case=False, na=False)].copy()
    df_cap_mp['Disponível'] = pd.to_numeric(df_cap_mp['Disponível'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
    
    # -----------------------------------------------------------------
    # REGRA OPERACIONAL DE JANELA DE ATENDIMENTO
    # -----------------------------------------------------------------
    # Não há atendimento de:
    #   - Domingo: nenhuma janela
    #   - Sábado à tarde: apenas a janela "Período da Tarde"
    # Linhas que caem nesses casos têm o "Disponível" zerado (a linha permanece
    # na base para auditoria, mas não é contabilizada nos indicadores).
    # -----------------------------------------------------------------
    
    def _normalizar(texto):
        """Remove acentos, deixa em maiúsculas e tira espaços extras. Robusto a variações de digitação."""
        if pd.isna(texto):
            return ''
        s = str(texto).strip().upper()
        substituicoes = str.maketrans('ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC')
        return s.translate(substituicoes)
    
    # Dia da semana: prioriza a coluna 'Dia' do arquivo; fallback para o cálculo via Data do Registro
    if 'Dia' in df_cap_mp.columns:
        df_cap_mp['_Dia_Norm'] = df_cap_mp['Dia'].apply(_normalizar)
    else:
        df_cap_mp['_Dia_Norm'] = ''
    # dayofweek: 0=segunda, 1=terça, ..., 5=sábado, 6=domingo
    df_cap_mp['_DiaSemana_Num'] = df_cap_mp['Data do Registro'].dt.dayofweek
    
    # Janela normalizada
    if 'Janela de atendimento' in df_cap_mp.columns:
        df_cap_mp['_Janela_Norm'] = df_cap_mp['Janela de atendimento'].apply(_normalizar)
    else:
        df_cap_mp['_Janela_Norm'] = ''
    
    # Máscaras (as duas verificações são combinadas via OR para robustez)
    eh_domingo = (df_cap_mp['_Dia_Norm'] == 'DOMINGO') | (df_cap_mp['_DiaSemana_Num'] == 6)
    eh_sabado = (df_cap_mp['_Dia_Norm'] == 'SABADO') | (df_cap_mp['_DiaSemana_Num'] == 5)
    eh_tarde = df_cap_mp['_Janela_Norm'].str.contains('TARDE', na=False)
    
    mascara_sem_atendimento = eh_domingo | (eh_sabado & eh_tarde)
    
    # Aplica a regra: zera o Disponível nas linhas que violam a janela operacional
    df_cap_mp.loc[mascara_sem_atendimento, 'Disponível'] = 0
    
    # Limpa colunas auxiliares antes de retornar
    df_cap_mp = df_cap_mp.drop(columns=['_Dia_Norm', '_DiaSemana_Num', '_Janela_Norm'])
    
    capacidade_agrupada = df_cap_mp.groupby('Prestador de Serviço')['Disponível'].sum().reset_index(name='Capacidade Disponível')
    
    return df_cap_mp, capacidade_agrupada

def encontrar_prestador_factory(df_ranges, dict_depara):
    """Closure para a função de busca de prestador (mantém regra original)."""
    def encontrar_prestador(cep_num):
        if pd.isna(cep_num): return None
        match = df_ranges[(df_ranges['Cep_De_Num'] <= cep_num) & (df_ranges['Cep_Ate_Num'] >= cep_num)]
        if not match.empty:
            franquia = str(match['Nome Service Area'].values[0]).strip()
            grade = str(match['GRADE'].values[0]).strip()
            return dict_depara.get((franquia, grade))
        return None
    return encontrar_prestador

def diagnosticar_cep(cep_num, df_ranges, dict_depara):
    """
    Versão verbose: retorna um dicionário detalhado mostrando exatamente o que aconteceu
    no mapeamento daquele CEP. Útil para troubleshoot quando um contrato aparece como
    'Sem Cobertura' ou foi associado a uma franquia que não corresponde à realidade.
    """
    resultado = {
        'cep_input': cep_num,
        'cep_valido': not pd.isna(cep_num),
        'ranges_encontrados': pd.DataFrame(),
        'qtd_ranges': 0,
        'tem_sobreposicao': False,
        'mapeamento_aplicado': None,
        'franquia_escolhida': None,
        'grade_escolhida': None,
        'depara_existe': False,
        'motivo_falha': None,
    }
    
    if pd.isna(cep_num):
        resultado['motivo_falha'] = "CEP nulo ou inválido."
        return resultado
    
    match = df_ranges[(df_ranges['Cep_De_Num'] <= cep_num) & (df_ranges['Cep_Ate_Num'] >= cep_num)]
    resultado['ranges_encontrados'] = match
    resultado['qtd_ranges'] = len(match)
    
    if match.empty:
        resultado['motivo_falha'] = (
            "CEP não está em nenhum range cadastrado no arquivo Range CEP.xlsx. "
            "Provável causa: faixa de CEP ainda não mapeada para nenhuma Service Area."
        )
        return resultado
    
    if len(match) > 1:
        resultado['tem_sobreposicao'] = True
    
    # Aplica a mesma regra do encontrar_prestador (pega o primeiro match)
    franquia = str(match['Nome Service Area'].values[0]).strip()
    grade = str(match['GRADE'].values[0]).strip()
    resultado['franquia_escolhida'] = franquia
    resultado['grade_escolhida'] = grade
    
    chave = (franquia, grade)
    if chave in dict_depara:
        resultado['depara_existe'] = True
        resultado['mapeamento_aplicado'] = dict_depara[chave]
    else:
        resultado['motivo_falha'] = (
            f"CEP cai no range da Service Area '{franquia}' com Grade '{grade}', "
            f"mas essa combinação NÃO existe no DE-PARA do arquivo Capacidade.xlsx. "
            f"Por isso o contrato fica 'Sem Cobertura' mesmo tendo range cadastrado."
        )
    
    return resultado

@st.cache_resource(show_spinner=False)
def construir_mapa_cep_prestador(ceps_unicos_tuple, df_ranges, dict_depara):
    """
    Constrói um dicionário {cep_num: prestador} a partir de CEPs únicos.
    Cacheado: como os CEPs vêm do Salesforce (cache de 6h) e os ranges vêm dos
    arquivos uploadados (cache por hash), esta função só roda quando uma das
    duas fontes muda. O resultado é reusado em TODAS as interações com filtros.
    """
    encontrar_prestador = encontrar_prestador_factory(df_ranges, dict_depara)
    return {cep: encontrar_prestador(cep) for cep in ceps_unicos_tuple if pd.notna(cep)}

# ==========================================
# 4. CARREGAMENTO DOS ARQUIVOS DE APOIO DA PASTA
# ==========================================
# Range CEP, De-Para e Capacidade são lidos automaticamente da pasta do app.
# Para atualizar, basta substituir o arquivo na pasta e clicar em "Atualizar".
PASTA_APP = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_RANGE_CEP = os.path.join(PASTA_APP, 'Range CEP.xlsx')
ARQUIVO_DEPARA = os.path.join(PASTA_APP, 'De-Para.xlsx')
ARQUIVO_CAPACIDADE = os.path.join(PASTA_APP, 'Capacidade.xlsx')

bytes_range_cep = None
bytes_depara = None
bytes_capacidade = None
ts_capacidade = None
erro_arquivos_estaveis = None

if os.path.exists(ARQUIVO_RANGE_CEP) and os.path.exists(ARQUIVO_DEPARA):
    try:
        with open(ARQUIVO_RANGE_CEP, 'rb') as f:
            bytes_range_cep = f.read()
        with open(ARQUIVO_DEPARA, 'rb') as f:
            bytes_depara = f.read()
    except Exception as e:
        erro_arquivos_estaveis = f"Erro ao ler arquivos de cadastro da pasta: {e}"
else:
    arquivos_faltantes = []
    if not os.path.exists(ARQUIVO_RANGE_CEP):
        arquivos_faltantes.append("Range CEP.xlsx")
    if not os.path.exists(ARQUIVO_DEPARA):
        arquivos_faltantes.append("De-Para.xlsx")
    erro_arquivos_estaveis = (
        f"Arquivo(s) de cadastro ausente(s) na pasta do app: {', '.join(arquivos_faltantes)}. "
        f"As análises que dependem de capacidade ficarão desabilitadas até o cadastro estar completo."
    )

# Capacidade: lida da pasta também, com timestamp para mostrar quando foi atualizada
if os.path.exists(ARQUIVO_CAPACIDADE):
    try:
        with open(ARQUIVO_CAPACIDADE, 'rb') as f:
            bytes_capacidade = f.read()
        # Captura a data/hora de modificação do arquivo para exibir na UI
        ts_mod = os.path.getmtime(ARQUIVO_CAPACIDADE)
        ts_capacidade = datetime.fromtimestamp(ts_mod, tz=FUSO_BR).strftime('%d/%m/%Y às %H:%M')
    except Exception as e:
        st.warning(f"⚠️ Erro ao ler Capacidade.xlsx da pasta: {e}")

# Processa os arquivos estáveis uma única vez (cacheado pelo hash dos bytes)
df_ranges = None
dict_depara = None
duplicatas_depara = []
cadastro_ok = False
if bytes_range_cep is not None and bytes_depara is not None:
    try:
        df_ranges, dict_depara, duplicatas_depara = processar_arquivos_estaveis(bytes_range_cep, bytes_depara)
        cadastro_ok = True
    except Exception as e:
        erro_arquivos_estaveis = f"Erro ao processar arquivos de cadastro: {e}"

# ==========================================
# 4.1. HELPER DE LEITURA DA CAPACIDADE (lida da pasta, retorna dados processados)
# ==========================================
def obter_capacidade_da_sessao(chave_aba):
    """
    Retorna os dados de capacidade (df_cap_mp, capacidade_agrupada), lidos automaticamente
    da pasta do app via Capacidade.xlsx. Também exibe uma linha discreta com a data/hora
    de modificação do arquivo, para o usuário saber quando a foto foi atualizada.
    
    Retorna: (df_cap_mp, capacidade_agrupada) ou (None, None) se o arquivo não existe.
    """
    if bytes_capacidade is None:
        st.warning(
            "⚠️ O arquivo **Capacidade.xlsx** não foi encontrado na pasta do app. "
            "Substitua o arquivo na pasta e clique em **🔄 Atualizar** no topo para recarregar."
        )
        return None, None
    
    # Exibe data/hora de atualização do arquivo
    st.caption(f"📂 Capacidade lida do arquivo da pasta &nbsp;•&nbsp; atualizado em **{ts_capacidade}**")
    
    try:
        return processar_capacidade(bytes_capacidade)
    except Exception as e:
        st.error(f"Erro ao processar o arquivo de Capacidade: {e}")
        return None, None

# ==========================================
# 5. CARGA DOS DADOS
# ==========================================
with st.spinner("Conectando ao Salesforce e consolidando KPIs..."):
    df_final = carregar_dados_completos()

# ==========================================
# 5.1. BARRA LATERAL (logo, filtros globais e atualizacao)
# ==========================================
with st.sidebar:
    _logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(_logo_path):
        _lc1, _lc2, _lc3 = st.columns([1, 2, 1])
        with _lc2:
            st.image(_logo_path, use_container_width=True)
            
    st.markdown("<h1 style='text-align:center; margin:0.3rem 0 0.2rem; font-weight:800;'>Painel de MP</h1>", unsafe_allow_html=True)
    
    st.header("Filtros")
    
    classificacoes_disponiveis = sorted(
        [c for c in df_final['Classificacao'].dropna().unique() if c and c != 'Não Classificado']
    ) + (['Não Classificado'] if (df_final['Classificacao'] == 'Não Classificado').any() else [])

    classificacoes_selecionadas = st.multiselect(
        "Classificação do Contrato",
        options=classificacoes_disponiveis,
        default=[],
        placeholder="Todas",
        key="filtro_classificacao_global",
        help="Filtra todos os indicadores e abas por uma ou mais classificações de contrato. Vazio = todas."
    )
    
    st.write("")
    if st.button("🔄 Atualizar Dados", key="btn_atualizar_topo", help="Recarrega os dados do Salesforce e os arquivos de capacidade", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# Aplica o filtro global. Se nada estiver selecionado, considera "todas as classificações".
if classificacoes_selecionadas:
    df_final = df_final[df_final['Classificacao'].isin(classificacoes_selecionadas)].copy()

# Indicador de última atualização na sidebar
ts_carga = df_final.attrs.get('timestamp_carga', 'desconhecido')
falhas_parse = df_final.attrs.get('falhas_parse_data', 0)
total_reg_original = df_final.attrs.get('total_registros', len(df_final))
total_reg_filtrado = len(df_final)

with st.sidebar:
    st.markdown("---")
    st.markdown("<h4 style='font-size:0.9rem; margin-bottom:5px; color:#16233F;'>Status dos Dados</h4>", unsafe_allow_html=True)
    info_msg = f"<p style='font-size:0.75rem; color:#647393; line-height:1.4;'>🕒 <b>Atualizado:</b> {ts_carga}<br>"
    if classificacoes_selecionadas:
        info_msg += f"📊 <b>Registros:</b> {total_reg_filtrado:,} (de {total_reg_original:,})<br>".replace(",", ".")
    else:
        info_msg += f"📊 <b>Registros:</b> {total_reg_original:,}<br>".replace(",", ".")
    if ts_capacidade:
        info_msg += f"📂 <b>Capacidade.xlsx:</b> {ts_capacidade}<br>"
    if falhas_parse > 0:
        info_msg += f"⚠️ <b>Erro:</b> {falhas_parse} OS não parseadas<br>"
    info_msg += "</p>"
    st.markdown(info_msg, unsafe_allow_html=True)

df_ativos_reais = df_final[df_final['Atraso_Base'] != AtrasoBase.ISENTO].copy()
df_ativos_filtrado = df_ativos_reais.copy()  # mantido para compatibilidade com código abaixo

# ==========================================
# 7. MAPEAMENTO CEP → PRESTADOR (uma vez só, usa Range CEP + De-Para)
# ==========================================
# O mapeamento depende APENAS dos arquivos estáveis (Range CEP + De-Para).
# A capacidade em si é carregada sob demanda em cada aba que precisa.
prestador_mapeado = False

if cadastro_ok:
    try:
        # Otimização: constrói o mapeamento CEP → Prestador apenas uma vez (cacheado)
        ceps_unicos = tuple(df_ativos_reais['CEP_Num'].dropna().unique())
        mapa_cep_prestador = construir_mapa_cep_prestador(ceps_unicos, df_ranges, dict_depara)
        
        df_ativos_reais['Prestador_CEP'] = df_ativos_reais['CEP_Num'].map(mapa_cep_prestador)
        df_ativos_filtrado['Prestador_CEP'] = df_ativos_filtrado['CEP_Num'].map(mapa_cep_prestador)
        
        prestador_mapeado = True
    except Exception as e:
        erro_arquivos_estaveis = f"Erro ao mapear CEPs para prestadores: {e}"

# Se houve algum erro de leitura dos arquivos estáveis, exibe discreto no corpo principal
if erro_arquivos_estaveis and not prestador_mapeado:
    st.warning(f"⚠️ {erro_arquivos_estaveis}")

# ==========================================
# 8. RENDERIZAÇÃO DAS ABAS
# ==========================================
aba_dashboard, aba_franquias, aba_capacidade, aba_diaria, aba_mailing, aba_m0, aba_mp_por_mes, aba_mp_agendado, aba_hist, aba_sem_cobertura, aba_consulta = st.tabs([
    "Visão Executiva", 
    "Visão por Franquias", 
    "Atraso vs Capacidade",
    "Capacidade Diária",
    "Mailing Acionável",
    "M0",
    "Quebra de MP por Mês",
    "MP Agendado",
    "Funil Mensal",
    "Sem Cobertura de CEP",
    "Consulta de Asset"
])

# === ABA 1: DASHBOARD EXECUTIVO ===
with aba_dashboard:
    df_view_dash = df_ativos_filtrado
    
    tot_cons = len(df_view_dash)
    tot_cons_em_dia = len(df_view_dash[df_view_dash['Status_MP_Real'] == StatusMP.EM_DIA])
    tot_cons_atraso = len(df_view_dash[df_view_dash['Atraso_Base'] == AtrasoBase.ATRASADO])
    tot_cons_prog = len(df_view_dash[df_view_dash['Status_MP_Real'] == StatusMP.PROGRAMADO])
    tot_cons_critico = len(df_view_dash[df_view_dash['Status_MP_Real'] == StatusMP.CRITICO])
    tot_cons_hoje = len(df_view_dash[(df_view_dash['Agendado_Hoje'] == True) & (df_view_dash['Atraso_Base'] == AtrasoBase.ATRASADO)])
    
    perc_cons_atraso = (tot_cons_atraso / tot_cons) * 100 if tot_cons > 0 else 0
    perc_cons_proj = (tot_cons_critico / tot_cons) * 100 if tot_cons > 0 else 0

    with st.container(border=True):
        st.markdown("#### 🌐 Base Ativa Total")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        col1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Volume da Carteira"}</div><div class="kpi-value">{f"{tot_cons:,}".replace(",", ".")}</div><div class="kpi-delta">{"Geral"}</div></div>''', unsafe_allow_html=True)
        col2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"MP Em Dia"}</div><div class="kpi-value">{f"{tot_cons_em_dia:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        col3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso Consolidado"}</div><div class="kpi-value">{f"{tot_cons_atraso:,}".replace(",", ".")}</div><div class="kpi-delta">{f"{perc_cons_atraso:.1f}% da base"}</div></div>''', unsafe_allow_html=True)
        col4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso"}</div><div class="kpi-value">{f"{tot_cons_critico:,}".replace(",", ".")}</div><div class="kpi-delta">{"Sem Ação"}</div></div>''', unsafe_allow_html=True)
        col5.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Prog. p/ Zerar (Mês)"}</div><div class="kpi-value">{f"{tot_cons_prog:,}".replace(",", ".")}</div><div class="kpi-delta">{"OS Válidas"}</div></div>''', unsafe_allow_html=True)
        col6.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Agendado p/ HOJE"}</div><div class="kpi-value">{f"{tot_cons_hoje:,}".replace(",", ".")}</div><div class="kpi-delta">{"Esforço diário"}</div></div>''', unsafe_allow_html=True)
        col7.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Projeção Pós-Baixas"}</div><div class="kpi-value">{f"{perc_cons_proj:.1f}%"}</div><div class="kpi-delta">{"Estimativa Final"}</div></div>''', unsafe_allow_html=True)
        with st.expander("📄 Extrato Rápido: Atrasos (Base Total)"):
            exibir_extrato_resumido(df_view_dash[df_view_dash['Atraso_Base'] == AtrasoBase.ATRASADO], key_download="base_total")

    st.write("") 
    
    df_adim = df_view_dash[df_view_dash['Status_Financeiro'] == StatusFin.ADIMPLENTE]
    tot_adim = len(df_adim)
    tot_adim_em_dia = len(df_adim[df_adim['Status_MP_Real'] == StatusMP.EM_DIA])
    tot_adim_atraso = len(df_adim[df_adim['Atraso_Base'] == AtrasoBase.ATRASADO])
    tot_adim_prog = len(df_adim[df_adim['Status_MP_Real'] == StatusMP.PROGRAMADO])
    tot_adim_critico = len(df_adim[df_adim['Status_MP_Real'] == StatusMP.CRITICO])
    tot_adim_hoje = len(df_adim[(df_adim['Agendado_Hoje'] == True) & (df_adim['Atraso_Base'] == AtrasoBase.ATRASADO)])

    perc_adim_atraso = (tot_adim_atraso / tot_adim) * 100 if tot_adim > 0 else 0
    perc_adim_proj = (tot_adim_critico / tot_adim) * 100 if tot_adim > 0 else 0

    with st.container(border=True):
        st.markdown("#### ✅ Contratos Adimplentes")
        colA1, colA2, colA3, colA4, colA5, colA6, colA7 = st.columns(7)
        colA1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Volume Adimplente"}</div><div class="kpi-value">{f"{tot_adim:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        colA2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"MP Em Dia"}</div><div class="kpi-value">{f"{tot_adim_em_dia:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        colA3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso Adimplente"}</div><div class="kpi-value">{f"{tot_adim_atraso:,}".replace(",", ".")}</div><div class="kpi-delta">{f"{perc_adim_atraso:.1f}% do segmento"}</div></div>''', unsafe_allow_html=True)
        colA4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso"}</div><div class="kpi-value">{f"{tot_adim_critico:,}".replace(",", ".")}</div><div class="kpi-delta">{"Prioridade Alta"}</div></div>''', unsafe_allow_html=True)
        colA5.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Prog. p/ Zerar (Mês)"}</div><div class="kpi-value">{f"{tot_adim_prog:,}".replace(",", ".")}</div><div class="kpi-delta">{"OS Válidas"}</div></div>''', unsafe_allow_html=True)
        colA6.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Agendado p/ HOJE"}</div><div class="kpi-value">{f"{tot_adim_hoje:,}".replace(",", ".")}</div><div class="kpi-delta">{"Esforço diário"}</div></div>''', unsafe_allow_html=True)
        colA7.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Projeção Pós-Baixas"}</div><div class="kpi-value">{f"{perc_adim_proj:.1f}%"}</div><div class="kpi-delta">{"Estimativa Final"}</div></div>''', unsafe_allow_html=True)
        with st.expander("📄 Extrato Rápido: Atrasos (Adimplentes)"):
            exibir_extrato_resumido(df_adim[df_adim['Atraso_Base'] == AtrasoBase.ATRASADO], key_download="adimplentes")

    st.write("") 

    df_inadim = df_view_dash[df_view_dash['Status_Financeiro'] == StatusFin.INADIMPLENTE]
    tot_inadim = len(df_inadim)
    tot_inadim_em_dia = len(df_inadim[df_inadim['Status_MP_Real'] == StatusMP.EM_DIA])
    tot_inadim_atraso = len(df_inadim[df_inadim['Atraso_Base'] == AtrasoBase.ATRASADO])
    tot_inadim_prog = len(df_inadim[df_inadim['Status_MP_Real'] == StatusMP.PROGRAMADO])
    tot_inadim_critico = len(df_inadim[df_inadim['Status_MP_Real'] == StatusMP.CRITICO])
    tot_inadim_hoje = len(df_inadim[(df_inadim['Agendado_Hoje'] == True) & (df_inadim['Atraso_Base'] == AtrasoBase.ATRASADO)])

    perc_inadim_atraso = (tot_inadim_atraso / tot_inadim) * 100 if tot_inadim > 0 else 0
    perc_inadim_proj = (tot_inadim_critico / tot_inadim) * 100 if tot_inadim > 0 else 0

    with st.container(border=True):
        st.markdown("#### ⚠️ Contratos Inadimplentes")
        colI1, colI2, colI3, colI4, colI5, colI6, colI7 = st.columns(7)
        colI1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Volume Inadimplente"}</div><div class="kpi-value">{f"{tot_inadim:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        colI2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"MP Em Dia"}</div><div class="kpi-value">{f"{tot_inadim_em_dia:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        colI3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso Inadimplente"}</div><div class="kpi-value">{f"{tot_inadim_atraso:,}".replace(",", ".")}</div><div class="kpi-delta">{f"{perc_inadim_atraso:.1f}% do segmento"}</div></div>''', unsafe_allow_html=True)
        colI4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso"}</div><div class="kpi-value">{f"{tot_inadim_critico:,}".replace(",", ".")}</div><div class="kpi-delta">{"Sem Ação"}</div></div>''', unsafe_allow_html=True)
        colI5.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Prog. p/ Zerar (Mês)"}</div><div class="kpi-value">{f"{tot_inadim_prog:,}".replace(",", ".")}</div><div class="kpi-delta">{"OS Válidas"}</div></div>''', unsafe_allow_html=True)
        colI6.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Agendado p/ HOJE"}</div><div class="kpi-value">{f"{tot_inadim_hoje:,}".replace(",", ".")}</div><div class="kpi-delta">{"Esforço diário"}</div></div>''', unsafe_allow_html=True)
        colI7.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Projeção Pós-Baixas"}</div><div class="kpi-value">{f"{perc_inadim_proj:.1f}%"}</div><div class="kpi-delta">{"Estimativa Final"}</div></div>''', unsafe_allow_html=True)
        with st.expander("📄 Extrato Rápido: Atrasos (Inadimplentes)"):
            exibir_extrato_resumido(df_inadim[df_inadim['Atraso_Base'] == AtrasoBase.ATRASADO], key_download="inadimplentes")

# === ABA 2: VISÃO POR FRANQUIAS ===
with aba_franquias:
    st.markdown("### 🏢 Análise de Eficiência por Franquia")
    
    col_filtro, _ = st.columns([1, 2])
    with col_filtro:
        filtro_franq = st.selectbox("Selecione o Segmento Financeiro:", ["Base Ativa Total", "Contratos Adimplentes", "Contratos Inadimplentes"], key="f_franq")
    
    # Aplica filtros globais junto com o segmento financeiro
    if filtro_franq == "Base Ativa Total": df_view = df_ativos_filtrado.copy()
    elif filtro_franq == "Contratos Adimplentes": df_view = df_ativos_filtrado[df_ativos_filtrado['Status_Financeiro'] == StatusFin.ADIMPLENTE].copy()
    else: df_view = df_ativos_filtrado[df_ativos_filtrado['Status_Financeiro'] == StatusFin.INADIMPLENTE].copy()

    # Agregação vetorizada (mais rápida que groupby.apply com lambda)
    if not df_view.empty:
        agg_franquia = df_view.groupby('FOZ_EndFranquiaForm__c').agg(
            **{
                'Total Ativos': ('FOZ_CodigoItem__c', 'size'),
                'MP Em Dia': ('Status_MP_Real', lambda x: (x == StatusMP.EM_DIA).sum()),
                'Programado (Mês)': ('Status_MP_Real', lambda x: (x == StatusMP.PROGRAMADO).sum()),
                'Atraso': ('Status_MP_Real', lambda x: (x == StatusMP.CRITICO).sum()),
                'Total Atrasado': ('Atraso_Base', lambda x: (x == AtrasoBase.ATRASADO).sum()),
            }
        ).reset_index()
        
        agg_franquia['% de Atraso'] = (agg_franquia['Total Atrasado'] / agg_franquia['Total Ativos']) * 100
        agg_franquia = agg_franquia.sort_values(by=['Atraso', 'Total Atrasado'], ascending=[False, False])
    
        # Tabela consolidada (visão geral + download)
        st.markdown("**Tabela Consolidada por Franquia**")
        st.dataframe(
            agg_franquia.rename(columns={'FOZ_EndFranquiaForm__c': 'Nome da Franquia'})
            .style.background_gradient(cmap='Blues', subset=['Total Atrasado', 'Atraso'])
            .format({'% de Atraso': "{:.1f}%"}),
            use_container_width=True, hide_index=True
        )
        
        st.download_button(
            label="📥 Baixar tabela de franquias (Excel)",
            data=df_para_excel_bytes(agg_franquia.rename(columns={'FOZ_EndFranquiaForm__c': 'Nome da Franquia'}), 'Franquias'),
            file_name=f"franquias_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            key="dl_franquias"
        )
        
        # ---------------------------------------------------------------
        # Visão expansível: clique em uma franquia para ver a quebra por Aging
        # ---------------------------------------------------------------
        st.markdown("---")
        st.markdown("**🔍 Detalhamento por Aging (clique para expandir)**")
        st.caption("Cada franquia abaixo pode ser expandida para mostrar a distribuição de contratos atrasados pelas faixas de aging.")
        
        # Campo de busca para filtrar franquias e não renderizar centenas de expanders
        busca_franq = st.text_input(
            "🔎 Buscar franquia (digite parte do nome para filtrar):",
            key="busca_franquia_aging",
            placeholder="Ex.: SAO PAULO, FORTALEZA, R01..."
        )
        
        # Pré-calcula a quebra de aging por franquia (apenas atrasados, vetorizado)
        df_atrasados_view = df_view[df_view['Atraso_Base'] == AtrasoBase.ATRASADO]
        if df_atrasados_view.empty:
            st.success("✅ Nenhum contrato em atraso no segmento selecionado. Nada a detalhar por aging.")
        else:
            quebra_aging = df_atrasados_view.groupby(['FOZ_EndFranquiaForm__c', 'AGING_MP']).size().unstack(fill_value=0)
            
            # Garante todas as faixas como colunas (mesmo as zeradas), na ordem cronológica de gravidade
            faixas_ordem = ['A) 0-30', 'B) 30-60', 'C) 60-90', 'D) 90-120', 'E) 120-150', 'F) 150+']
            for faixa in faixas_ordem:
                if faixa not in quebra_aging.columns:
                    quebra_aging[faixa] = 0
            quebra_aging = quebra_aging[faixas_ordem]
            quebra_aging['Total Atrasado'] = quebra_aging.sum(axis=1)
            
            # Aplica filtro de busca
            franquias_para_exibir = agg_franquia['FOZ_EndFranquiaForm__c'].tolist()
            if busca_franq:
                termo = busca_franq.upper().strip()
                franquias_para_exibir = [f for f in franquias_para_exibir if termo in str(f).upper()]
            
            # Limita a renderização para não estourar a UI quando há muitas franquias
            LIMITE_EXPANDERS = 30
            franquias_renderizar = [f for f in franquias_para_exibir if f in quebra_aging.index]
            
            if not franquias_renderizar:
                st.info("Nenhuma franquia encontrada com esse termo de busca, ou nenhuma franquia tem contratos atrasados.")
            else:
                if len(franquias_renderizar) > LIMITE_EXPANDERS:
                    st.warning(
                        f"⚠️ {len(franquias_renderizar)} franquias correspondem ao filtro. "
                        f"Exibindo as **{LIMITE_EXPANDERS} com maior volume de atraso** para preservar a performance. "
                        f"Use o campo de busca acima para refinar."
                    )
                    franquias_renderizar = franquias_renderizar[:LIMITE_EXPANDERS]
                
                # Renomeação amigável das faixas para exibição
                rename_faixas = {
                    'A) 0-30': '0-30 dias', 'B) 30-60': '30-60 dias', 'C) 60-90': '60-90 dias',
                    'D) 90-120': '90-120 dias', 'E) 120-150': '120-150 dias', 'F) 150+': '+150 dias'
                }
                
                for franq in franquias_renderizar:
                    linha_agg = agg_franquia[agg_franquia['FOZ_EndFranquiaForm__c'] == franq].iloc[0]
                    total_atr = int(quebra_aging.loc[franq, 'Total Atrasado'])
                    total_ativ = int(linha_agg['Total Ativos'])
                    perc = (total_atr / total_ativ * 100) if total_ativ > 0 else 0
                    
                    titulo_expander = (
                        f"{franq}  •  {total_atr:,} atrasados de {total_ativ:,} ativos  •  {perc:.1f}%"
                    ).replace(",", ".")
                    
                    with st.expander(titulo_expander):
                        # Mini-KPIs por faixa
                        colunas_faixas = st.columns(6)
                        for col, faixa in zip(colunas_faixas, faixas_ordem):
                            qtd = int(quebra_aging.loc[franq, faixa])
                            col.markdown(f'''<div class="kpi-container"><div class="kpi-title">{rename_faixas[faixa]}</div><div class="kpi-value">{f"{qtd:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                        
                        # Linha resumo: contagem por status (programado vs sem ação)
                        df_franq_atr = df_atrasados_view[df_atrasados_view['FOZ_EndFranquiaForm__c'] == franq]
                        prog_qtd = (df_franq_atr['Status_MP_Real'] == StatusMP.PROGRAMADO).sum()
                        sem_acao_qtd = (df_franq_atr['Status_MP_Real'] == StatusMP.CRITICO).sum()
                        
                        st.caption(
                            f"📌 Dos {total_atr:,} atrasados desta franquia: "
                            f"**{prog_qtd:,}** já têm OS programada para o mês • "
                            f"**{sem_acao_qtd:,}** ainda sem ação".replace(",", ".")
                        )
                        
                        # Tabela detalhada dos contratos atrasados desta franquia
                        df_franq_show = df_franq_atr.copy()
                        df_franq_show['Vencimento MP'] = df_franq_show['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
                        df_franq_show = df_franq_show[[
                            'FOZ_CodigoItem__c', 'Account.Name', 'Status_MP_Real', 'AGING_MP',
                            'Dias_Atraso', 'Vencimento MP', 'Status_Financeiro'
                        ]].rename(columns={
                            'FOZ_CodigoItem__c': 'Cód. Item',
                            'Account.Name': 'Cliente',
                            'Status_MP_Real': 'Status',
                            'AGING_MP': 'Aging',
                            'Dias_Atraso': 'Dias Atrasado',
                            'Status_Financeiro': 'Status Fin.'
                        }).sort_values(by='Dias Atrasado', ascending=False)
                        
                        st.dataframe(df_franq_show, use_container_width=True, hide_index=True, height=300)
    else:
        st.info("Nenhuma franquia disponível com os filtros aplicados.")

# === ABA 3: ATRASO VS CAPACIDADE ===
with aba_capacidade:
    st.markdown("### ⚖️ Distribuição de Atraso vs Capacidade")
    
    if not prestador_mapeado:
        st.warning("⚠️ Os arquivos de cadastro (Range CEP / De-Para) não estão disponíveis. Esta análise depende deles.")
    else:
        # Solicita o upload da Capacidade dentro da aba (a sessão guarda para outras abas)
        df_cap_mp, capacidade_agrupada = obter_capacidade_da_sessao("atraso_vs_capacidade")
        
        if df_cap_mp is not None:
            col_filtro_fin, col_filtro_franq = st.columns(2)
            with col_filtro_fin:
                filtro_cap_fin = st.selectbox("Status Financeiro:", ["Base Ativa Total", "Contratos Adimplentes", "Contratos Inadimplentes"], key="f_cap")
            
            df_alvo_cap = df_ativos_reais[df_ativos_reais['Atraso_Base'] == AtrasoBase.ATRASADO].copy()
            if filtro_cap_fin == "Contratos Adimplentes": df_alvo_cap = df_alvo_cap[df_alvo_cap['Status_Financeiro'] == StatusFin.ADIMPLENTE]
            elif filtro_cap_fin == "Contratos Inadimplentes": df_alvo_cap = df_alvo_cap[df_alvo_cap['Status_Financeiro'] == StatusFin.INADIMPLENTE]
            
            atrasos_grade = df_alvo_cap.groupby('Prestador_CEP', dropna=False).size().reset_index(name='Volume de Atrasos')
            atrasos_grade['Prestador_CEP'] = atrasos_grade['Prestador_CEP'].fillna('⚠️ SEM COBERTURA DE CEP')
            
            df_cruzamento = pd.merge(atrasos_grade, capacidade_agrupada, left_on='Prestador_CEP', right_on='Prestador de Serviço', how='outer')
            df_cruzamento['Prestador_CEP'] = df_cruzamento['Prestador_CEP'].fillna(df_cruzamento['Prestador de Serviço'])
            df_cruzamento = df_cruzamento.drop(columns=['Prestador de Serviço']).fillna(0)
            
            df_cruzamento['Volume de Atrasos'] = df_cruzamento['Volume de Atrasos'].astype(int)
            df_cruzamento['Capacidade Disponível'] = df_cruzamento['Capacidade Disponível'].astype(int)
            df_cruzamento['GAP (Sobra/Falta)'] = (df_cruzamento['Capacidade Disponível'] - df_cruzamento['Volume de Atrasos']).astype(int)
            df_cruzamento = df_cruzamento.rename(columns={'Prestador_CEP': 'Grade Operacional'})
            
            lista_franquias = ["Todas"] + sorted([str(x) for x in df_cruzamento['Grade Operacional'].unique() if pd.notna(x)])
            with col_filtro_franq:
                franq_selecionada = st.selectbox("📍 Filtrar Franquia/Grade Específica:", lista_franquias)
                
            if franq_selecionada != "Todas":
                df_cruzamento_view = df_cruzamento[df_cruzamento['Grade Operacional'] == franq_selecionada]
                if franq_selecionada == '⚠️ SEM COBERTURA DE CEP':
                    df_extrato_view = df_alvo_cap[df_alvo_cap['Prestador_CEP'].isnull()]
                else:
                    df_extrato_view = df_alvo_cap[df_alvo_cap['Prestador_CEP'] == franq_selecionada]
            else:
                df_cruzamento_view = df_cruzamento.sort_values(by='Volume de Atrasos', ascending=False)
                df_extrato_view = df_alvo_cap.copy()
                df_extrato_view['Prestador_CEP'] = df_extrato_view['Prestador_CEP'].fillna('⚠️ SEM COBERTURA DE CEP')
            
            st.markdown("---")
            tot_atr = int(df_cruzamento_view['Volume de Atrasos'].sum())
            tot_cap = int(df_cruzamento_view['Capacidade Disponível'].sum())
            gap_total = tot_cap - tot_atr
            
            col_sp1, col_c1, col_c2, col_c3, col_sp2 = st.columns([1, 2, 2, 2, 1])
            col_c1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Volume Atrasado (Mapeado)"}</div><div class="kpi-value">{f"{tot_atr:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            col_c2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Capacidade Livre (MP)"}</div><div class="kpi-value">{f"{tot_cap:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            col_c3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"GAP Global"}</div><div class="kpi-value">{f"{gap_total:,}".replace(",", ".")}</div><div class="kpi-delta">{"Capacidade vs Atraso"}</div></div>''', unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("**Tabela de Dimensionamento de Rotas**")
            st.dataframe(df_cruzamento_view.style.background_gradient(cmap='RdYlGn', subset=['GAP (Sobra/Falta)']), use_container_width=True, hide_index=True)
            
            st.download_button(
                label="📥 Baixar dimensionamento de rotas (Excel)",
                data=df_para_excel_bytes(df_cruzamento_view, 'Capacidade'),
                file_name=f"capacidade_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.ms-excel",
                key="dl_capacidade"
            )
                
            with st.expander(f"📄 Extrato Detalhado de Atrasos - {franq_selecionada}"):
                exibir_extrato_resumido(df_extrato_view, key_download=f"capacidade_{franq_selecionada}")

# === ABA 4: CAPACIDADE DIÁRIA ===
with aba_diaria:
    st.markdown("### 📅 Capacidade Diária de Atendimento (MP)")
    st.markdown("Visualize o volume diário de disponibilidade de atendimento cadastrado por cada base.")
    
    if not prestador_mapeado:
        st.warning("⚠️ Os arquivos de cadastro (Range CEP / De-Para) não estão disponíveis. Esta análise depende deles.")
    else:
        df_cap_mp, _ = obter_capacidade_da_sessao("capacidade_diaria")
        
        if df_cap_mp is not None:
            lista_franq_diaria = ["Todas"] + sorted([str(x) for x in df_cap_mp['Prestador de Serviço'].dropna().unique()])
            filtro_diaria = st.selectbox("📍 Filtrar Franquia (Visão Diária):", lista_franq_diaria)
            
            df_view_diaria = df_cap_mp.copy()
            if filtro_diaria != "Todas":
                df_view_diaria = df_view_diaria[df_view_diaria['Prestador de Serviço'] == filtro_diaria]
            
            if not df_view_diaria.empty:
                # Pivot usando o datetime diretamente como coluna (garante ordem cronológica correta)
                pivot_diaria = pd.pivot_table(
                    df_view_diaria,
                    values='Disponível',
                    index='Prestador de Serviço',
                    columns='Data do Registro',
                    aggfunc='sum',
                    fill_value=0
                ).astype(int)
                
                pivot_diaria = pivot_diaria.reindex(columns=sorted(pivot_diaria.columns))
                pivot_diaria.columns = [pd.Timestamp(c).strftime('%d/%m/%Y') for c in pivot_diaria.columns]
                
                qtd_dias = len(pivot_diaria.columns)
                qtd_prestadores = len(pivot_diaria.index)
                primeiro_dia = pivot_diaria.columns[0] if qtd_dias > 0 else '-'
                ultimo_dia = pivot_diaria.columns[-1] if qtd_dias > 0 else '-'
                st.caption(f"📅 Exibindo **{qtd_dias} dias** ({primeiro_dia} → {ultimo_dia}) e **{qtd_prestadores} prestador(es)**. Use o scroll horizontal da tabela para ver todas as datas.")
                
                altura_tabela = min(600, max(200, 50 + qtd_prestadores * 35))
                st.dataframe(
                    pivot_diaria.style.background_gradient(cmap='Greens', axis=None),
                    use_container_width=True,
                    height=altura_tabela
                )
                
                st.download_button(
                    label="📥 Baixar capacidade diária (Excel)",
                    data=df_para_excel_bytes(pivot_diaria.reset_index(), 'CapacidadeDiaria'),
                    file_name=f"capacidade_diaria_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.ms-excel",
                    key="dl_diaria"
                )

# === ABA 5: MAILING ACIONÁVEL ===
with aba_mailing:
    st.markdown("### ✉️ Mailing Acionável (Pronto para Agendamento)")
    st.markdown("Gere listas de clientes em atraso que **pertencem a franquias com capacidade ociosa** e que **ainda não possuem OS aberta**, ordenados rigorosamente do mais atrasado para o menos atrasado e limitados ao número de vagas da região.")
    
    if not prestador_mapeado:
        st.warning("⚠️ Os arquivos de cadastro (Range CEP / De-Para) não estão disponíveis. O Mailing depende deles.")
    else:
        _, capacidade_agrupada = obter_capacidade_da_sessao("mailing")
        
        if capacidade_agrupada is None:
            pass  # ainda não tem capacidade — helper já mostrou o uploader
        else:
            col_filtro_mail, _col2 = st.columns([1, 2])
            with col_filtro_mail:
                filtro_mail_fin = st.selectbox("Priorização Financeira do Mailing:", ["Base Ativa Total", "Contratos Adimplentes", "Contratos Inadimplentes"])
        
            # REGRA DE NEGÓCIO: mailing só lista contratos atrasados que AINDA NÃO TÊM OS aberta.
            # Como a regra do negócio impede abrir duas OS ao mesmo tempo para o mesmo contrato,
            # incluir contratos que já têm OS no mailing geraria contato indevido com o cliente
            # e potencial duplicidade. Por isso filtramos Tem_OS_Aberta == False.
            df_mail_base = df_ativos_reais[
                (df_ativos_reais['Atraso_Base'] == AtrasoBase.ATRASADO) &
                (df_ativos_reais['Tem_OS_Aberta'] == False)
            ].copy()
        
            # Aplica o filtro de segmento financeiro ANTES do diagnóstico, para que os números
            # apresentados reflitam exatamente o recorte selecionado pelo usuário.
            df_atrasados_segmento = df_ativos_reais[df_ativos_reais['Atraso_Base'] == AtrasoBase.ATRASADO].copy()
            if filtro_mail_fin == "Contratos Adimplentes":
                df_mail_base = df_mail_base[df_mail_base['Status_Financeiro'] == StatusFin.ADIMPLENTE]
                df_atrasados_segmento = df_atrasados_segmento[df_atrasados_segmento['Status_Financeiro'] == StatusFin.ADIMPLENTE]
                rotulo_segmento = "adimplentes"
            elif filtro_mail_fin == "Contratos Inadimplentes":
                df_mail_base = df_mail_base[df_mail_base['Status_Financeiro'] == StatusFin.INADIMPLENTE]
                df_atrasados_segmento = df_atrasados_segmento[df_atrasados_segmento['Status_Financeiro'] == StatusFin.INADIMPLENTE]
                rotulo_segmento = "inadimplentes"
            else:
                rotulo_segmento = "ao todo"
        
            # Diagnóstico dinâmico: quantos contratos do SEGMENTO selecionado foram excluídos por já terem OS
            total_atrasados_seg = len(df_atrasados_segmento)
            com_os = total_atrasados_seg - len(df_mail_base)
            st.caption(
                f"🔍 {total_atrasados_seg:,} contratos atrasados {rotulo_segmento}. "
                f"Destes, **{com_os:,} já possuem OS aberta** (excluídos do mailing) e "
                f"**{len(df_mail_base):,} estão elegíveis** para nova abordagem.".replace(",", ".")
            )
        
            # Merge de Atrasos com Capacidade
            df_mail_cruzado = pd.merge(df_mail_base, capacidade_agrupada, left_on='Prestador_CEP', right_on='Prestador de Serviço', how='left')
            df_mail_cruzado['Capacidade Disponível'] = df_mail_cruzado['Capacidade Disponível'].fillna(0).astype(int)
        
            # Filtra apenas quem tem vaga maior que 0
            df_mail_filtrado = df_mail_cruzado[df_mail_cruzado['Capacidade Disponível'] > 0].copy()
        
            if not df_mail_filtrado.empty:
                # ----- VETORIZAÇÃO do groupby.apply (mantém regra: ordena por atraso DESC e corta no limite de vagas) -----
                # 1. Ordena por Prestador_CEP (asc), Dias_Atraso (desc) e Cód. Item (asc para desempate determinístico)
                df_mail_filtrado = df_mail_filtrado.sort_values(
                    by=['Prestador_CEP', 'Dias_Atraso', 'FOZ_CodigoItem__c'],
                    ascending=[True, False, True]
                )
                # 2. Numera cada cliente dentro do prestador (0, 1, 2, ...)
                df_mail_filtrado['_rank'] = df_mail_filtrado.groupby('Prestador_CEP').cumcount()
                # 3. Mantém apenas os clientes cujo rank é menor que a capacidade disponível
                df_mail_final = df_mail_filtrado[df_mail_filtrado['_rank'] < df_mail_filtrado['Capacidade Disponível']].drop(columns=['_rank']).reset_index(drop=True)
            
                st.markdown(f"**{len(df_mail_final)} contratos selecionados e cortados cirurgicamente de acordo com o limite de vagas operacionais.**")
            
                df_mail_final['Data_Vencimento_MP'] = df_mail_final['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
                
                # LGPD: telefones de clientes NÃO são exibidos nem trafegam pelo painel online.
                # O mailing completo com telefones é gerado localmente via gerar_mailing_local.py.
                st.info(
                    "🔒 **LGPD:** os telefones dos clientes não são exibidos no painel online. "
                    "Para gerar o mailing completo com telefones, use o **gerador local** "
                    "(`gerar_mailing_local.py`) na sua máquina."
                )
                
                cols_finais = [
                    'FOZ_CodigoItem__c', 'Account.Name', 'Qtd_Contratos_Cliente',
                    'Status_Financeiro', 'Data_Vencimento_MP', 'Dias_Atraso',
                    'Prestador_CEP', 'Capacidade Disponível'
                ]
                
                df_exibicao_mail = df_mail_final[cols_finais].rename(columns={
                    'FOZ_CodigoItem__c': 'Cód. Item',
                    'Account.Name': 'Cliente',
                    'Qtd_Contratos_Cliente': 'Qtd Contratos',
                    'Status_Financeiro': 'Status Fin.',
                    'Data_Vencimento_MP': 'Vencimento MP',
                    'Dias_Atraso': 'Dias Atraso',
                    'Prestador_CEP': 'Grade/Franquia',
                    'Capacidade Disponível': 'Vagas na Região'
                }).sort_values(by=['Vagas na Região', 'Dias Atraso'], ascending=[False, False])
                
                st.dataframe(df_exibicao_mail, use_container_width=True, hide_index=True)
            
                st.download_button(
                    label="📥 Baixar Mailing (sem telefones)",
                    data=df_para_excel_bytes(df_exibicao_mail, 'Mailing_Agendamento'),
                    file_name=f"Mailing_Agendamento_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
                
                # ============================================================
                # EXTRATOS DOS NÃO ACIONADOS — clientes em atraso que ficaram
                # de fora do mailing por restrição de capacidade. Útil para:
                #  1) Justificar pedidos de aumento de capacidade com dados
                #  2) Identificar franquias críticas (alta demanda, sem vaga)
                #  3) Garantir que ninguém é esquecido na operação
                # ============================================================
                st.markdown("---")
                st.markdown("### 🚫 Contratos NÃO acionados (sem capacidade de agendamento)")
                st.markdown(
                    "Contratos atrasados e elegíveis para contato, **mas que ficaram fora do mailing** "
                    "porque a franquia responsável não tem vagas suficientes. Use este extrato para "
                    "dimensionar pedidos de aumento de capacidade e identificar regiões críticas."
                )
                
                # GRUPO 1: Excedente — franquia TEM vagas, mas o contrato ficou após o corte
                # (ex.: franquia com 20 vagas e 50 atrasados → 30 excedentes)
                # GRUPO 2: Franquia sem vagas — capacidade zero na região
                # 
                # Para identificar os dois grupos, refazemos o cruzamento Atrasados × Capacidade
                # a partir de df_mail_base (todos os atrasados elegíveis, independente da capacidade)
                df_excedente = pd.merge(
                    df_mail_base,
                    capacidade_agrupada,
                    left_on='Prestador_CEP',
                    right_on='Prestador de Serviço',
                    how='left'
                )
                df_excedente['Capacidade Disponível'] = df_excedente['Capacidade Disponível'].fillna(0).astype(int)
                
                # Separa em dois grupos
                df_grupo1 = df_excedente[df_excedente['Capacidade Disponível'] > 0].copy()  # franquia com vaga
                df_grupo2 = df_excedente[df_excedente['Capacidade Disponível'] == 0].copy()  # sem vaga
                
                # GRUPO 1: refaz o ranking e pega quem está APÓS o corte
                if not df_grupo1.empty:
                    df_grupo1 = df_grupo1.sort_values(
                        by=['Prestador_CEP', 'Dias_Atraso', 'FOZ_CodigoItem__c'],
                        ascending=[True, False, True]
                    )
                    df_grupo1['_rank'] = df_grupo1.groupby('Prestador_CEP').cumcount()
                    df_excedente_capacidade = df_grupo1[
                        df_grupo1['_rank'] >= df_grupo1['Capacidade Disponível']
                    ].drop(columns=['_rank']).copy()
                else:
                    df_excedente_capacidade = pd.DataFrame()
                
                # GRUPO 2: franquia sem nenhuma vaga
                df_sem_vagas = df_grupo2.copy()
                
                # Concatena os dois grupos com um campo identificador
                if not df_excedente_capacidade.empty:
                    df_excedente_capacidade['Motivo_Nao_Acionamento'] = 'Excedente de capacidade'
                if not df_sem_vagas.empty:
                    df_sem_vagas['Motivo_Nao_Acionamento'] = 'Franquia sem vagas'
                
                df_nao_acionados = pd.concat(
                    [df_excedente_capacidade, df_sem_vagas],
                    ignore_index=True
                ) if (not df_excedente_capacidade.empty or not df_sem_vagas.empty) else pd.DataFrame()
                
                if df_nao_acionados.empty:
                    st.success(
                        "✅ Excelente! Todos os contratos atrasados elegíveis estão sendo acionados — "
                        "a capacidade atual da rede atende 100% da demanda neste segmento financeiro."
                    )
                else:
                    # KPIs do extrato
                    qtd_excedente = len(df_excedente_capacidade) if not df_excedente_capacidade.empty else 0
                    qtd_sem_vagas = len(df_sem_vagas) if not df_sem_vagas.empty else 0
                    qtd_total_nao_acionados = qtd_excedente + qtd_sem_vagas
                    qtd_franquias_afetadas = df_nao_acionados['Prestador_CEP'].nunique()
                    
                    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
                    col_k1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Total não acionados"}</div><div class="kpi-value">{f"{qtd_total_nao_acionados:,}".replace(",", ".")}</div><div class="kpi-delta">{"Contratos perdidos no recorte"}</div></div>''', unsafe_allow_html=True)
                    col_k2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Excedente de capacidade"}</div><div class="kpi-value">{f"{qtd_excedente:,}".replace(",", ".")}</div><div class="kpi-delta">{"Franquia tem vaga, mas não p/ todos"}</div></div>''', unsafe_allow_html=True)
                    col_k3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Franquia sem vagas"}</div><div class="kpi-value">{f"{qtd_sem_vagas:,}".replace(",", ".")}</div><div class="kpi-delta">{"Zero capacidade na região"}</div></div>''', unsafe_allow_html=True)
                    col_k4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Franquias afetadas"}</div><div class="kpi-value">{f"{qtd_franquias_afetadas:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                    
                    st.write("")
                    
                    # Resumo por franquia (priorização para aumento de capacidade)
                    st.markdown("**📊 Resumo por franquia (priorize aumento de capacidade onde o volume é maior)**")
                    df_nao_acionados['Prestador_CEP_Display'] = df_nao_acionados['Prestador_CEP'].fillna('⚠️ SEM COBERTURA DE CEP')
                    resumo_franq = df_nao_acionados.groupby(['Prestador_CEP_Display', 'Motivo_Nao_Acionamento']).size().unstack(fill_value=0)
                    
                    # Garante as duas colunas (mesmo se um dos motivos estiver vazio)
                    for col in ['Excedente de capacidade', 'Franquia sem vagas']:
                        if col not in resumo_franq.columns:
                            resumo_franq[col] = 0
                    resumo_franq['Total não acionados'] = resumo_franq.sum(axis=1)
                    resumo_franq = resumo_franq.sort_values('Total não acionados', ascending=False).reset_index()
                    resumo_franq.columns = ['Franquia', 'Excedente', 'Sem Vagas', 'Total']
                    
                    st.dataframe(
                        resumo_franq.style.background_gradient(cmap='Reds', subset=['Total']),
                        use_container_width=True, hide_index=True
                    )
                    
                    st.write("")
                    
                    # Extrato detalhado (mesmo formato do mailing principal, mas com motivo)
                    st.markdown("**📋 Extrato detalhado**")
                    df_nao_acionados['Vencimento MP'] = df_nao_acionados['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
                    
                    # LGPD: sem telefones no painel online (use o gerador local de mailing)
                    cols_na = [
                        'Motivo_Nao_Acionamento',
                        'FOZ_CodigoItem__c', 'Account.Name', 'Qtd_Contratos_Cliente',
                        'Status_Financeiro', 'Vencimento MP', 'Dias_Atraso',
                        'Prestador_CEP_Display', 'Capacidade Disponível'
                    ]
                    
                    df_exibicao_na = df_nao_acionados[cols_na].rename(columns={
                        'Motivo_Nao_Acionamento': 'Motivo',
                        'FOZ_CodigoItem__c': 'Cód. Item',
                        'Account.Name': 'Cliente',
                        'Qtd_Contratos_Cliente': 'Qtd Contratos',
                        'Status_Financeiro': 'Status Fin.',
                        'Dias_Atraso': 'Dias Atraso',
                        'Prestador_CEP_Display': 'Grade/Franquia',
                        'Capacidade Disponível': 'Vagas na Região'
                    }).sort_values(by=['Motivo', 'Grade/Franquia', 'Dias Atraso'],
                                   ascending=[True, True, False])
                    
                    st.dataframe(df_exibicao_na, use_container_width=True, hide_index=True)
                    
                    st.download_button(
                        label="📥 Baixar Não Acionados (Excel)",
                        data=df_para_excel_bytes(df_exibicao_na, 'Nao_Acionados'),
                        file_name=f"Nao_Acionados_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        mime="application/vnd.ms-excel",
                        key="dl_nao_acionados"
                    )
            else:
                st.info("Não há clientes em atraso nas franquias que possuem capacidade livre neste momento.")

# === ABA 6: M0 (CONTRATOS COM MP VENCENDO NO MÊS+1) ===
with aba_m0:
    st.markdown("### 🎯 M0 — Contratos que entram em atraso no próximo mês")
    st.markdown(
        "Lista os contratos da base ativa que **entram em atraso no próximo mês civil** "
        "(vencimento da MP + 30 dias de carência) em relação à data de hoje. Use essa aba para "
        "se antecipar e atuar antes que esses contratos entrem em atraso."
    )
    
    # Calcula o mês-alvo: mês corrente + 1
    hoje_br = datetime.now(FUSO_BR)
    mes_corrente = hoje_br.month
    ano_corrente = hoje_br.year
    
    # Mês seguinte (com virada de ano)
    if mes_corrente == 12:
        mes_alvo, ano_alvo = 1, ano_corrente + 1
    else:
        mes_alvo, ano_alvo = mes_corrente + 1, ano_corrente
    
    nomes_meses = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    nome_mes_alvo = f"{nomes_meses[mes_alvo]}/{ano_alvo}"
    
    st.caption(f"📅 Mês de referência: **{nome_mes_alvo}** (hoje é {hoje_br.strftime('%d/%m/%Y')})")
    
    # A "entrada em atraso" acontece CARENCIA_ATRASO_DIAS dias após o vencimento (mesma regra do
    # Atraso_Base). Por isso o M0 olha o mês em que o contrato ENTRA EM ATRASO (vencimento + carência),
    # e não o mês do vencimento cru. Ex.: venceu 15/06 -> entra em atraso 16/07 -> cai no M0 de julho.
    # IMPORTANTE: usamos a base completa (df_final), não df_ativos_reais, para a visão crua
    # (inclui contratos com OS de desinstalação, se houver).
    _entrada_atraso_m0 = df_final['FOZ_DataProximaMP__c'] + pd.Timedelta(days=CARENCIA_ATRASO_DIAS)
    df_m0 = df_final[
        (_entrada_atraso_m0.dt.month == mes_alvo) &
        (_entrada_atraso_m0.dt.year == ano_alvo)
    ].copy()
    
    if df_m0.empty:
        st.info(f"Nenhum contrato com MP vencendo em {nome_mes_alvo}.")
    else:
        # KPIs no topo
        total_m0 = len(df_m0)
        adim_m0 = (df_m0['Status_Financeiro'] == StatusFin.ADIMPLENTE).sum()
        inadim_m0 = (df_m0['Status_Financeiro'] == StatusFin.INADIMPLENTE).sum()
        com_os_m0 = df_m0['Tem_OS_Aberta'].sum() if 'Tem_OS_Aberta' in df_m0.columns else 0
        sem_os_m0 = total_m0 - com_os_m0
        clientes_unicos = df_m0['Account.CNPJ__c'].nunique()
        
        with st.container(border=True):
            st.markdown(f"#### 📊 Resumo M0 — {nome_mes_alvo}")
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            col1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Contratos no M0"}</div><div class="kpi-value">{f"{total_m0:,}".replace(",", ".")}</div><div class="kpi-delta">{"Vencendo no mês"}</div></div>''', unsafe_allow_html=True)
            col2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Clientes únicos"}</div><div class="kpi-value">{f"{clientes_unicos:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            col3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Adimplentes"}</div><div class="kpi-value">{f"{adim_m0:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            col4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Inadimplentes"}</div><div class="kpi-value">{f"{inadim_m0:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            col5.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Com OS aberta"}</div><div class="kpi-value">{f"{com_os_m0:,}".replace(",", ".")}</div><div class="kpi-delta">{"Já em ação"}</div></div>''', unsafe_allow_html=True)
            col6.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Sem OS aberta"}</div><div class="kpi-value">{f"{sem_os_m0:,}".replace(",", ".")}</div><div class="kpi-delta">{"Pendente"}</div></div>''', unsafe_allow_html=True)
        
        st.write("")
        
        # Filtros opcionais
        col_filtro_fin, col_filtro_os, col_filtro_franq = st.columns(3)
        with col_filtro_fin:
            filtro_m0_fin = st.selectbox(
                "Status Financeiro:",
                ["Todos", "Apenas Adimplentes", "Apenas Inadimplentes"],
                key="filtro_m0_fin"
            )
        with col_filtro_os:
            filtro_m0_os = st.selectbox(
                "OS Aberta:",
                ["Todos", "Apenas COM OS aberta", "Apenas SEM OS aberta"],
                key="filtro_m0_os"
            )
        with col_filtro_franq:
            lista_franq_m0 = ["Todas"] + sorted([str(x) for x in df_m0['FOZ_EndFranquiaForm__c'].dropna().unique()])
            filtro_m0_franq = st.selectbox("Franquia:", lista_franq_m0, key="filtro_m0_franq")
        
        df_m0_view = df_m0.copy()
        if filtro_m0_fin == "Apenas Adimplentes":
            df_m0_view = df_m0_view[df_m0_view['Status_Financeiro'] == StatusFin.ADIMPLENTE]
        elif filtro_m0_fin == "Apenas Inadimplentes":
            df_m0_view = df_m0_view[df_m0_view['Status_Financeiro'] == StatusFin.INADIMPLENTE]
        if filtro_m0_os == "Apenas COM OS aberta":
            df_m0_view = df_m0_view[df_m0_view['Tem_OS_Aberta'] == True]
        elif filtro_m0_os == "Apenas SEM OS aberta":
            df_m0_view = df_m0_view[df_m0_view['Tem_OS_Aberta'] == False]
        if filtro_m0_franq != "Todas":
            df_m0_view = df_m0_view[df_m0_view['FOZ_EndFranquiaForm__c'] == filtro_m0_franq]
        
        st.caption(f"Exibindo **{len(df_m0_view):,} contrato(s)** após filtros.".replace(",", "."))
        
        if not df_m0_view.empty:
            df_m0_view['Vencimento MP'] = df_m0_view['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
            df_m0_show = df_m0_view[[
                'FOZ_CodigoItem__c', 'Account.Name', 'Qtd_Contratos_Cliente',
                'Vencimento MP', 'FOZ_EndFranquiaForm__c', 'Status_Financeiro',
                'Tem_OS_Aberta', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento'
            ]].rename(columns={
                'FOZ_CodigoItem__c': 'Cód. Item',
                'Account.Name': 'Cliente',
                'Qtd_Contratos_Cliente': 'Qtd Contratos',
                'FOZ_EndFranquiaForm__c': 'Franquia',
                'Status_Financeiro': 'Status Fin.',
                'Tem_OS_Aberta': 'Tem OS?',
                'Numero_Caso': 'Nº OS',
                'Tipo_Servico': 'Tipo de Serviço',
                'Data_Agendamento': 'Data OS (Agendada)'
            }).fillna({'Nº OS': '-', 'Tipo de Serviço': '-', 'Data OS (Agendada)': '-'})
            df_m0_show['Tem OS?'] = df_m0_show['Tem OS?'].map({True: 'Sim', False: 'Não'})
            
            st.dataframe(df_m0_show, use_container_width=True, hide_index=True)
            
            st.download_button(
                label="📥 Baixar M0 (Excel)",
                data=df_para_excel_bytes(df_m0_show, 'M0'),
                file_name=f"M0_{nomes_meses[mes_alvo].lower()}_{ano_alvo}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.ms-excel",
                key="dl_m0"
            )
        else:
            st.info("Nenhum contrato encontrado com os filtros aplicados.")

# === ABA: QUEBRA DE MP POR MÊS (M1, M2, M3...) ===
with aba_mp_por_mes:
    st.markdown("### 🗓️ Quebra de MP por Mês (M1, M2, M3...)")
    st.markdown(
        "Distribui a base ativa pelos próximos meses, mostrando **quantos contratos têm a MP vencendo** "
        "em cada mês à frente. **M1** = um mês à frente do mês corrente, **M2** = dois meses à frente, "
        "e assim por diante."
    )

    # Texto explicativo: como esta aba consolida as informações
    with st.container(border=True):
        st.markdown(
            """
**ℹ️ Como esta aba consolida as informações**

- **Critério de mês:** diferente da aba **M0**, aqui o contrato é alocado pelo **mês da própria data de
  vencimento da MP** (`FOZ_DataProximaMP__c`), **sem** aplicar os 30 dias de carência. Ou seja, se a MP
  vence em qualquer dia de um mês, o contrato é contado naquele mês — independentemente do dia.
- **Como os "M" são contados:** o mês corrente é o ponto de partida. **M1** é o próximo mês civil, **M2**
  o seguinte, e assim por diante (a virada de ano é tratada automaticamente).
- **Base utilizada:** a base completa de contratos da carga atual (mesma origem do M0), incluindo
  eventuais contratos com OS de desinstalação aberta, para dar a visão crua do volume.
- **O que cada linha mostra:** para o mês daquele "M", o total de contratos com MP vencendo e a quebra
  por situação financeira (Adimplentes / Inadimplentes) e por OS (com/sem OS aberta).
- **Fora do recorte futuro:** contratos com vencimento **no mês atual ou já vencidos** não entram nas
  colunas M1+ — eles ficam de fora desta visão, que olha apenas os meses à frente.
            """
        )

    # Base de referência temporal
    hoje_mpm = datetime.now(FUSO_BR)
    mes_corrente_mpm = hoje_mpm.month
    ano_corrente_mpm = hoje_mpm.year

    nomes_meses_mpm = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }

    st.caption(f"📅 Hoje é {hoje_mpm.strftime('%d/%m/%Y')}. Cada coluna 'M' é contada a partir do mês corrente ({nomes_meses_mpm[mes_corrente_mpm]}/{ano_corrente_mpm}).")

    # Quantidade de meses à frente a exibir (M1..Mn)
    horizonte_meses = st.slider(
        "Quantos meses à frente exibir (M1 até Mn):",
        min_value=3, max_value=18, value=12, step=1, key="mpm_horizonte"
    )

    # IMPORTANTE: nesta aba (e SOMENTE nesta aba) NÃO se aplica a carência de 30 dias.
    # O contrato é alocado pelo mês da própria data de vencimento da MP.
    # Usa a base completa (df_final) para a visão crua.
    _venc_mpm = df_final['FOZ_DataProximaMP__c']

    # Índice de mês absoluto (ano*12 + mês) para calcular a diferença em meses de forma robusta
    base_idx = ano_corrente_mpm * 12 + mes_corrente_mpm
    _mes_idx_mpm = _venc_mpm.dt.year * 12 + _venc_mpm.dt.month
    _offset_meses = (_mes_idx_mpm - base_idx)  # 1 = próximo mês (M1), 2 = M2, ...

    df_mpm = df_final.copy()
    df_mpm['_offset_meses'] = _offset_meses

    # Monta a tabela-resumo M1..Mn
    linhas_resumo = []
    for n in range(1, horizonte_meses + 1):
        mes_n = mes_corrente_mpm + n
        ano_n = ano_corrente_mpm + (mes_n - 1) // 12
        mes_n = (mes_n - 1) % 12 + 1
        rotulo_mes = f"{nomes_meses_mpm[mes_n]}/{ano_n}"

        df_bucket = df_mpm[df_mpm['_offset_meses'] == n]
        total_n = len(df_bucket)
        adim_n = int((df_bucket['Status_Financeiro'] == StatusFin.ADIMPLENTE).sum())
        inadim_n = int((df_bucket['Status_Financeiro'] == StatusFin.INADIMPLENTE).sum())
        com_os_n = int(df_bucket['Tem_OS_Aberta'].sum()) if 'Tem_OS_Aberta' in df_bucket.columns else 0
        sem_os_n = total_n - com_os_n

        linhas_resumo.append({
            'Período': f'M{n}',
            'Mês de Vencimento': rotulo_mes,
            'Contratos': total_n,
            'Adimplentes': adim_n,
            'Inadimplentes': inadim_n,
            'Com OS aberta': com_os_n,
            'Sem OS aberta': sem_os_n,
        })

    df_resumo_mpm = pd.DataFrame(linhas_resumo)

    # Tabela-resumo (formata milhares com ponto para exibição)
    df_resumo_show = df_resumo_mpm.copy()
    for col in ['Contratos', 'Adimplentes', 'Inadimplentes', 'Com OS aberta', 'Sem OS aberta']:
        df_resumo_show[col] = df_resumo_show[col].map(lambda v: f"{v:,}".replace(",", "."))

    st.markdown("#### 📋 Quebra por mês")
    st.dataframe(df_resumo_show, use_container_width=True, hide_index=True)

    st.download_button(
        label="📥 Baixar quebra por mês (Excel)",
        data=df_para_excel_bytes(df_resumo_mpm, 'MP_por_Mes'),
        file_name=f"quebra_mp_por_mes_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.ms-excel",
        key="dl_mp_por_mes"
    )

    # Drill-down: detalhar os contratos de um M específico
    st.markdown("---")
    st.markdown("#### 🔎 Ver contratos de um mês específico")
    opcoes_drill = [f"M{n} — {df_resumo_mpm.loc[n-1, 'Mês de Vencimento']}" for n in range(1, horizonte_meses + 1)]
    escolha_drill = st.selectbox("Selecione o mês:", opcoes_drill, key="mpm_drill")
    n_escolhido = int(escolha_drill.split("—")[0].strip().lstrip("M"))

    df_detalhe = df_mpm[df_mpm['_offset_meses'] == n_escolhido].copy()
    if df_detalhe.empty:
        st.info("Nenhum contrato neste mês.")
    else:
        df_detalhe['Vencimento MP'] = df_detalhe['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
        cols_det = [
            'FOZ_CodigoItem__c', 'Account.Name', 'Qtd_Contratos_Cliente',
            'Vencimento MP', 'FOZ_EndFranquiaForm__c', 'Status_Financeiro',
            'Tem_OS_Aberta', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento'
        ]
        cols_det_existentes = [c for c in cols_det if c in df_detalhe.columns]
        df_detalhe_show = df_detalhe[cols_det_existentes].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item',
            'Account.Name': 'Cliente',
            'Qtd_Contratos_Cliente': 'Qtd Contratos',
            'FOZ_EndFranquiaForm__c': 'Franquia',
            'Status_Financeiro': 'Status Fin.',
            'Tem_OS_Aberta': 'Tem OS?',
            'Numero_Caso': 'Nº OS',
            'Tipo_Servico': 'Tipo de Serviço',
            'Data_Agendamento': 'Data OS (Agendada)'
        }).fillna({'Nº OS': '-', 'Tipo de Serviço': '-', 'Data OS (Agendada)': '-'})
        if 'Tem OS?' in df_detalhe_show.columns:
            df_detalhe_show['Tem OS?'] = df_detalhe_show['Tem OS?'].map({True: 'Sim', False: 'Não'})

        st.caption(f"**{len(df_detalhe_show):,} contrato(s)** em {escolha_drill}.".replace(",", "."))
        st.dataframe(df_detalhe_show, use_container_width=True, hide_index=True)

        st.download_button(
            label="📥 Baixar detalhe deste mês (Excel)",
            data=df_para_excel_bytes(df_detalhe_show, f'M{n_escolhido}'),
            file_name=f"detalhe_M{n_escolhido}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.ms-excel",
            key="dl_mp_por_mes_detalhe"
        )


# === ABA: MP AGENDADO (quebra por mês da data agendada) ===
with aba_mp_agendado:
    st.markdown("### 📆 MP Agendado — quebra por mês")
    st.markdown(
        "Todas as **OS de Manutenção Preventiva com data agendada** (data da visita), "
        "agrupadas pelo **mês do agendamento**. A escolha do item de serviço usa a regra de WOLI "
        "(ignora Cancelado/Reagendado e pega o válido mais recente). "
        "Reflete a carteira ativa e respeita o filtro global de Classificação."
    )

    _meses_abrev = {
        1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
        7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'
    }

    df_ag = df_final.attrs.get('os_mp_agendado')
    if df_ag is None or df_ag.empty:
        st.info("Nenhuma OS de Manutenção Preventiva com data agendada encontrada.")
    else:
        df_ag = df_ag.copy()
        df_ag['CodigoItem'] = df_ag['CodigoItem'].astype(str)

        # Restringe à carteira ativa/filtrada (inner join => respeita o filtro de Classificação)
        _ctx_cols = ['FOZ_CodigoItem__c', 'Account.Name', 'FOZ_EndFranquiaForm__c', 'Status_Financeiro']
        _ctx = df_final[[c for c in _ctx_cols if c in df_final.columns]].copy()
        _ctx['FOZ_CodigoItem__c'] = _ctx['FOZ_CodigoItem__c'].astype(str)
        df_ag = df_ag.merge(_ctx, left_on='CodigoItem', right_on='FOZ_CodigoItem__c', how='inner')

        if df_ag.empty:
            st.info("Nenhuma OS de MP agendada na carteira ativa atual (verifique o filtro de Classificação).")
        else:
            # --- Filtro de Status do Item (WOLI) no TOPO da aba: afeta KPIs, gráfico e tabela ---
            _status_opts = sorted([s for s in df_ag['Status_Item_Servico'].dropna().unique()])
            status_sel = st.multiselect(
                "Status do Item (WOLI):",
                options=_status_opts,
                default=[],
                placeholder="Todos",
                key="filtro_mp_ag_status",
                help="Filtra os indicadores, o gráfico e a tabela por um ou mais status do item de serviço. Vazio = todos."
            )
            if status_sel:
                df_ag = df_ag[df_ag['Status_Item_Servico'].isin(status_sel)].copy()

            if df_ag.empty:
                st.info("Nenhuma OS de MP agendada com o(s) status selecionado(s).")
            else:
                _hoje = datetime.now(FUSO_BR)
                _mes_c, _ano_c = _hoje.month, _hoje.year

                total_agendado = len(df_ag)
                no_mes = int(((df_ag['Mes_Agendamento'] == _mes_c) & (df_ag['Ano_Agendamento'] == _ano_c)).sum())
                clientes_unicos = df_ag['Account.Name'].nunique() if 'Account.Name' in df_ag.columns else df_ag['CodigoItem'].nunique()

                with st.container(border=True):
                    st.markdown("#### 📊 Resumo")
                    k1, k2, k3 = st.columns(3)
                    k1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Total agendado (carteira ativa)"}</div><div class="kpi-value">{f"{total_agendado:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                    k2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{f"Agendado neste mês ({_meses_abrev[_mes_c]}/{_ano_c})"}</div><div class="kpi-value">{f"{no_mes:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                    k3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Clientes únicos"}</div><div class="kpi-value">{f"{clientes_unicos:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)

                st.write("")

                # Quebra por mês — todos os meses presentes, em ordem cronológica
                df_ag['_MesKey'] = df_ag['Ano_Agendamento'].astype(int) * 100 + df_ag['Mes_Agendamento'].astype(int)
                df_ag['Mês'] = df_ag['Mes_Agendamento'].astype(int).map(_meses_abrev) + '/' + df_ag['Ano_Agendamento'].astype(int).astype(str)

                resumo_mes = (
                    df_ag.groupby(['_MesKey', 'Mês']).size()
                    .reset_index(name='OS agendadas')
                    .sort_values('_MesKey')
                )

                fig_ag = px.bar(resumo_mes, x='Mês', y='OS agendadas', text='OS agendadas')
                fig_ag.update_traces(textposition='outside')
                fig_ag.update_xaxes(categoryorder='array', categoryarray=resumo_mes['Mês'].tolist())
                fig_ag = aplicar_tema_moderno(fig_ag)
                st.plotly_chart(fig_ag, use_container_width=True)

                # Detalhe das OS (tabela em largura total — sem a tabela "Por mês")
                st.markdown("##### Detalhe das OS")
                _meses_opts = ['Todos os meses'] + resumo_mes['Mês'].tolist()
                filtro_mes_ag = st.selectbox("Filtrar por mês:", _meses_opts, key="filtro_mp_ag_mes")
                df_det = df_ag if filtro_mes_ag == 'Todos os meses' else df_ag[df_ag['Mês'] == filtro_mes_ag]

                _cols_det = ['CodigoItem', 'Account.Name', 'FOZ_EndFranquiaForm__c', 'Status_Financeiro',
                             'Numero_Caso', 'Tipo_Servico', 'Status_Item_Servico', 'Data_Agendamento', 'Mês']
                df_det_show = df_det[[c for c in _cols_det if c in df_det.columns]].rename(columns={
                    'CodigoItem': 'Cód. Item', 'Account.Name': 'Cliente',
                    'FOZ_EndFranquiaForm__c': 'Franquia', 'Status_Financeiro': 'Status Fin.',
                    'Numero_Caso': 'Nº OS', 'Tipo_Servico': 'Tipo de Serviço',
                    'Status_Item_Servico': 'Status do Item', 'Data_Agendamento': 'Data Agendada'
                }).fillna('—')
                st.caption(f"Exibindo **{len(df_det_show):,} OS**.".replace(",", "."))
                st.dataframe(df_det_show, use_container_width=True, hide_index=True)

                st.download_button(
                    label="📥 Baixar MP agendado (Excel)",
                    data=df_para_excel_bytes(df_det_show, 'MP_Agendado'),
                    file_name=f"mp_agendado_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.ms-excel",
                    key="dl_mp_agendado"
                )

# === ABA 6: HISTÓRICO (SNAPSHOT) ===
with aba_hist:
    st.markdown("### 🔻 Funil de Conversão Mensal")
    st.markdown(
        "Mostra a jornada dos contratos atrasados ao longo do mês: do total que "
        "iniciou o mês em atraso, quantos estavam aptos para acionamento, quantos "
        "tiveram MP agendada e quantos tiveram a OS executada com sucesso. "
        "**Capture uma vez no dia 01 do mês** — o painel calcula o restante automaticamente."
    )
    
    hoje_funil = datetime.now(FUSO_BR)
    mes_funil = hoje_funil.month
    ano_funil = hoje_funil.year
    nomes_meses_funil = {
        1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
        7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
    }
    rotulo_mes_funil = f"{nomes_meses_funil[mes_funil]}/{ano_funil}"
    
    # Monta o SNAPSHOT do momento (lista de contratos atrasados + se tinha OS aberta)
    df_snapshot = df_ativos_reais[df_ativos_reais['Atraso_Base'] == AtrasoBase.ATRASADO].copy()
    df_snapshot_export = df_snapshot[[
        'FOZ_CodigoItem__c', 'Account.CNPJ__c', 'Classificacao', 
        'Status_Financeiro', 'Tem_OS_Aberta'
    ]].copy()
    df_snapshot_export.columns = ['Cod_Item', 'CNPJ', 'Classificacao', 
                                   'Status_Financeiro', 'Tinha_OS_Aberta_No_Snapshot']
    df_snapshot_export['Mes_Referencia'] = rotulo_mes_funil
    df_snapshot_export['Ano'] = ano_funil
    df_snapshot_export['Mes'] = mes_funil
    df_snapshot_export['Data_Snapshot'] = hoje_funil.strftime('%d/%m/%Y %H:%M')
    
    # ---- BOTÃO DE CAPTURA ----
    col_cap1, col_cap2 = st.columns([1, 3])
    with col_cap1:
        capturar_funil = st.button("📸 Capturar Atrasos do Dia 01", type="primary", key="btn_capturar_funil")
    with col_cap2:
        st.caption(
            f"Capturando para o mês de referência **{rotulo_mes_funil}** "
            f"(**{len(df_snapshot_export)}** contratos em atraso neste momento). "
            f"Recaptura no mesmo mês substitui a anterior."
        )
    
    if capturar_funil:
        if df_snapshot_export.empty:
            st.warning("Não há contratos em atraso para capturar neste momento.")
        else:
            # Junta com o histórico (se houver), removendo qualquer captura anterior do MESMO mês
            if os.path.exists(ARQUIVO_FUNIL):
                try:
                    df_funil_hist = ler_csv_seguro(ARQUIVO_FUNIL)
                    if 'Mes_Referencia' in df_funil_hist.columns:
                        df_funil_hist = df_funil_hist[df_funil_hist['Mes_Referencia'] != rotulo_mes_funil]
                        df_funil_atualizado = pd.concat([df_funil_hist, df_snapshot_export], ignore_index=True)
                    else:
                        # Arquivo antigo com estrutura agregada — descarta
                        df_funil_atualizado = df_snapshot_export
                except Exception:
                    df_funil_atualizado = df_snapshot_export
            else:
                df_funil_atualizado = df_snapshot_export
            
            st.success(
                f"✅ Snapshot de {rotulo_mes_funil} capturado com {len(df_snapshot_export)} contratos! "
                f"Use uma das duas formas abaixo para atualizar o arquivo do projeto."
            )
            
            csv_funil_str = df_funil_atualizado.to_csv(index=False)
            csv_funil_bytes = csv_funil_str.encode('utf-8-sig')
            
            # Tabs com as duas opções de saída
            tab_download, tab_copiar = st.tabs(["📥 Baixar arquivo", "📋 Copiar e colar (sem download)"])
            
            with tab_download:
                st.caption(
                    "Clique no botão para baixar o arquivo CSV e substituir o `historico_funil.csv` "
                    "na pasta do projeto."
                )
                st.download_button(
                    label="📥 Baixar historico_funil.csv",
                    data=csv_funil_bytes,
                    file_name="historico_funil.csv",
                    mime="text/csv",
                    key="dl_funil_csv"
                )
            
            with tab_copiar:
                st.caption(
                    "**Use esta opção se sua rede bloqueia downloads.** "
                    "1) Clique no ícone de copiar no canto superior direito da caixa abaixo. "
                    "2) Abra o Bloco de Notas (ou VS Code). "
                    "3) Cole (Ctrl+V) e salve como **`historico_funil.csv`** — "
                    "no Bloco de Notas, escolha **Codificação: UTF-8** e nome com aspas: `\"historico_funil.csv\"`. "
                    "4) Substitua o arquivo na pasta do projeto."
                )
                st.code(csv_funil_str, language="csv")
                st.info(
                    f"📊 **{len(df_funil_atualizado):,} linhas** no arquivo total — "
                    f"se for muito grande, use o Bloco de Notas (lida bem com arquivos grandes).".replace(",", ".")
                )
    
    # ---- VISUALIZAÇÃO ----
    st.markdown("#### 📊 Visualização")
    
    if not os.path.exists(ARQUIVO_FUNIL):
        st.info(
            "Nenhum snapshot capturado ainda. Clique em **📸 Capturar Atrasos do Dia 01** acima, "
            "baixe o arquivo e suba para a pasta do projeto."
        )
    else:
        try:
            df_funil_view = ler_csv_seguro(ARQUIVO_FUNIL)
            
            # Validação: estrutura nova precisa ter Cod_Item e Tinha_OS_Aberta_No_Snapshot
            colunas_esperadas = ['Mes_Referencia', 'Ano', 'Mes', 'Cod_Item', 
                                 'CNPJ', 'Classificacao', 'Status_Financeiro', 
                                 'Tinha_OS_Aberta_No_Snapshot', 'Data_Snapshot']
            colunas_faltando = [c for c in colunas_esperadas if c not in df_funil_view.columns]
            
            if colunas_faltando:
                # Detecta se as colunas "encontradas" parecem ser lixo de XLSX
                colunas_str = ", ".join(map(str, df_funil_view.columns.tolist()))
                parece_xlsx = 'PK' in colunas_str or 'Content_Types' in colunas_str or 'xml' in colunas_str
                
                if parece_xlsx:
                    st.error(
                        "⚠️ **O arquivo `historico_funil.csv` na pasta é um Excel (.xlsx) renomeado, "
                        "não um CSV de verdade.** Excel e CSV têm formatos internos diferentes — "
                        "renomear a extensão não converte um no outro."
                    )
                    st.markdown(
                        "**Para resolver:** \n"
                        "1. Clique em **📸 Capturar Atrasos do Dia 01** acima.\n"
                        "2. Na seção que aparecer, use a aba **📋 Copiar e colar** (se sua rede bloqueia downloads).\n"
                        "3. Cole o conteúdo no Bloco de Notas, salve como `historico_funil.csv` "
                        "(com aspas no nome para não virar .txt), e suba pro GitHub."
                    )
                else:
                    st.error(
                        f"⚠️ O arquivo `historico_funil.csv` está com estrutura antiga ou incorreta. "
                        f"Colunas faltando: **{', '.join(colunas_faltando)}**."
                    )
                    st.markdown(
                        "Clique em **📸 Capturar Atrasos do Dia 01** para gerar um arquivo novo no formato correto. "
                        "Se sua rede bloqueia downloads, use a aba **📋 Copiar e colar** que aparece após a captura."
                    )
                
                with st.expander("🔎 Diagnóstico — colunas detectadas no arquivo"):
                    st.code(colunas_str)
            else:
                # Filtros
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    meses_disp = df_funil_view['Mes_Referencia'].drop_duplicates().tolist()
                    meses_ord = sorted(meses_disp, key=lambda m: (
                        df_funil_view[df_funil_view['Mes_Referencia'] == m]['Ano'].iloc[0],
                        df_funil_view[df_funil_view['Mes_Referencia'] == m]['Mes'].iloc[0]
                    ))
                    mes_sel = st.selectbox("Mês:", meses_ord, index=len(meses_ord)-1, key="funil_mes")
                with col_f2:
                    classifs = ["(Todas)"] + sorted(df_funil_view['Classificacao'].dropna().unique().tolist())
                    classif_sel = st.selectbox("Tipo de Cliente:", classifs, key="funil_classif")
                with col_f3:
                    status_fins = ["(Todos)"] + sorted(df_funil_view['Status_Financeiro'].dropna().unique().tolist())
                    status_sel = st.selectbox("Status Financeiro:", status_fins, key="funil_status")
                
                # Aplica filtros sobre a lista de contratos do snapshot
                df_fv = df_funil_view[df_funil_view['Mes_Referencia'] == mes_sel].copy()
                if classif_sel != "(Todas)":
                    df_fv = df_fv[df_fv['Classificacao'] == classif_sel]
                if status_sel != "(Todos)":
                    df_fv = df_fv[df_fv['Status_Financeiro'] == status_sel]
                
                if df_fv.empty:
                    st.warning("Nenhum dado para os filtros selecionados.")
                else:
                    # Identifica o mês/ano do snapshot e a data exata
                    ano_snap = int(df_fv['Ano'].iloc[0])
                    mes_snap = int(df_fv['Mes'].iloc[0])
                    # Data do snapshot (primeira data registrada para o mês)
                    try:
                        data_snap_str = df_fv['Data_Snapshot'].iloc[0]
                        data_snap = pd.to_datetime(data_snap_str, format='%d/%m/%Y %H:%M')
                    except Exception:
                        # Fallback: primeiro dia do mês
                        data_snap = pd.Timestamp(year=ano_snap, month=mes_snap, day=1)
                    
                    # X e Y vêm DIRETO do snapshot (estado congelado no dia 01)
                    X = len(df_fv)
                    # Y = aptos no momento do snapshot (sem OS aberta naquela hora)
                    # Trata o boolean que pode ter virado string ao salvar/ler do CSV
                    serie_tinha_os = df_fv['Tinha_OS_Aberta_No_Snapshot'].astype(str).str.lower()
                    Y = int((serie_tinha_os == 'false').sum())
                    
                    # Z e W são calculados EM TEMPO REAL, lendo as OS de MP do Salesforce
                    # e verificando quais delas pertencem aos contratos do snapshot
                    df_os_mp_atual = df_final.attrs.get('os_mp', pd.DataFrame())
                    
                    if df_os_mp_atual.empty:
                        Z = 0
                        W = 0
                        aviso_os = "⚠️ Não há OS de MP carregadas do Salesforce — Z e W não puderam ser calculados."
                    else:
                        # OS de MP criadas DEPOIS do snapshot E DENTRO do mês de referência
                        # (mês fechado: só conta o que aconteceu naquele mês)
                        from pandas import Timestamp
                        inicio_mes = Timestamp(year=ano_snap, month=mes_snap, day=1)
                        if mes_snap == 12:
                            fim_mes = Timestamp(year=ano_snap+1, month=1, day=1)
                        else:
                            fim_mes = Timestamp(year=ano_snap, month=mes_snap+1, day=1)
                        
                        df_os_periodo = df_os_mp_atual[
                            (df_os_mp_atual['CreatedDate'] >= data_snap) &
                            (df_os_mp_atual['CreatedDate'] < fim_mes)
                        ].copy()
                        
                        # Só conta OS de contratos que estavam no snapshot E que estavam APTOS
                        # (sem OS aberta no momento do snapshot — coerente com o funil)
                        # Normaliza Cod_Item removendo zeros à esquerda em AMBOS os lados
                        # (o CSV pode perder zeros e o Salesforce mantém — sem isso, perderia matches)
                        cods_aptos = set(
                            df_fv[serie_tinha_os == 'false']['Cod_Item']
                            .astype(str).str.lstrip('0')
                        )
                        df_os_aptos = df_os_periodo[
                            df_os_periodo['CodigoItem'].astype(str).str.lstrip('0').isin(cods_aptos)
                        ]
                        
                        # Z = contratos aptos que ganharam pelo menos 1 OS de MP no mês (dedup por contrato)
                        cods_com_os = set(df_os_aptos['CodigoItem'].dropna().astype(str))
                        Z = len(cods_com_os)
                        
                        # W = dos Z, quantos tiveram a OS executada com sucesso
                        df_os_sucesso = df_os_aptos[df_os_aptos['Status_Caso'] == 'Executado com Sucesso']
                        cods_com_sucesso = set(df_os_sucesso['CodigoItem'].dropna().astype(str))
                        W = len(cods_com_sucesso)
                        aviso_os = None
                    
                    if aviso_os:
                        st.warning(aviso_os)
                    
                    # Legenda explicativa — para o leitor (diretoria) entender o funil de bate-pronto
                    st.markdown(
                        """
                        <div style='background-color:#f1f5f9; border-left:4px solid #1f77b4; padding:14px 18px; border-radius:6px; margin-bottom:18px;'>
                            <div style='font-size:13px; font-weight:700; color:#0f172a; margin-bottom:8px;'>📖 Como ler este funil</div>
                            <table style='width:100%; font-size:12px; color:#334155; border-collapse:collapse;'>
                                <tr>
                                    <td style='padding:4px 8px; vertical-align:top; width:40px;'><span style='display:inline-block; width:14px; height:14px; background-color:#1f77b4; border-radius:3px;'></span></td>
                                    <td style='padding:4px 8px;'><b>Iniciaram o mês em atraso</b> — contratos cuja manutenção preventiva já estava vencida (passou da data de vencimento) na foto do dia 01.</td>
                                </tr>
                                <tr>
                                    <td style='padding:4px 8px; vertical-align:top;'><span style='display:inline-block; width:14px; height:14px; background-color:#17a2b8; border-radius:3px;'></span></td>
                                    <td style='padding:4px 8px;'><b>Aptos para acionamento</b> — destes, os que ainda não tinham nenhuma ordem de serviço aberta (passíveis de novo contato).</td>
                                </tr>
                                <tr>
                                    <td style='padding:4px 8px; vertical-align:top;'><span style='display:inline-block; width:14px; height:14px; background-color:#ffc107; border-radius:3px;'></span></td>
                                    <td style='padding:4px 8px;'><b>MP agendada no mês</b> — destes aptos, quantos efetivamente tiveram uma ordem de manutenção preventiva criada durante o mês.</td>
                                </tr>
                                <tr>
                                    <td style='padding:4px 8px; vertical-align:top;'><span style='display:inline-block; width:14px; height:14px; background-color:#28a745; border-radius:3px;'></span></td>
                                    <td style='padding:4px 8px;'><b>OS de MP baixada com sucesso</b> — destes agendados, quantos tiveram a manutenção concluída e executada com sucesso.</td>
                                </tr>
                            </table>
                            <div style='font-size:11px; color:#64748b; margin-top:10px; font-style:italic;'>
                                💡 Os percentuais no gráfico mostram a proporção em relação ao início do funil (etapa azul). Quanto menor a queda entre as etapas, melhor está a operação convertendo atrasos em manutenções concluídas.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    # Gráfico de funil
                    etapas = [
                        'Iniciaram o mês em atraso',
                        'Aptos para acionamento',
                        'MP agendada no mês',
                        'OS de MP baixada com sucesso'
                    ]
                    valores = [X, Y, Z, W]
                    
                    fig_funil = go.Figure(go.Funnel(
                        y=etapas,
                        x=valores,
                        textposition="inside",
                        textinfo="value+percent initial",
                        marker={"color": ["#1f77b4", "#17a2b8", "#ffc107", "#28a745"]},
                        connector={"line": {"color": "#cbd5e1", "width": 1}}
                    ))
                    fig_funil.update_layout(
                        title=f"Funil de Conversão — {mes_sel}",
                        margin={"t": 50, "b": 20, "l": 20, "r": 20},
                        height=400
                    )
                    fig_funil = aplicar_tema_moderno(fig_funil)
                    st.plotly_chart(fig_funil, use_container_width=True)
                    
                    # KPIs de conversão
                    col_c1, col_c2, col_c3 = st.columns(3)
                    conv_xy = (Y / X * 100) if X > 0 else 0
                    conv_yz = (Z / Y * 100) if Y > 0 else 0
                    conv_zw = (W / Z * 100) if Z > 0 else 0
                    col_c1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso → Aptos"}</div><div class="kpi-value">{f"{conv_xy:.1f}%"}</div><div class="kpi-delta">{f"{Y} de {X}"}</div></div>''', unsafe_allow_html=True)
                    col_c2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Aptos → Agendados"}</div><div class="kpi-value">{f"{conv_yz:.1f}%"}</div><div class="kpi-delta">{f"{Z} de {Y}"}</div></div>''', unsafe_allow_html=True)
                    col_c3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Agendados → Baixados"}</div><div class="kpi-value">{f"{conv_zw:.1f}%"}</div><div class="kpi-delta">{f"{W} de {Z}"}</div></div>''', unsafe_allow_html=True)
                    
                    # Evolução mês a mês (se houver mais de um mês capturado)
                    if len(meses_ord) > 1:
                        st.markdown("#### 📈 Evolução mês a mês")
                        # Para cada mês, recalcula X/Y/Z/W (a mesma lógica acima, sem filtros)
                        linhas_evol = []
                        for mes_lbl in meses_ord:
                            sub = df_funil_view[df_funil_view['Mes_Referencia'] == mes_lbl]
                            if classif_sel != "(Todas)":
                                sub = sub[sub['Classificacao'] == classif_sel]
                            if status_sel != "(Todos)":
                                sub = sub[sub['Status_Financeiro'] == status_sel]
                            if sub.empty:
                                continue
                            
                            ano_m = int(sub['Ano'].iloc[0])
                            mes_m = int(sub['Mes'].iloc[0])
                            try:
                                data_m = pd.to_datetime(sub['Data_Snapshot'].iloc[0], format='%d/%m/%Y %H:%M')
                            except Exception:
                                data_m = pd.Timestamp(year=ano_m, month=mes_m, day=1)
                            
                            X_m = len(sub)
                            serie_tinha_os_m = sub['Tinha_OS_Aberta_No_Snapshot'].astype(str).str.lower()
                            Y_m = int((serie_tinha_os_m == 'false').sum())
                            
                            if not df_os_mp_atual.empty:
                                if mes_m == 12:
                                    fim_m = Timestamp(year=ano_m+1, month=1, day=1)
                                else:
                                    fim_m = Timestamp(year=ano_m, month=mes_m+1, day=1)
                                df_os_p = df_os_mp_atual[
                                    (df_os_mp_atual['CreatedDate'] >= data_m) &
                                    (df_os_mp_atual['CreatedDate'] < fim_m)
                                ]
                                cods_aptos_m = set(
                                    sub[serie_tinha_os_m == 'false']['Cod_Item']
                                    .astype(str).str.lstrip('0')
                                )
                                df_os_aptos_m = df_os_p[
                                    df_os_p['CodigoItem'].astype(str).str.lstrip('0').isin(cods_aptos_m)
                                ]
                                Z_m = df_os_aptos_m['CodigoItem'].dropna().nunique()
                                W_m = df_os_aptos_m[df_os_aptos_m['Status_Caso'] == 'Executado com Sucesso']['CodigoItem'].dropna().nunique()
                            else:
                                Z_m = 0
                                W_m = 0
                            
                            linhas_evol.append({
                                'Mes': mes_lbl, '_ano': ano_m, '_mes': mes_m,
                                'Iniciaram atraso': X_m, 'Aptos': Y_m,
                                'MP agendada': Z_m, 'OS baixada': W_m
                            })
                        
                        if linhas_evol:
                            df_evol_plot = pd.DataFrame(linhas_evol).sort_values(['_ano', '_mes'])
                            fig_evol = px.line(
                                df_evol_plot, x='Mes',
                                y=['Iniciaram atraso', 'Aptos', 'MP agendada', 'OS baixada'],
                                markers=True, title="Evolução das etapas do funil",
                                color_discrete_map={
                                    'Iniciaram atraso': '#1f77b4', 'Aptos': '#17a2b8',
                                    'MP agendada': '#ffc107', 'OS baixada': '#28a745'
                                }
                            )
                            fig_evol.update_layout(yaxis_title="Contratos", xaxis_title="Mês")
                            fig_evol = aplicar_tema_moderno(fig_evol)
                            st.plotly_chart(fig_evol, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao processar o funil: {e}")

# === ABA 7: SEM COBERTURA DE CEP ===
with aba_sem_cobertura:
    st.markdown("### 📍 Contratos Sem Cobertura de CEP")
    st.markdown(
        "Máquinas cujo CEP cadastrado **não casa com nenhum range** da planilha de Range CEP. "
        "Estes contratos ficam invisíveis nas análises de capacidade e mailing — corrigir o cadastro "
        "(no Salesforce ou no arquivo de ranges) os reincorpora à operação automaticamente."
    )
    
    if not prestador_mapeado:
        st.warning(
            "⚠️ A análise de cobertura depende dos arquivos `Range CEP.xlsx` e `De-Para.xlsx`. "
            "Coloque ambos na pasta do app para visualizar esta aba."
        )
    else:
        # Identifica os contratos sem cobertura: Prestador_CEP nulo após o mapeamento
        df_sem_cob = df_ativos_reais[df_ativos_reais['Prestador_CEP'].isnull()].copy()
        
        if len(df_sem_cob) == 0:
            st.success("✅ Todos os contratos da base ativa estão com cobertura de CEP. Nenhuma correção cadastral necessária.")
        else:
            # KPIs consolidados
            total_sc = len(df_sem_cob)
            atrasados_sc = len(df_sem_cob[df_sem_cob['Atraso_Base'] == AtrasoBase.ATRASADO])
            em_dia_sc = len(df_sem_cob[df_sem_cob['Atraso_Base'] == AtrasoBase.EM_DIA])
            criticos_sc = len(df_sem_cob[df_sem_cob['Status_MP_Real'] == StatusMP.CRITICO])
            adim_sc = len(df_sem_cob[df_sem_cob['Status_Financeiro'] == StatusFin.ADIMPLENTE])
            inadim_sc = len(df_sem_cob[df_sem_cob['Status_Financeiro'] == StatusFin.INADIMPLENTE])
            
            with st.container(border=True):
                st.markdown("#### 📊 Resumo da Base Sem Cobertura")
                col1, col2, col3, col4, col5, col6 = st.columns(6)
                col1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Total"}</div><div class="kpi-value">{f"{total_sc:,}".replace(",", ".")}</div><div class="kpi-delta">{"Sem cobertura"}</div></div>''', unsafe_allow_html=True)
                col2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"MP Em Dia"}</div><div class="kpi-value">{f"{em_dia_sc:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                col3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Em Atraso"}</div><div class="kpi-value">{f"{atrasados_sc:,}".replace(",", ".")}</div><div class="kpi-delta">{f"{(atrasados_sc/total_sc*100):.1f}% do segmento" if total_sc > 0 else "0%"}</div></div>''', unsafe_allow_html=True)
                col4.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Atraso"}</div><div class="kpi-value">{f"{criticos_sc:,}".replace(",", ".")}</div><div class="kpi-delta">{"Sem capacidade definida"}</div></div>''', unsafe_allow_html=True)
                col5.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Adimplentes"}</div><div class="kpi-value">{f"{adim_sc:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
                col6.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Inadimplentes"}</div><div class="kpi-value">{f"{inadim_sc:,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
            
            st.write("")
            
            # Quebra por UF (primeiros 2 dígitos do CEP definem a faixa de UF)
            # Tabela de faixas de CEP por UF (segundo Correios)
            def cep_para_uf(cep_num):
                """Retorna a UF a partir do CEP numérico."""
                if pd.isna(cep_num):
                    return 'CEP Inválido'
                cep_int = int(cep_num)
                # Faixas oficiais dos Correios (resumidas, primeiros dígitos do CEP)
                if 1000000 <= cep_int <= 19999999: return 'SP'
                elif 20000000 <= cep_int <= 28999999: return 'RJ'
                elif 29000000 <= cep_int <= 29999999: return 'ES'
                elif 30000000 <= cep_int <= 39999999: return 'MG'
                elif 40000000 <= cep_int <= 48999999: return 'BA'
                elif 49000000 <= cep_int <= 49999999: return 'SE'
                elif 50000000 <= cep_int <= 56999999: return 'PE'
                elif 57000000 <= cep_int <= 57999999: return 'AL'
                elif 58000000 <= cep_int <= 58999999: return 'PB'
                elif 59000000 <= cep_int <= 59999999: return 'RN'
                elif 60000000 <= cep_int <= 63999999: return 'CE'
                elif 64000000 <= cep_int <= 64999999: return 'PI'
                elif 65000000 <= cep_int <= 65999999: return 'MA'
                elif 66000000 <= cep_int <= 68899999: return 'PA'
                elif 68900000 <= cep_int <= 68999999: return 'AP'
                elif 69000000 <= cep_int <= 69299999: return 'AM'
                elif 69300000 <= cep_int <= 69399999: return 'RR'
                elif 69400000 <= cep_int <= 69899999: return 'AM'
                elif 69900000 <= cep_int <= 69999999: return 'AC'
                elif 70000000 <= cep_int <= 72799999: return 'DF'
                elif 72800000 <= cep_int <= 72999999: return 'GO'
                elif 73000000 <= cep_int <= 73699999: return 'DF'
                elif 73700000 <= cep_int <= 76799999: return 'GO'
                elif 76800000 <= cep_int <= 76999999: return 'RO'
                elif 77000000 <= cep_int <= 77999999: return 'TO'
                elif 78000000 <= cep_int <= 78899999: return 'MT'
                elif 79000000 <= cep_int <= 79999999: return 'MS'
                elif 80000000 <= cep_int <= 87999999: return 'PR'
                elif 88000000 <= cep_int <= 89999999: return 'SC'
                elif 90000000 <= cep_int <= 99999999: return 'RS'
                else: return 'Faixa Desconhecida'
            
            df_sem_cob['UF_Estimada'] = df_sem_cob['CEP_Num'].apply(cep_para_uf)
            
            # Distribuição por UF
            with st.container(border=True):
                st.markdown("#### 🗺️ Distribuição por UF (estimada pelo CEP)")
                st.caption("A UF é inferida a partir das faixas oficiais de CEP dos Correios. Útil para direcionar a correção do cadastro de ranges.")
                
                dist_uf = df_sem_cob.groupby('UF_Estimada').agg(
                    Total=('FOZ_CodigoItem__c', 'size'),
                    Em_Atraso=('Atraso_Base', lambda x: (x == AtrasoBase.ATRASADO).sum()),
                    Criticos=('Status_MP_Real', lambda x: (x == StatusMP.CRITICO).sum()),
                ).reset_index().sort_values(by='Total', ascending=False)
                dist_uf.columns = ['UF', 'Total', 'Em Atraso', 'Atraso']
                
                st.dataframe(
                    dist_uf.style.background_gradient(cmap='Reds', subset=['Total', 'Em Atraso', 'Atraso']),
                    use_container_width=True, hide_index=True
                )
            
            st.write("")
            
            # Lista detalhada
            with st.container(border=True):
                st.markdown("#### 📋 Lista Detalhada (para correção cadastral)")
                
                # Filtro por UF para facilitar o tratamento
                lista_ufs = ["Todas"] + sorted(df_sem_cob['UF_Estimada'].unique().tolist())
                col_filtro_uf, col_filtro_status = st.columns(2)
                with col_filtro_uf:
                    filtro_uf_sc = st.selectbox("Filtrar UF:", lista_ufs, key="filtro_uf_sem_cob")
                with col_filtro_status:
                    filtro_status_sc = st.selectbox(
                        "Filtrar Status:", 
                        ["Todos", "Em Atraso (todos)", "Em Atraso (sem ação)", "Apenas Em Dia"],
                        key="filtro_status_sem_cob"
                    )
                
                df_view_sc = df_sem_cob.copy()
                if filtro_uf_sc != "Todas":
                    df_view_sc = df_view_sc[df_view_sc['UF_Estimada'] == filtro_uf_sc]
                if filtro_status_sc == "Em Atraso (todos)":
                    df_view_sc = df_view_sc[df_view_sc['Atraso_Base'] == AtrasoBase.ATRASADO]
                elif filtro_status_sc == "Em Atraso (sem ação)":
                    df_view_sc = df_view_sc[df_view_sc['Status_MP_Real'] == StatusMP.CRITICO]
                elif filtro_status_sc == "Apenas Em Dia":
                    df_view_sc = df_view_sc[df_view_sc['Atraso_Base'] == AtrasoBase.EM_DIA]
                
                st.caption(f"Exibindo **{len(df_view_sc):,} contrato(s)** com os filtros aplicados.".replace(",", "."))
                
                if len(df_view_sc) > 0:
                    df_view_sc['Data_Vencimento_MP'] = df_view_sc['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
                    df_exibicao_sc = df_view_sc[[
                        'FOZ_CodigoItem__c', 'Account.Name', 'CEP_Limpo', 'UF_Estimada',
                        'FOZ_EndFranquiaForm__c', 'Status_MP_Real', 'AGING_MP', 'Status_Financeiro',
                        'Data_Vencimento_MP'
                    ]].rename(columns={
                        'FOZ_CodigoItem__c': 'Cód. Item',
                        'Account.Name': 'Cliente',
                        'CEP_Limpo': 'CEP',
                        'UF_Estimada': 'UF (estimada)',
                        'FOZ_EndFranquiaForm__c': 'Franquia Cadastrada (SF)',
                        'Status_MP_Real': 'Status da MP',
                        'AGING_MP': 'Aging',
                        'Status_Financeiro': 'Status Fin.',
                        'Data_Vencimento_MP': 'Vencimento MP'
                    })
                    
                    st.dataframe(df_exibicao_sc, use_container_width=True, hide_index=True)
                    
                    st.download_button(
                        label="📥 Baixar lista para correção (Excel)",
                        data=df_para_excel_bytes(df_exibicao_sc, 'SemCoberturaCEP'),
                        file_name=f"sem_cobertura_cep_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.ms-excel",
                        key="dl_sem_cobertura"
                    )
                else:
                    st.info("Nenhum contrato encontrado com os filtros aplicados.")
        
        # ----------------------------------------
        # 🔬 DIAGNÓSTICO DE CEP — ferramenta de troubleshoot
        # ----------------------------------------
        st.write("")
        with st.container(border=True):
            st.markdown("#### 🔬 Diagnóstico de CEP (Ferramenta de Investigação)")
            st.markdown(
                "Cole um CEP para entender exatamente **por que** ele aparece como sem cobertura "
                "(ou para confirmar em qual prestador ele cai). Útil para identificar erros de cadastro, "
                "ranges faltantes ou mapeamentos DE-PARA ausentes."
            )
            
            col_input, col_btn_diag = st.columns([3, 1])
            with col_input:
                cep_input = st.text_input(
                    "CEP para diagnosticar:",
                    placeholder="Ex.: 05707-001 ou 05707001",
                    key="cep_diagnostico"
                )
            with col_btn_diag:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                executar_diag = st.button("Investigar", key="btn_diag_cep")
            
            if executar_diag and cep_input:
                # Limpa e converte o CEP
                cep_limpo = re.sub(r'\D', '', str(cep_input))
                if len(cep_limpo) == 0:
                    st.error("CEP inválido. Digite apenas números (com ou sem traço).")
                else:
                    try:
                        cep_num = int(cep_limpo)
                        diag = diagnosticar_cep(cep_num, df_ranges, dict_depara)
                        
                        # Bloco 1: Status final
                        if diag['mapeamento_aplicado']:
                            st.success(
                                f"✅ **CEP {cep_input} mapeado com sucesso para o prestador "
                                f"`{diag['mapeamento_aplicado']}`**"
                            )
                        else:
                            st.error(f"❌ **CEP {cep_input} NÃO foi mapeado para nenhum prestador.**")
                            st.caption(f"**Motivo:** {diag['motivo_falha']}")
                        
                        # Bloco 2: Ranges em que o CEP cai
                        st.markdown("**📋 Ranges encontrados no arquivo Range CEP.xlsx:**")
                        if diag['qtd_ranges'] == 0:
                            st.info(
                                f"O CEP `{cep_input}` (número {cep_num}) "
                                f"**não cai em nenhum range cadastrado**. "
                                f"O arquivo Range CEP.xlsx precisa de uma nova entrada cobrindo essa faixa."
                            )
                        else:
                            df_ranges_diag = diag['ranges_encontrados'][[
                                'Nome Service Area', 'Cep "De"', 'Cep "Até"', 'GRADE'
                            ]].reset_index(drop=True)
                            df_ranges_diag.index = df_ranges_diag.index + 1
                            st.dataframe(df_ranges_diag, use_container_width=True)
                            
                            if diag['tem_sobreposicao']:
                                st.warning(
                                    f"⚠️ **Atenção: este CEP cai em {diag['qtd_ranges']} ranges sobrepostos.** "
                                    f"O sistema escolhe automaticamente o **primeiro** da lista acima "
                                    f"(`{diag['franquia_escolhida']}` / `{diag['grade_escolhida']}`). "
                                    f"Se o prestador correto for outro, será necessário ajustar o arquivo "
                                    f"Range CEP.xlsx removendo a sobreposição."
                                )
                            else:
                                st.caption(
                                    f"O CEP cai em **1 range único**: Service Area "
                                    f"`{diag['franquia_escolhida']}` com Grade `{diag['grade_escolhida']}`."
                                )
                        
                        # Bloco 3: Verificação no DE-PARA
                        if diag['qtd_ranges'] > 0:
                            st.markdown("**🔗 Verificação no DE-PARA da planilha de Capacidade:**")
                            chave = (diag['franquia_escolhida'], diag['grade_escolhida'])
                            if diag['depara_existe']:
                                st.success(
                                    f"✅ Existe mapeamento para `{chave[0]}` + `{chave[1]}` → "
                                    f"`{diag['mapeamento_aplicado']}`"
                                )
                            else:
                                st.error(
                                    f"❌ **NÃO existe mapeamento** para `{chave[0]}` + `{chave[1]}` no DE-PARA. "
                                    f"Adicione essa combinação na aba DE>PARA do arquivo Capacidade.xlsx "
                                    f"para resolver o problema."
                                )
                    except ValueError:
                        st.error(f"Não consegui interpretar o CEP `{cep_input}` como número.")
        
        # ----------------------------------------
        # ⚠️ DIAGNÓSTICO: duplicatas no DE-PARA
        # ----------------------------------------
        if duplicatas_depara:
            with st.container(border=True):
                st.markdown("#### ⚠️ Duplicatas detectadas no DE-PARA")
                st.markdown(
                    f"Foram encontradas **{len(duplicatas_depara)} entrada(s) duplicada(s)** no arquivo "
                    f"Capacidade.xlsx (aba DE>PARA). Quando duas linhas têm a mesma combinação "
                    f"(Franquia + Grade), apenas a última prevalece — as anteriores são silenciosamente perdidas."
                )
                st.dataframe(pd.DataFrame(duplicatas_depara), use_container_width=True, hide_index=True)


# === ABA 10: CONSULTA DE ASSET ===
with aba_consulta:
    st.markdown("### 🔍 Consulta Rápida de Asset")
    st.markdown(
        "Cole uma lista de **Códigos de Item** (um por linha, ou separados por vírgula/espaço) "
        "para consultar o status completo de cada contrato na base atual."
    )
    
    # Área de input
    texto_codigos = st.text_area(
        "Códigos de Item para consultar:",
        placeholder="Exemplos:\n17181\n28553\n28554\n\nOu separados por vírgula: 17181, 28553, 28554",
        height=150,
        key="textarea_consulta_asset"
    )
    
    col_btn, col_info = st.columns([1, 4])
    with col_btn:
        consultar = st.button("🔎 Consultar", type="primary", key="btn_consulta_asset")
    
    if consultar and texto_codigos.strip():
        # Parse robusto: aceita quebras de linha, vírgulas, ponto-vírgula, tabs e espaços
        codigos_brutos = re.split(r'[\n,;\t\s]+', texto_codigos.strip())
        # Normaliza para string sem espaços e descarta vazios
        codigos_buscados = [c.strip() for c in codigos_brutos if c.strip()]
        # Remove duplicatas preservando ordem
        codigos_buscados = list(dict.fromkeys(codigos_buscados))
        
        if not codigos_buscados:
            st.warning("Nenhum código válido foi identificado no texto inserido.")
        else:
            # A comparação precisa ser robusta a tipos E a zeros à esquerda
            # (Salesforce usa '00017143', usuário pode digitar '17143')
            df_busca = df_final.copy()
            df_busca['_codigo_str'] = df_busca['FOZ_CodigoItem__c'].astype(str).str.strip()
            df_busca['_codigo_norm'] = df_busca['_codigo_str'].str.lstrip('0')
            codigos_norm = [c.lstrip('0') for c in codigos_buscados]
            
            # Identifica encontrados e não encontrados (compara sem zeros à esquerda)
            df_encontrados = df_busca[df_busca['_codigo_norm'].isin(codigos_norm)].copy()
            encontrados_norm = set(df_encontrados['_codigo_norm'].tolist())
            nao_encontrados = [codigos_buscados[i] for i, cn in enumerate(codigos_norm) if cn not in encontrados_norm]
            
            # Resumo da consulta
            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Códigos buscados"}</div><div class="kpi-value">{len(codigos_buscados)}</div></div>''', unsafe_allow_html=True)
            col_r2.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Encontrados"}</div><div class="kpi-value">{len(df_encontrados)}</div></div>''', unsafe_allow_html=True)
            col_r3.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Não encontrados"}</div><div class="kpi-value">{len(nao_encontrados)}</div><div class="kpi-delta">{"Inativos ou não existem" if nao_encontrados else "Todos OK"}</div></div>''', unsafe_allow_html=True)
            
            # Lista os não encontrados
            if nao_encontrados:
                with st.expander(f"⚠️ {len(nao_encontrados)} código(s) não encontrado(s) na base"):
                    st.caption(
                        "Estes códigos não vieram do Salesforce na carga atual. Possíveis motivos: "
                        "(1) Asset com status diferente de 'Ativo-Em Operação' (ex.: Inativo, Desinstalado, Cancelado); "
                        "(2) digitados incorretamente; ou (3) não existem. "
                        "Obs.: contratos com OS de desinstalação aberta APARECEM aqui (como 'DESCONSIDERADO'), "
                        "pois não são removidos da carga — apenas das análises de atraso."
                    )
                    st.code("\n".join(nao_encontrados))
            
            st.markdown("---")
            
            if not df_encontrados.empty:
                # LGPD: telefones não são exibidos no painel online
                # (use o gerador local de mailing para obter contatos)
                
                # Formata datas para exibição
                df_encontrados['Vencimento MP'] = df_encontrados['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
                df_encontrados['Última MP'] = pd.to_datetime(df_encontrados.get('FOZ_DataUltimaMP__c'), errors='coerce').dt.strftime('%d/%m/%Y')
                df_encontrados['Tem OS Aberta?'] = df_encontrados['Tem_OS_Aberta'].map({True: 'Sim', False: 'Não'})
                
                # Trata valores nulos visíveis
                df_encontrados['Última MP'] = df_encontrados['Última MP'].fillna('—')
                df_encontrados['Numero_Caso'] = df_encontrados['Numero_Caso'].fillna('—')
                df_encontrados['Tipo_Servico'] = df_encontrados['Tipo_Servico'].fillna('—')
                df_encontrados['Data_Agendamento'] = df_encontrados['Data_Agendamento'].fillna('—')
                
                # Monta a tabela final na ordem que faz sentido para consulta operacional
                cols_consulta = [
                    'FOZ_CodigoItem__c', 'Account.Name', 'Qtd_Contratos_Cliente',
                    'Classificacao', 'Status_Financeiro', 'FOZ_EndFranquiaForm__c', 'CEP_Limpo',
                    'Status_MP_Real', 'AGING_MP', 'Dias_Atraso', 
                    'Vencimento MP', 'Última MP',
                    'Tem OS Aberta?', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento',
                    'SerialNumber'
                ]
                
                # Garante que todas as colunas existam (algumas podem não estar presentes em situações específicas)
                cols_existentes = [c for c in cols_consulta if c in df_encontrados.columns]
                
                df_show = df_encontrados[cols_existentes].rename(columns={
                    'FOZ_CodigoItem__c': 'Cód. Item',
                    'Account.Name': 'Cliente',
                    'Qtd_Contratos_Cliente': 'Qtd Contratos',
                    'Classificacao': 'Classificação',
                    'Status_Financeiro': 'Status Fin.',
                    'FOZ_EndFranquiaForm__c': 'Franquia',
                    'CEP_Limpo': 'CEP',
                    'Status_MP_Real': 'Status MP',
                    'AGING_MP': 'Aging',
                    'Dias_Atraso': 'Dias Atraso',
                    'Numero_Caso': 'Nº OS',
                    'Tipo_Servico': 'Tipo de Serviço',
                    'Data_Agendamento': 'Data OS Agendada',
                    'SerialNumber': 'Nº de Série'
                })
                
                # Preserva a ordem dos códigos colados (útil quando o usuário tem lista priorizada)
                ordem_dict = {c: i for i, c in enumerate(codigos_buscados)}
                df_show['_ordem'] = df_show['Cód. Item'].astype(str).map(ordem_dict)
                df_show = df_show.sort_values('_ordem').drop(columns=['_ordem']).reset_index(drop=True)
                
                st.markdown(f"**📋 {len(df_show)} contrato(s) encontrado(s)**")
                st.dataframe(df_show, use_container_width=True, hide_index=True)
                
                st.download_button(
                    label="📥 Baixar resultado da consulta (Excel)",
                    data=df_para_excel_bytes(df_show, 'Consulta_Asset'),
                    file_name=f"consulta_asset_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.ms-excel",
                    key="dl_consulta_asset"
                )
    elif consultar:
        st.warning("Cole pelo menos um código de item para consultar.")
    else:
        st.info(
            "💡 **Dica:** o campo aceita códigos colados de uma coluna do Excel "
            "(uma linha por código), separados por vírgula, ou misturados. "
            "Códigos duplicados são consolidados automaticamente."
        )
    
    # ============================================================
    # EXTRATO DE CONTRATOS DESCONSIDERADOS (ISENTOS POR DESINSTALAÇÃO)
    # ============================================================
    # Permite validar quais contratos estão sendo escondidos da base de atraso por
    # terem OS de desinstalação aberta. Útil para auditar os "contratos que sumiram".
    st.markdown("---")
    st.markdown("### 🚫 Contratos desconsiderados (OS de desinstalação aberta)")
    st.caption(
        "Contratos que TÊM atraso de MP mas foram retirados das análises por terem "
        "OS de desinstalação aberta. Use este extrato para validar se o volume está correto."
    )
    
    df_isentos_val = df_final[df_final['Atraso_Base'] == AtrasoBase.ISENTO].copy()
    
    if df_isentos_val.empty:
        st.info("Nenhum contrato desconsiderado por desinstalação no momento.")
    else:
        st.markdown(f'''<div class="kpi-container"><div class="kpi-title">{"Total desconsiderados"}</div><div class="kpi-value">{f"{len(df_isentos_val):,}".replace(",", ".")}</div></div>''', unsafe_allow_html=True)
        
        df_isentos_val['Vencimento MP'] = df_isentos_val['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
        cols_is = [
            'FOZ_CodigoItem__c', 'Account.Name',
            'FOZ_EndFranquiaForm__c', 'Status_Financeiro', 'Vencimento MP',
            'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento'
        ]
        cols_is_existentes = [c for c in cols_is if c in df_isentos_val.columns]
        df_isentos_show = df_isentos_val[cols_is_existentes].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente',
            'FOZ_EndFranquiaForm__c': 'Franquia',
            'Status_Financeiro': 'Status Fin.', 'Numero_Caso': 'Nº OS',
            'Tipo_Servico': 'Tipo de Serviço', 'Data_Agendamento': 'Data OS'
        }).fillna({'Nº OS': '-', 'Tipo de Serviço': '-', 'Data OS': '-'})
        
        st.dataframe(df_isentos_show, use_container_width=True, hide_index=True, height=400)
        
        st.download_button(
            label="📥 Baixar desconsiderados (Excel)",
            data=df_para_excel_bytes(df_isentos_show, 'Desconsiderados'),
            file_name=f"desconsiderados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            key="dl_desconsiderados_val"
        )