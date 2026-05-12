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

ARQUIVO_HISTORICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'historico_backlog_mp.csv')
FUSO_BR = pytz.timezone('America/Sao_Paulo')

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA E CSS
# ==========================================
st.set_page_config(
    page_title="Manutenção Preventiva", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
/* Esconder a sidebar completamente — painel executivo, sem ruído operacional */
section[data-testid="stSidebar"] { display: none !important; }
button[kind="header"] { display: none !important; }
div[data-testid="collapsedControl"] { display: none !important; }

/* Esconder o header padrão do Streamlit (barra cinza com menu hamburguer no topo) */
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
footer { display: none !important; }

/* Como o header foi removido, o conteúdo principal pode subir um pouco */
div[data-testid="stAppViewContainer"] > .main { padding-top: 0 !important; }

/* Botão de atualizar discreto no canto superior */
div[data-testid="stButton"] > button[kind="secondary"] {
    background-color: transparent;
    border: 1px solid #cbd5e1;
    color: #475569;
    font-size: 12px;
    padding: 4px 12px;
    height: auto;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
    color: #1e293b;
}

/* Ajuste de Títulos */
h1 { font-size: 1.5rem !important; font-weight: 700 !important; margin-bottom: 0px !important; padding-bottom: 5px !important; }
h3 { font-size: 1.1rem !important; margin-top: 5px !important; margin-bottom: 5px !important; color: #333; }
h4 { font-size: 0.95rem !important; color: #444; margin-bottom: 10px !important; font-weight: 600 !important; }
p { font-size: 0.85rem !important; margin-bottom: 5px !important;}

/* Card individual para cada KPI */
div[data-testid="stMetric"] {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    padding: 12px 15px;
    border-radius: 8px;
    box-shadow: 0px 2px 4px rgba(0,0,0,0.03);
    display: flex;
    flex-direction: column;
    height: 110px; 
}

/* Rótulo do KPI (texto pequeno acima do número) */
div[data-testid="stMetricLabel"],
div[data-testid="stMetricLabel"] p,
div[data-testid="stMetricLabel"] label,
div[data-testid="metric-container"] label {
    font-size: 11px !important;
    font-weight: 700 !important;
    color: #475569 !important;
    margin-bottom: 2px !important;
}

/* Valor do KPI (número grande) — em NEGRITO forte */
div[data-testid="stMetricValue"],
div[data-testid="stMetricValue"] > div,
div[data-testid="metric-container"] > div > div {
    font-size: 22px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
}

/* Delta do KPI (descrição abaixo do número) */
div[data-testid="stMetricDelta"],
div[data-testid="stMetricDelta"] > div {
    font-size: 10px !important;
    font-weight: 600 !important;
}

div.block-container { padding-top: 1.2rem; padding-bottom: 1.2rem; }
div[data-testid="metric-container"] {
    background-color: transparent !important;
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
}
/* Multiselect no topo: deixar mais compacto e visualmente discreto */
div[data-testid="stMultiSelect"] label { 
    font-size: 11px !important; 
    font-weight: 600 !important; 
    color: #475569 !important; 
    margin-bottom: 2px !important;
}
div[data-testid="stMultiSelect"] > div > div { 
    min-height: 32px !important; 
    font-size: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# Topo: apenas o título e subtítulo (controles ficam abaixo, após a carga dos dados)
st.markdown("<h1>📊 Manutenção Preventiva</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #666;'>Visão executiva de atraso, priorização status financeiro, agendamentos e distribuição por franquias e regiões de atendimento.</p>", unsafe_allow_html=True)

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

# ==========================================
# 3. CONEXÃO E PROCESSAMENTO
# ==========================================
@st.cache_data(ttl=21600, show_spinner=False, persist="disk")
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
        Account.PersonEmail, Account.PersonMobilePhone,
        FOZ_EndFranquiaForm__c, FOZ_EnderecoEntrega__r.FOZ_CEP__c
    FROM Asset
    WHERE Status = 'Ativo-Em Operação'
    """
    query_contatos = "SELECT AccountId, Account.FOZ_CNPJ__c FROM Contact WHERE Account.FOZ_CNPJ__c != null"
    query_os = """
    SELECT Case.FOZ_Asset__r.FOZ_CodigoItem__c, Case.CaseNumber, Case.Status, FOZ_Agendado_Data_Periodo__c, FOZ_Tipo_de_Servico__c
    FROM WorkOrder WHERE Case.Type = 'OS' AND Case.Status != 'Cancelado' AND Case.Status != 'Fechado' AND Status != 'Cancelado' AND Status != 'Fechado'
    """
    # Novas queries para captura TODOS os contatos (telefone + e-mail) por cliente,
    # vindos das duas fontes complementares do modelo de dados (Contact e AccountContactRelation).
    # A unicidade é por (CNPJ, telefone/email, fonte).
    query_contatos_completos = """
    SELECT 
        Account.CNPJ__c, Account.FOZ_CNPJ__c,
        FirstName, LastName, MobilePhone, Phone, Email, Title, LastModifiedDate
    FROM Contact 
    WHERE (Account.CNPJ__c != null OR Account.FOZ_CNPJ__c != null)
      AND (MobilePhone != null OR Phone != null OR Email != null)
    """
    query_acr_completos = """
    SELECT 
        Account.CNPJ__c, Account.FOZ_CNPJ__c,
        Contact.FirstName, Contact.LastName, Contact.MobilePhone, Contact.Phone, 
        Contact.Email, Contact.Title, Contact.LastModifiedDate
    FROM AccountContactRelation
    WHERE (Account.CNPJ__c != null OR Account.FOZ_CNPJ__c != null)
      AND (Contact.MobilePhone != null OR Contact.Phone != null OR Contact.Email != null)
    """
    
    registros_ativos = sf.query_all(query_ativos).get('records', [])
    registros_contatos = sf.query_all(query_contatos).get('records', [])
    registros_os = sf.query_all(query_os).get('records', [])
    registros_contatos_completos = sf.query_all(query_contatos_completos).get('records', [])
    registros_acr_completos = sf.query_all(query_acr_completos).get('records', [])
    
    df_ativos = pd.json_normalize(registros_ativos)
    df_contatos = pd.json_normalize(registros_contatos)
    df_contatos_completos = pd.json_normalize(registros_contatos_completos) if registros_contatos_completos else pd.DataFrame()
    df_acr_completos = pd.json_normalize(registros_acr_completos) if registros_acr_completos else pd.DataFrame()
    
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
        
        if data_agendamento_raw:
            try:
                data_limpa = str(data_agendamento_raw).split(' -')[0].strip()
                data_obj = pd.to_datetime(data_limpa, format='%d/%m/%Y').date()
                if data_obj.month == mes_atual and data_obj.year == ano_atual and data_obj >= hoje_data: agendado_mes_atual = True
                if data_obj == hoje_data: agendado_hoje = True
            except Exception:
                falhas_parse_data += 1

        lista_os.append({
            'CodigoItem': asset.get('FOZ_CodigoItem__c'), 'Tem_OS_Aberta': True,
            'Agendado_Mes_Atual': agendado_mes_atual, 'Agendado_Hoje': agendado_hoje,
            'Tem_Data': tem_data, 'Numero_Caso': caso.get('CaseNumber'),
            'Tipo_Servico': tipo_servico, 'Data_Agendamento_Raw': data_agendamento_raw
        })
    
    df_os = pd.DataFrame(lista_os)
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
    df['Atraso_Base'] = np.where(df['Meses_Diff'] >= 1, AtrasoBase.ATRASADO, AtrasoBase.EM_DIA)
    
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
    
    df['Dias_Atraso'] = (hoje_limpo - df['FOZ_DataProximaMP__c']).dt.days
    
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
    
    # ==========================================
    # CONTATOS COMPLETOS (uma linha por contato/canal)
    # ==========================================
    # Monta uma tabela LONGA com todos os contatos disponíveis por CNPJ, vinda de 3 fontes:
    #   1) Dados pessoais do Account (PersonEmail / PersonMobilePhone)
    #   2) Objeto Contact relacionado à Account
    #   3) AccountContactRelation (contatos cross-account)
    # Cada linha representa UM canal (telefone OU e-mail) de UMA pessoa em UMA fonte.
    # A unicidade é por (CNPJ, valor, tipo, fonte) — telefones/emails iguais entre fontes
    # ficam separados para o usuário ver qual fonte tem a informação.
    
    linhas_contatos = []
    
    # FONTE 1: Account pessoa física (PersonEmail / PersonMobilePhone do próprio Asset.Account)
    if 'Account.PersonEmail' in df.columns or 'Account.PersonMobilePhone' in df.columns:
        df_pessoa = df[['Account.CNPJ__c']].copy()
        df_pessoa['CNPJ_Limpo'] = df_pessoa['Account.CNPJ__c']  # já vem limpo
        if 'Account.PersonMobilePhone' in df.columns:
            df_pessoa['Telefone'] = df['Account.PersonMobilePhone']
        else:
            df_pessoa['Telefone'] = None
        if 'Account.PersonEmail' in df.columns:
            df_pessoa['Email'] = df['Account.PersonEmail']
        else:
            df_pessoa['Email'] = None
        df_pessoa = df_pessoa.dropna(subset=['CNPJ_Limpo']).drop_duplicates(subset=['CNPJ_Limpo'])
        for _, row in df_pessoa.iterrows():
            cnpj = row['CNPJ_Limpo']
            if pd.notna(row['Telefone']) and str(row['Telefone']).strip():
                linhas_contatos.append({
                    'CNPJ_Limpo': cnpj, 'Origem': 'Cadastro do Cliente',
                    'Nome_Contato': 'Titular', 'Cargo': '',
                    'Tipo': 'Telefone', 'Valor': str(row['Telefone']).strip()
                })
            if pd.notna(row['Email']) and str(row['Email']).strip():
                linhas_contatos.append({
                    'CNPJ_Limpo': cnpj, 'Origem': 'Cadastro do Cliente',
                    'Nome_Contato': 'Titular', 'Cargo': '',
                    'Tipo': 'E-mail', 'Valor': str(row['Email']).strip()
                })
    
    # Helper para CNPJ do Contact / ACR (pode vir em CNPJ__c ou FOZ_CNPJ__c)
    def _cnpj_unificado(row):
        cnpj1 = row.get('Account.CNPJ__c')
        cnpj2 = row.get('Account.FOZ_CNPJ__c')
        valor = cnpj1 if pd.notna(cnpj1) and str(cnpj1).strip() else cnpj2
        return manter_apenas_numeros(valor) if pd.notna(valor) else None
    
    # FONTE 2: Contact (uma linha por contato relacionado)
    if not df_contatos_completos.empty:
        df_c = df_contatos_completos.copy()
        df_c['CNPJ_Limpo'] = df_c.apply(_cnpj_unificado, axis=1)
        df_c = df_c.dropna(subset=['CNPJ_Limpo'])
        for _, row in df_c.iterrows():
            cnpj = row['CNPJ_Limpo']
            nome = f"{str(row.get('FirstName') or '').strip()} {str(row.get('LastName') or '').strip()}".strip() or 'Sem nome'
            cargo = str(row.get('Title') or '').strip()
            for col, tipo in [('MobilePhone', 'Telefone'), ('Phone', 'Telefone'), ('Email', 'E-mail')]:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    linhas_contatos.append({
                        'CNPJ_Limpo': cnpj, 'Origem': 'Contatos (Contact)',
                        'Nome_Contato': nome, 'Cargo': cargo,
                        'Tipo': tipo, 'Valor': str(val).strip()
                    })
    
    # FONTE 3: AccountContactRelation (contatos cross-account)
    if not df_acr_completos.empty:
        df_a = df_acr_completos.copy()
        # Renomeia as colunas aninhadas Contact.X -> X para reuso do mesmo código
        df_a = df_a.rename(columns={
            'Contact.FirstName': 'FirstName', 'Contact.LastName': 'LastName',
            'Contact.MobilePhone': 'MobilePhone', 'Contact.Phone': 'Phone',
            'Contact.Email': 'Email', 'Contact.Title': 'Title',
            'Contact.LastModifiedDate': 'LastModifiedDate'
        })
        df_a['CNPJ_Limpo'] = df_a.apply(_cnpj_unificado, axis=1)
        df_a = df_a.dropna(subset=['CNPJ_Limpo'])
        for _, row in df_a.iterrows():
            cnpj = row['CNPJ_Limpo']
            nome = f"{str(row.get('FirstName') or '').strip()} {str(row.get('LastName') or '').strip()}".strip() or 'Sem nome'
            cargo = str(row.get('Title') or '').strip()
            for col, tipo in [('MobilePhone', 'Telefone'), ('Phone', 'Telefone'), ('Email', 'E-mail')]:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    linhas_contatos.append({
                        'CNPJ_Limpo': cnpj, 'Origem': 'Contatos (ACR)',
                        'Nome_Contato': nome, 'Cargo': cargo,
                        'Tipo': tipo, 'Valor': str(val).strip()
                    })
    
    df_contatos_long = pd.DataFrame(linhas_contatos)
    if not df_contatos_long.empty:
        # Remove duplicatas exatas (mesmo CNPJ + mesmo Valor + mesmo Tipo + mesma Origem)
        df_contatos_long = df_contatos_long.drop_duplicates(
            subset=['CNPJ_Limpo', 'Tipo', 'Valor', 'Origem'], keep='first'
        ).reset_index(drop=True)
    
    # Metadados úteis para a UI
    df.attrs['timestamp_carga'] = hoje.strftime('%d/%m/%Y %H:%M:%S')
    df.attrs['falhas_parse_data'] = falhas_parse_data
    df.attrs['total_registros'] = len(df)
    df.attrs['contatos_long'] = df_contatos_long
        
    return df

@st.cache_data(show_spinner=False)
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

@st.cache_data(show_spinner=False)
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

@st.cache_data(show_spinner=False)
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
# 5.1. BARRA DE CONTROLES (filtro global + botão atualizar)
# ==========================================
# Filtro e botão compactos, alinhados à esquerda logo abaixo do título.
# Proporção 3 / 1 / 8: filtro compacto / botão estreito / muito espaço livre à direita,
# para que o conjunto fique próximo do título e não pareça flutuando no meio da tela.
classificacoes_disponiveis = sorted(
    [c for c in df_final['Classificacao'].dropna().unique() if c and c != 'Não Classificado']
) + (['Não Classificado'] if (df_final['Classificacao'] == 'Não Classificado').any() else [])

col_filtro, col_btn, col_espaco = st.columns([3, 1, 8])
with col_filtro:
    classificacoes_selecionadas = st.multiselect(
        "Classificação do Contrato",
        options=classificacoes_disponiveis,
        default=[],
        placeholder="Todas",
        key="filtro_classificacao_global",
        help="Filtra todos os indicadores e abas por uma ou mais classificações de contrato. Vazio = todas."
    )
with col_btn:
    st.markdown("<div style='height: 22px;'></div>", unsafe_allow_html=True)
    if st.button("🔄 Atualizar", key="btn_atualizar_topo", help="Recarrega os dados do Salesforce e os arquivos de capacidade"):
        st.cache_data.clear()
        st.rerun()

# Aplica o filtro global. Se nada estiver selecionado, considera "todas as classificações".
if classificacoes_selecionadas:
    df_final = df_final[df_final['Classificacao'].isin(classificacoes_selecionadas)].copy()

# Indicador de última atualização
ts_carga = df_final.attrs.get('timestamp_carga', 'desconhecido')
falhas_parse = df_final.attrs.get('falhas_parse_data', 0)
total_reg_original = df_final.attrs.get('total_registros', len(df_final))
total_reg_filtrado = len(df_final)
info_msg = f"🕒 Dados atualizados em <b>{ts_carga}</b> &nbsp;|&nbsp; "
if classificacoes_selecionadas:
    info_msg += f"{total_reg_filtrado:,} registros (filtrado de {total_reg_original:,}) &nbsp;|&nbsp; ".replace(",", ".")
else:
    info_msg += f"{total_reg_original:,} registros &nbsp;|&nbsp; ".replace(",", ".")
info_msg += "cache válido por 6h"
if ts_capacidade:
    info_msg += f" &nbsp;|&nbsp; 📂 Capacidade.xlsx: <b>{ts_capacidade}</b>"
if falhas_parse > 0:
    info_msg += f" &nbsp;|&nbsp; ⚠️ {falhas_parse} datas de OS não puderam ser parseadas"
if classificacoes_selecionadas:
    info_msg += f" &nbsp;|&nbsp; 🎯 Classificação: <b>{', '.join(classificacoes_selecionadas)}</b>"
st.markdown(f"<p style='color: #555; font-size: 12px;'>{info_msg}</p>", unsafe_allow_html=True)

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
aba_dashboard, aba_franquias, aba_capacidade, aba_diaria, aba_mailing, aba_m0, aba_hist, aba_desconsiderados, aba_sem_cobertura = st.tabs([
    "📊 Visão Executiva", 
    "🏢 Visão por Franquias", 
    "⚖️ Atraso vs Capacidade",
    "📅 Capacidade Diária",
    "✉️ Mailing Acionável",
    "🎯 M0",
    "📸 Fotografia Histórica",
    "🚫 Desconsiderados",
    "📍 Sem Cobertura de CEP"
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
        col1.metric("Volume da Carteira", f"{tot_cons:,}".replace(",", "."), "Geral")
        col2.metric("MP Em Dia", f"{tot_cons_em_dia:,}".replace(",", "."))
        col3.metric("Atraso Consolidado", f"{tot_cons_atraso:,}".replace(",", "."), f"{perc_cons_atraso:.1f}% da base", delta_color="inverse")
        col4.metric("Atraso", f"{tot_cons_critico:,}".replace(",", "."), "Sem Ação", delta_color="off")
        col5.metric("Prog. p/ Zerar (Mês)", f"{tot_cons_prog:,}".replace(",", "."), "OS Válidas", delta_color="normal")
        col6.metric("Agendado p/ HOJE", f"{tot_cons_hoje:,}".replace(",", "."), "Esforço diário", delta_color="normal")
        col7.metric("Projeção Pós-Baixas", f"{perc_cons_proj:.1f}%", "Estimativa Final", delta_color="normal")
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
        colA1.metric("Volume Adimplente", f"{tot_adim:,}".replace(",", "."))
        colA2.metric("MP Em Dia", f"{tot_adim_em_dia:,}".replace(",", "."))
        colA3.metric("Atraso Adimplente", f"{tot_adim_atraso:,}".replace(",", "."), f"{perc_adim_atraso:.1f}% do segmento", delta_color="inverse")
        colA4.metric("Atraso", f"{tot_adim_critico:,}".replace(",", "."), "Prioridade Alta", delta_color="off")
        colA5.metric("Prog. p/ Zerar (Mês)", f"{tot_adim_prog:,}".replace(",", "."), "OS Válidas", delta_color="normal")
        colA6.metric("Agendado p/ HOJE", f"{tot_adim_hoje:,}".replace(",", "."), "Esforço diário", delta_color="normal")
        colA7.metric("Projeção Pós-Baixas", f"{perc_adim_proj:.1f}%", "Estimativa Final", delta_color="normal")
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
        colI1.metric("Volume Inadimplente", f"{tot_inadim:,}".replace(",", "."))
        colI2.metric("MP Em Dia", f"{tot_inadim_em_dia:,}".replace(",", "."))
        colI3.metric("Atraso Inadimplente", f"{tot_inadim_atraso:,}".replace(",", "."), f"{perc_inadim_atraso:.1f}% do segmento", delta_color="inverse")
        colI4.metric("Atraso", f"{tot_inadim_critico:,}".replace(",", "."), "Sem Ação", delta_color="off")
        colI5.metric("Prog. p/ Zerar (Mês)", f"{tot_inadim_prog:,}".replace(",", "."), "OS Válidas", delta_color="normal")
        colI6.metric("Agendado p/ HOJE", f"{tot_inadim_hoje:,}".replace(",", "."), "Esforço diário", delta_color="normal")
        colI7.metric("Projeção Pós-Baixas", f"{perc_inadim_proj:.1f}%", "Estimativa Final", delta_color="normal")
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
                            col.metric(rename_faixas[faixa], f"{qtd:,}".replace(",", "."))
                        
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
            col_c1.metric("Volume Atrasado (Mapeado)", f"{tot_atr:,}".replace(",", "."))
            col_c2.metric("Capacidade Livre (MP)", f"{tot_cap:,}".replace(",", "."))
            col_c3.metric("GAP Global", f"{gap_total:,}".replace(",", "."), "Capacidade vs Atraso", delta_color="normal" if gap_total >= 0 else "inverse")
            
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
                
                # ----------------------------------------------------------
                # TELEFONES EM COLUNAS: cada contrato continua em UMA linha,
                # mas ganha colunas adicionais "Telefone 01", "Telefone 02", ...
                # com todos os telefones únicos disponíveis daquele CNPJ
                # (vindos do Cadastro + Contact + AccountContactRelation).
                # ----------------------------------------------------------
                df_contatos_long = df_final.attrs.get('contatos_long', pd.DataFrame())
                
                # Filtra apenas telefones, deduplica por CNPJ + valor (mesmo número em
                # fontes diferentes não vira duplicidade) e numera sequencialmente
                tel_por_cnpj = {}
                if df_contatos_long is not None and not df_contatos_long.empty:
                    df_tel = df_contatos_long[df_contatos_long['Tipo'] == 'Telefone'].copy()
                    if not df_tel.empty:
                        # Normaliza o telefone (só dígitos) para deduplicação, mas mantém o
                        # valor original para exibição
                        df_tel['_normalizado'] = df_tel['Valor'].astype(str).str.replace(r'\D', '', regex=True)
                        df_tel = df_tel[df_tel['_normalizado'].str.len() >= 8]  # descarta lixo curto
                        df_tel = df_tel.drop_duplicates(subset=['CNPJ_Limpo', '_normalizado'], keep='first')
                        
                        # Agrupa por CNPJ e empilha os telefones em lista
                        for cnpj, grupo in df_tel.groupby('CNPJ_Limpo'):
                            tel_por_cnpj[cnpj] = grupo['Valor'].tolist()
                
                # Quantas colunas de telefone serão criadas? (máximo entre todos os clientes do mailing)
                max_tel = 0
                for cnpj in df_mail_final['Account.CNPJ__c']:
                    max_tel = max(max_tel, len(tel_por_cnpj.get(cnpj, [])))
                
                # Cria as colunas Telefone 01, Telefone 02, ... no DataFrame de exibição
                df_mail_show = df_mail_final.copy()
                for i in range(max_tel):
                    col_nome = f"Telefone {i+1:02d}"
                    df_mail_show[col_nome] = df_mail_show['Account.CNPJ__c'].apply(
                        lambda c: tel_por_cnpj.get(c, [])[i] if i < len(tel_por_cnpj.get(c, [])) else ''
                    )
                
                # Monta o DataFrame final na ordem de colunas que o usuário pediu
                cols_finais = [
                    'FOZ_CodigoItem__c', 'Account.Name', 'Account.CNPJ__c', 'Qtd_Contratos_Cliente',
                    'Status_Financeiro', 'Data_Vencimento_MP', 'Dias_Atraso',
                    'Prestador_CEP', 'Capacidade Disponível'
                ] + [f"Telefone {i+1:02d}" for i in range(max_tel)]
                
                df_exibicao_mail = df_mail_show[cols_finais].rename(columns={
                    'FOZ_CodigoItem__c': 'Cód. Item',
                    'Account.Name': 'Cliente',
                    'Account.CNPJ__c': 'CNPJ',
                    'Qtd_Contratos_Cliente': 'Qtd Contratos',
                    'Status_Financeiro': 'Status Fin.',
                    'Data_Vencimento_MP': 'Vencimento MP',
                    'Dias_Atraso': 'Dias Atraso',
                    'Prestador_CEP': 'Grade/Franquia',
                    'Capacidade Disponível': 'Vagas na Região'
                }).sort_values(by=['Vagas na Região', 'Dias Atraso'], ascending=[False, False])
                
                # Estatísticas
                qtd_sem_tel = (df_exibicao_mail[df_exibicao_mail.columns[df_exibicao_mail.columns.str.startswith('Telefone')].tolist()].eq('').all(axis=1).sum()
                               if max_tel > 0 else len(df_exibicao_mail))
                
                st.caption(
                    f"📋 **{len(df_exibicao_mail)} contratos** no mailing — até **{max_tel} telefone(s)** "
                    f"por cliente. **{qtd_sem_tel}** contrato(s) sem nenhum telefone cadastrado."
                )
                
                st.dataframe(df_exibicao_mail, use_container_width=True, hide_index=True)
            
                st.download_button(
                    label="📥 Baixar Mailing Pronto (Excel)",
                    data=df_para_excel_bytes(df_exibicao_mail, 'Mailing_Agendamento'),
                    file_name=f"Mailing_Agendamento_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("Não há clientes em atraso nas franquias que possuem capacidade livre neste momento.")

# === ABA 6: M0 (CONTRATOS COM MP VENCENDO NO MÊS+1) ===
with aba_m0:
    st.markdown("### 🎯 M0 — Contratos com MP vencendo no próximo mês")
    st.markdown(
        "Lista todos os contratos da base ativa cuja **próxima MP vence no próximo mês civil** "
        "em relação à data de hoje. **Visão crua**, sem a regra de 'atraso = vencimento + 1 mês' "
        "aplicada nas outras abas. Use essa aba para se antecipar e atuar antes que esses contratos "
        "entrem em atraso."
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
    
    # Filtra contratos da base ativa cujo FOZ_DataProximaMP__c cai no mês-alvo.
    # IMPORTANTE: aqui usamos a base completa (df_final) e NÃO df_ativos_reais,
    # porque queremos a visão crua, incluindo contratos com OS de desinstalação se houver.
    df_m0 = df_final[
        (df_final['FOZ_DataProximaMP__c'].dt.month == mes_alvo) &
        (df_final['FOZ_DataProximaMP__c'].dt.year == ano_alvo)
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
            col1.metric("Contratos no M0", f"{total_m0:,}".replace(",", "."), "Vencendo no mês")
            col2.metric("Clientes únicos", f"{clientes_unicos:,}".replace(",", "."))
            col3.metric("Adimplentes", f"{adim_m0:,}".replace(",", "."))
            col4.metric("Inadimplentes", f"{inadim_m0:,}".replace(",", "."))
            col5.metric("Com OS aberta", f"{com_os_m0:,}".replace(",", "."), "Já em ação", delta_color="normal")
            col6.metric("Sem OS aberta", f"{sem_os_m0:,}".replace(",", "."), "Pendente", delta_color="off")
        
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
                'FOZ_CodigoItem__c', 'Account.Name', 'Account.CNPJ__c', 'Qtd_Contratos_Cliente',
                'Vencimento MP', 'FOZ_EndFranquiaForm__c', 'Status_Financeiro',
                'Tem_OS_Aberta', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento'
            ]].rename(columns={
                'FOZ_CodigoItem__c': 'Cód. Item',
                'Account.Name': 'Cliente',
                'Account.CNPJ__c': 'CNPJ',
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

# === ABA 6: HISTÓRICO (SNAPSHOT) ===
with aba_hist:
    st.markdown("### 📸 Fotografia Histórica (Evolução do Backlog)")
    st.markdown("Acompanhe a curva de evolução dos atrasos salvando um 'retrato' da operação atual.")
    
    tot_atrasos_geral = len(df_ativos_reais[df_ativos_reais['Atraso_Base'] == AtrasoBase.ATRASADO])
    tot_criticos_geral = len(df_ativos_reais[df_ativos_reais['Status_MP_Real'] == StatusMP.CRITICO])
    
    registro_hoje = pd.DataFrame([{
        'Data Snapshot': datetime.now(FUSO_BR).strftime('%d/%m/%Y %H:%M'),
        'Volume Base Total': len(df_ativos_reais),
        'Atraso Consolidado': tot_atrasos_geral,
        'Atraso Crítico (Sem Ação)': tot_criticos_geral,
        'Programado (Mês)': len(df_ativos_reais[df_ativos_reais['Status_MP_Real'] == StatusMP.PROGRAMADO])
    }])
    
    col_hist1, col_hist2 = st.columns([1, 4])
    with col_hist1:
        if st.button("Salvar Retrato de Hoje", type="primary"):
            try:
                if os.path.exists(ARQUIVO_HISTORICO):
                    df_hist = pd.read_csv(ARQUIVO_HISTORICO)
                    df_hist = pd.concat([df_hist, registro_hoje], ignore_index=True)
                else:
                    df_hist = registro_hoje
                df_hist.to_csv(ARQUIVO_HISTORICO, index=False)
                st.success("Snapshot salvo com sucesso!")
            except Exception as e:
                st.error(f"Erro ao salvar snapshot: {e}")
            
    with col_hist2:
        if os.path.exists(ARQUIVO_HISTORICO):
            try:
                df_hist_plot = pd.read_csv(ARQUIVO_HISTORICO)
                df_hist_plot['Data_Parse'] = pd.to_datetime(df_hist_plot['Data Snapshot'], format='%d/%m/%Y %H:%M')
                df_hist_plot = df_hist_plot.sort_values('Data_Parse')
                
                # Renomeia visualmente para o gráfico (a coluna interna mantém o nome antigo
                # para preservar compatibilidade com CSVs já salvos antes da renomeação).
                df_plot = df_hist_plot.rename(columns={'Atraso Crítico (Sem Ação)': 'Atraso (Sem Ação)'})
                
                fig_linha = px.line(
                    df_plot, x='Data Snapshot', y=['Atraso Consolidado', 'Atraso (Sem Ação)'], 
                    markers=True, title="Curva de Redução de Atrasos",
                    color_discrete_map={'Atraso Consolidado': '#1f77b4', 'Atraso (Sem Ação)': '#d62728'}
                )
                fig_linha.update_layout(yaxis_title="Volume de Máquinas", xaxis_title="Data do Retrato")
                st.plotly_chart(fig_linha, use_container_width=True)
                
                with st.expander("Ver Base Histórica Completa"):
                    st.dataframe(df_hist_plot.drop(columns=['Data_Parse']), hide_index=True)
                    st.download_button(
                        label="📥 Baixar histórico (Excel)",
                        data=df_para_excel_bytes(df_hist_plot.drop(columns=['Data_Parse']), 'Historico'),
                        file_name=f"historico_backlog_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.ms-excel",
                        key="dl_historico"
                    )
            except Exception as e:
                st.error(f"Erro ao ler histórico: {e}")
        else:
            st.info("Nenhum histórico salvo ainda. Clique no botão ao lado para criar o primeiro registro.")

# === ABA 7: DESCONSIDERADOS ===
with aba_desconsiderados:
    st.markdown("### 🚫 Contratos Desconsiderados")
    st.markdown("Máquinas que teriam MP vencida, mas possuem OS de **Desinstalação** aberta.")
    df_isentos = df_final[df_final['Atraso_Base'] == AtrasoBase.ISENTO].copy()
    with st.container(border=True):
        st.markdown("#### 🚫 Máquinas em Desinstalação")
        col_kpi1, _ = st.columns([1, 6])
        col_kpi1.metric("Máquinas Desconsideradas", len(df_isentos))
    
    if len(df_isentos) > 0:
        df_isentos['Data_Vencimento_MP'] = df_isentos['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
        df_exibicao_isentos = df_isentos[[
            'FOZ_CodigoItem__c', 'Account.Name', 'SerialNumber', 'Status_MP_Real', 
            'Data_Vencimento_MP', 'Numero_Caso', 'Tipo_Servico', 'Data_Agendamento'
        ]].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente', 'SerialNumber': 'Nº Série',
            'Status_MP_Real': 'Motivo', 'Data_Vencimento_MP': 'Vencimento Original',
            'Numero_Caso': 'Nº OS', 'Tipo_Servico': 'Serviço', 'Data_Agendamento': 'Data OS'
        }).fillna({'Data OS': '-'})
        st.dataframe(df_exibicao_isentos, use_container_width=True, hide_index=True)
        
        st.download_button(
            label="📥 Baixar desconsiderados (Excel)",
            data=df_para_excel_bytes(df_exibicao_isentos, 'Desconsiderados'),
            file_name=f"desconsiderados_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.ms-excel",
            key="dl_desconsiderados"
        )

# === ABA 8: SEM COBERTURA DE CEP ===
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
                col1.metric("Total", f"{total_sc:,}".replace(",", "."), "Sem cobertura")
                col2.metric("MP Em Dia", f"{em_dia_sc:,}".replace(",", "."))
                col3.metric("Em Atraso", f"{atrasados_sc:,}".replace(",", "."), 
                           f"{(atrasados_sc/total_sc*100):.1f}% do segmento", delta_color="inverse")
                col4.metric("Atraso", f"{criticos_sc:,}".replace(",", "."), 
                           "Sem capacidade definida", delta_color="off")
                col5.metric("Adimplentes", f"{adim_sc:,}".replace(",", "."))
                col6.metric("Inadimplentes", f"{inadim_sc:,}".replace(",", "."))
            
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