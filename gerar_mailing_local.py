# -*- coding: utf-8 -*-
"""
============================================================
GERADOR LOCAL DE MAILING ACIONÁVEL (com telefones)
============================================================
Por questões de LGPD, os telefones dos clientes NÃO ficam no
painel online (Streamlit Cloud). Este script roda LOCALMENTE
na sua máquina, replica a mesma lógica do painel e gera o
Excel completo do mailing — com telefones — para compartilhar
com o time que precisa.

COMO USAR:
  1. Coloque este arquivo na mesma pasta dos arquivos:
       - Range CEP.xlsx
       - De-Para.xlsx
       - Capacidade.xlsx
  2. Configure as credenciais abaixo (ou use variáveis de ambiente)
  3. Rode:  python gerar_mailing_local.py
  4. Escolha a carteira quando perguntado
  5. O Excel é salvo na mesma pasta

REQUISITOS:  pip install pandas simple-salesforce openpyxl xlsxwriter
============================================================
"""

import os
import re
import sys
import unicodedata
from datetime import datetime
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd
from simple_salesforce import Salesforce

# ============================================================
# CREDENCIAIS — preencha aqui OU defina variáveis de ambiente
# SF_USERNAME / SF_PASSWORD / SF_TOKEN
# ============================================================
PASTA = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env_path = os.path.join(PASTA, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip("'\"")

load_env()

SF_USERNAME = os.environ.get('SF_USER', os.environ.get('SF_USERNAME', 'ext-potavio@culligan.com'))
SF_PASSWORD = os.environ.get('SF_PWD', os.environ.get('SF_PASSWORD', ''))
SF_TOKEN    = os.environ.get('SF_TOKEN', '')

ARQ_RANGE_CEP  = os.path.join(PASTA, 'Range CEP.xlsx')
ARQ_DEPARA     = os.path.join(PASTA, 'De-Para.xlsx')
ARQ_CAPACIDADE = os.path.join(PASTA, 'Capacidade.xlsx')


def normalizar_texto(s):
    """Remove acentos e converte para maiúsculas para comparações robustas."""
    if pd.isna(s):
        return ''
    s = str(s)
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return s.upper().strip()


def main():
    print("=" * 60)
    print("GERADOR LOCAL DE MAILING ACIONÁVEL (com telefones)")
    print("=" * 60)

    # ---------------- 1. Escolha da carteira ----------------
    print("\nQual mailing você quer gerar?")
    print("  1 - Base Total (todos)")
    print("  2 - Apenas Adimplentes")
    print("  3 - Apenas Inadimplentes")
    escolha = input("Digite 1, 2 ou 3: ").strip()
    mapa_carteira = {'1': 'Base Total', '2': 'Adimplente', '3': 'Inadimplente'}
    if escolha not in mapa_carteira:
        print("Opção inválida. Saindo.")
        sys.exit(1)
    carteira = mapa_carteira[escolha]
    print(f"\n→ Carteira selecionada: {carteira}")

    # ---------------- 2. Validação de credenciais e arquivos ----------------
    senha = SF_PASSWORD
    token = SF_TOKEN
    if not senha or not token:
        print("❌ Credenciais do Salesforce não encontradas. Verifique o arquivo .env.")
        sys.exit(1)

    for arq in [ARQ_RANGE_CEP, ARQ_DEPARA, ARQ_CAPACIDADE]:
        if not os.path.exists(arq):
            print(f"❌ Arquivo obrigatório não encontrado: {arq}")
            print("   Coloque este script na mesma pasta dos arquivos Excel do painel.")
            sys.exit(1)

    # ---------------- 3. Conexão e queries ----------------
    print("\nConectando ao Salesforce...")
    sf = Salesforce(username=SF_USERNAME, password=senha, security_token=token)
    print("Conexão OK. Baixando dados (pode levar alguns minutos)...")

    query_ativos = """
    SELECT 
        FOZ_CodigoItem__c, Status, FOZ_DataProximaMP__c,
        AccountId, Account.Name, Account.FOZ_StatusPosicaoFinanceira__c, 
        Account.CNPJ__c, Account.FOZ_Classificacao__c,
        Account.PersonMobilePhone, Account.PersonHomePhone,
        FOZ_EndFranquiaForm__c, FOZ_EnderecoEntrega__r.FOZ_CEP__c
    FROM Asset
    WHERE Status = 'Ativo-Em Operação'
    """
    query_os = """
    SELECT Case.FOZ_Asset__r.FOZ_CodigoItem__c, Case.CaseNumber, Case.Status,
           FOZ_Agendado_Data_Periodo__c, FOZ_Tipo_de_Servico__c
    FROM WorkOrder
    WHERE Case.Type = 'OS' AND Case.Status != 'Cancelado' AND Case.Status != 'Fechado'
      AND Status != 'Cancelado' AND Status != 'Fechado'
    """
    query_contatos = """
    SELECT Account.CNPJ__c, Account.FOZ_CNPJ__c, MobilePhone, Phone
    FROM Contact 
    WHERE (Account.CNPJ__c != null OR Account.FOZ_CNPJ__c != null)
      AND (MobilePhone != null OR Phone != null)
    """
    query_acr = """
    SELECT Account.CNPJ__c, Account.FOZ_CNPJ__c, Contact.MobilePhone, Contact.Phone
    FROM AccountContactRelation
    WHERE (Account.CNPJ__c != null OR Account.FOZ_CNPJ__c != null)
      AND (Contact.MobilePhone != null OR Contact.Phone != null)
    """

    registros_ativos   = sf.query_all(query_ativos).get('records', [])
    print(f"  Ativos: {len(registros_ativos)}")
    registros_os       = sf.query_all(query_os).get('records', [])
    print(f"  OS abertas: {len(registros_os)}")
    registros_contatos = sf.query_all(query_contatos).get('records', [])
    print(f"  Contatos: {len(registros_contatos)}")
    registros_acr      = sf.query_all(query_acr).get('records', [])
    print(f"  Relacionamentos (ACR): {len(registros_acr)}")

    # ---------------- 4. Base de ativos ----------------
    df = pd.json_normalize(registros_ativos)
    df = df[[c for c in df.columns if 'attributes' not in c]]
    df['FOZ_DataProximaMP__c'] = pd.to_datetime(df['FOZ_DataProximaMP__c'], errors='coerce')

    # ---------------- 5. OS abertas (Tem_OS_Aberta + isenção por desinstalação) ----------------
    df_os = pd.json_normalize(registros_os)
    if not df_os.empty:
        df_os = df_os.rename(columns={
            'Case.FOZ_Asset__r.FOZ_CodigoItem__c': 'CodigoItem',
            'FOZ_Tipo_de_Servico__c': 'Tipo_Servico',
            'Case.CaseNumber': 'Numero_Caso'
        })
        df_os = df_os[['CodigoItem', 'Tipo_Servico', 'Numero_Caso']].dropna(subset=['CodigoItem'])
        df_os['CodigoItem'] = df_os['CodigoItem'].astype(str)
        # Agrupa por contrato: tem OS aberta; algum tipo contém DESINSTALA?
        df_os['_desinst'] = df_os['Tipo_Servico'].astype(str).apply(
            lambda t: 'DESINSTALA' in normalizar_texto(t)
        )
        agg = df_os.groupby('CodigoItem').agg(
            Tem_OS_Aberta=('CodigoItem', 'size'),
            Tem_Desinstalacao=('_desinst', 'any'),
            Numero_Caso=('Numero_Caso', 'first'),
            Tipo_Servico=('Tipo_Servico', 'first')
        ).reset_index()
        agg['Tem_OS_Aberta'] = True
    else:
        agg = pd.DataFrame(columns=['CodigoItem', 'Tem_OS_Aberta', 'Tem_Desinstalacao', 'Numero_Caso', 'Tipo_Servico'])

    df['_cod'] = df['FOZ_CodigoItem__c'].astype(str)
    df = df.merge(agg, left_on='_cod', right_on='CodigoItem', how='left')
    df['Tem_OS_Aberta'] = df['Tem_OS_Aberta'].fillna(False).astype(bool)
    df['Tem_Desinstalacao'] = df['Tem_Desinstalacao'].fillna(False).astype(bool)

    # ---------------- 5.1. Qtd Contratos por Cliente ----------------
    qtd_contratos_por_cnpj = df.groupby('Account.CNPJ__c')['FOZ_CodigoItem__c'].count()
    df['Qtd_Contratos_Cliente'] = df['Account.CNPJ__c'].map(qtd_contratos_por_cnpj).fillna(1).astype(int)

    # ---------------- 6. Regra de atraso (mesma do painel) ----------------
    hoje = pd.Timestamp(datetime.now().date())
    limite_carencia = hoje - relativedelta(months=1)
    df['Atrasado'] = df['FOZ_DataProximaMP__c'] < limite_carencia
    df['Dias_Atraso'] = (hoje - df['FOZ_DataProximaMP__c']).dt.days

    # O "Em Dia" não deve excluir quem tem OS Aberta (só exclui Desinstalação)
    df_sem_desinst = df[~df['Tem_Desinstalacao']].copy()

    # ---------------- 7. Filtro de carteira ----------------
    status_norm = df_sem_desinst['Account.FOZ_StatusPosicaoFinanceira__c'].apply(normalizar_texto)
    if carteira == 'Adimplente':
        df_sem_desinst = df_sem_desinst[status_norm.str.contains('INADIMPLENTE') == False].copy()
    elif carteira == 'Inadimplente':
        df_sem_desinst = df_sem_desinst[status_norm.str.contains('INADIMPLENTE')].copy()

    # Mailing Acionável EXCLUI quem tem OS aberta
    base = df_sem_desinst[df_sem_desinst['Atrasado'] & ~df_sem_desinst['Tem_OS_Aberta']].copy()
    
    # Com OS Aberta (Não podem ser acionados)
    com_os_aberta = df_sem_desinst[df_sem_desinst['Atrasado'] & df_sem_desinst['Tem_OS_Aberta']].copy()
    
    # Em Dia inclui todos que não estão atrasados
    mp_em_dia = df_sem_desinst[~df_sem_desinst['Atrasado']].copy()

    print(f"\nTotal filtrado (sem desinstalação, filtro carteira {carteira}): {len(df_sem_desinst)}")
    print(f" -> Atrasados APTOS (Mailing Acionável / Sem Capacidade): {len(base)}")
    print(f" -> Atrasados com OS Aberta: {len(com_os_aberta)}")
    print(f" -> Em Dia (total): {len(mp_em_dia)}")

    if base.empty and mp_em_dia.empty:
        print("Nenhum contrato elegível para esta carteira. Nada a gerar.")
        sys.exit(0)

    # ---------------- 8. Mapeamento CEP → Prestador (Range CEP + De-Para) ----------------
    print("Mapeando CEPs para prestadores...")
    df_range = pd.read_excel(ARQ_RANGE_CEP)
    df_depara = pd.read_excel(ARQ_DEPARA)

    def cep_num(c):
        if pd.isna(c):
            return np.nan
        nums = re.sub(r'\D', '', str(c))
        return int(nums) if nums else np.nan

    df_range['_de']  = df_range['Cep "De"'].apply(cep_num)
    df_range['_ate'] = df_range['Cep "Até"'].apply(cep_num)
    
    # Se a coluna 'Nome Service Area' não existir, tenta outro nome caso a planilha mude
    col_nome_sa = 'Nome Service Area' if 'Nome Service Area' in df_range.columns else df_range.columns[0]
    col_grade = 'GRADE' if 'GRADE' in df_range.columns else df_range.columns[3]
    
    ranges = df_range[['_de', '_ate', col_nome_sa, col_grade]].dropna().values.tolist()

    df_depara['Grade_Match'] = df_depara['Franquia Relatório Capacidade'].str.extract(r'(R\d{2})')
    dict_depara = {}
    for _, row in df_depara.iterrows():
        chave = (str(row['Franquia Range CEP']).strip(), str(row['Grade_Match']).strip())
        dict_depara[chave] = str(row['Franquia Relatório Capacidade']).strip()

    def prestador_do_cep(cep):
        n = cep_num(cep)
        if pd.isna(n):
            return None
        for de, ate, franquia, grade in ranges:
            if de <= n <= ate:
                return dict_depara.get((str(franquia).strip(), str(grade).strip()))
        return None

    ceps_unicos = df_sem_desinst['FOZ_EnderecoEntrega__r.FOZ_CEP__c'].dropna().unique()
    mapa_cep = {cep: prestador_do_cep(cep) for cep in ceps_unicos}
    base['Prestador_CEP'] = base['FOZ_EnderecoEntrega__r.FOZ_CEP__c'].map(mapa_cep)
    com_os_aberta['Prestador_CEP'] = com_os_aberta['FOZ_EnderecoEntrega__r.FOZ_CEP__c'].map(mapa_cep)
    mp_em_dia['Prestador_CEP'] = mp_em_dia['FOZ_EnderecoEntrega__r.FOZ_CEP__c'].map(mapa_cep)

    # ---------------- 9. Capacidade e corte ----------------
    print("Aplicando corte por capacidade...")
    df_cap = pd.read_excel(ARQ_CAPACIDADE)
    df_cap.columns = df_cap.columns.str.strip()
    
    if 'Data do Registro' in df_cap.columns and 'Disponível' in df_cap.columns:
        df_cap['Data do Registro'] = pd.to_datetime(df_cap['Data do Registro'], format='%d/%m/%Y', errors='coerce')
        hoje_limpo = pd.to_datetime(datetime.now().date())
        df_cap_futuro = df_cap[df_cap['Data do Registro'] >= hoje_limpo].copy()
        if 'Serviços' in df_cap.columns:
            df_cap_mp = df_cap_futuro[df_cap_futuro['Serviços'].astype(str).str.contains('MP', case=False, na=False)].copy()
        else:
            df_cap_mp = df_cap_futuro.copy()
            
        df_cap_mp['Disponível'] = pd.to_numeric(df_cap_mp['Disponível'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0).astype(int)
        
        def _normalizar(texto):
            if pd.isna(texto): return ''
            s = str(texto).strip().upper()
            return s.translate(str.maketrans('ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'AAAAAEEEEIIIIOOOOOUUUUC'))
            
        if 'Dia' in df_cap_mp.columns: df_cap_mp['_Dia_Norm'] = df_cap_mp['Dia'].apply(_normalizar)
        else: df_cap_mp['_Dia_Norm'] = ''
        df_cap_mp['_DiaSemana_Num'] = df_cap_mp['Data do Registro'].dt.dayofweek
        if 'Janela de atendimento' in df_cap_mp.columns: df_cap_mp['_Janela_Norm'] = df_cap_mp['Janela de atendimento'].apply(_normalizar)
        else: df_cap_mp['_Janela_Norm'] = ''
        
        eh_domingo = (df_cap_mp['_Dia_Norm'] == 'DOMINGO') | (df_cap_mp['_DiaSemana_Num'] == 6)
        eh_sabado = (df_cap_mp['_Dia_Norm'] == 'SABADO') | (df_cap_mp['_DiaSemana_Num'] == 5)
        eh_tarde = df_cap_mp['_Janela_Norm'].str.contains('TARDE', na=False)
        df_cap_mp.loc[eh_domingo | (eh_sabado & eh_tarde), 'Disponível'] = 0
        
        col_prest_cap = 'Prestador de Serviço' if 'Prestador de Serviço' in df_cap_mp.columns else df_cap_mp.columns[0]
        capacidade = df_cap_mp.groupby(df_cap_mp[col_prest_cap].astype(str).str.strip())['Disponível'] \
                           .sum().rename('Capacidade').reset_index() \
                           .rename(columns={col_prest_cap: 'Prestador'})
    else:
        col_prest_cap = df_cap.columns[0]
        cols_vagas = df_cap.select_dtypes(include=[np.number]).columns
        df_cap['_total'] = df_cap[cols_vagas].sum(axis=1)
        capacidade = df_cap.groupby(df_cap[col_prest_cap].astype(str).str.strip())['_total'] \
                           .sum().rename('Capacidade').reset_index() \
                           .rename(columns={col_prest_cap: 'Prestador'})

    base['_prest'] = base['Prestador_CEP'].astype(str).str.strip()
    base = base.merge(capacidade, left_on='_prest', right_on='Prestador', how='left')
    base['Capacidade'] = base['Capacidade'].fillna(0).astype(int)

    com_vaga = base[base['Capacidade'] > 0].copy()
    com_vaga = com_vaga.sort_values(
        by=['_prest', 'Dias_Atraso', 'FOZ_CodigoItem__c'],
        ascending=[True, False, True]
    )
    com_vaga['_rank'] = com_vaga.groupby('_prest').cumcount()
    mailing = com_vaga[com_vaga['_rank'] < com_vaga['Capacidade']].drop(columns=['_rank']).copy()
    excedente = com_vaga[com_vaga['_rank'] >= com_vaga['Capacidade']].drop(columns=['_rank']).copy()
    excedente['Motivo'] = 'Excedente de capacidade'
    sem_vagas = base[base['Capacidade'] == 0].copy()
    sem_vagas['Motivo'] = 'Franquia sem vagas'
    nao_acionados = pd.concat([excedente, sem_vagas], ignore_index=True)
    print(f"Mailing (cabem na capacidade): {len(mailing)} | Não acionados: {len(nao_acionados)}")

    # ---------------- 10. Telefones (Account + Contact + ACR), dedup por dígitos ----------------
    print("Montando telefones por CNPJ...")
    frames = []

    def so_digitos(v):
        return re.sub(r'\D', '', str(v)) if pd.notna(v) else ''

    # Fonte 1: Account (da própria base de ativos)
    for col_tel in ['Account.PersonMobilePhone', 'Account.PersonHomePhone']:
        if col_tel in df.columns:
            s = df[['Account.CNPJ__c', col_tel]].dropna()
            s.columns = ['CNPJ', 'Tel']
            frames.append(s)

    # Fonte 2: Contact
    df_ct = pd.json_normalize(registros_contatos)
    if not df_ct.empty:
        df_ct['CNPJ'] = df_ct['Account.CNPJ__c'].fillna(df_ct.get('Account.FOZ_CNPJ__c'))
        for col_tel in ['MobilePhone', 'Phone']:
            if col_tel in df_ct.columns:
                s = df_ct[['CNPJ', col_tel]].dropna()
                s.columns = ['CNPJ', 'Tel']
                frames.append(s)

    # Fonte 3: ACR
    df_acr = pd.json_normalize(registros_acr)
    if not df_acr.empty:
        df_acr['CNPJ'] = df_acr['Account.CNPJ__c'].fillna(df_acr.get('Account.FOZ_CNPJ__c'))
        for col_tel in ['Contact.MobilePhone', 'Contact.Phone']:
            if col_tel in df_acr.columns:
                s = df_acr[['CNPJ', col_tel]].dropna()
                s.columns = ['CNPJ', 'Tel']
                frames.append(s)

    if frames:
        tels = pd.concat(frames, ignore_index=True)
        tels['CNPJ'] = tels['CNPJ'].astype(str).str.replace(r'\D', '', regex=True)
        tels['_norm'] = tels['Tel'].apply(so_digitos)
        tels = tels[tels['_norm'].str.len() >= 8]
        tels = tels.drop_duplicates(subset=['CNPJ', '_norm'], keep='first')
        tel_por_cnpj = tels.groupby('CNPJ')['Tel'].apply(list).to_dict()
    else:
        tel_por_cnpj = {}

    def montar_telefones(df_alvo):
        cnpjs_limpos = df_alvo['Account.CNPJ__c'].astype(str).str.replace(r'\D', '', regex=True)
        listas = cnpjs_limpos.map(lambda c: tel_por_cnpj.get(c, []))
        max_tel = listas.str.len().max() if len(listas) else 0
        max_tel = int(max_tel) if pd.notna(max_tel) else 0
        for i in range(max_tel):
            df_alvo[f'Telefone {i+1:02d}'] = listas.map(
                lambda l: l[i] if i < len(l) else ''
            )
        return df_alvo, max_tel

    mailing, n_tel_m = montar_telefones(mailing)
    if not nao_acionados.empty:
        nao_acionados, _ = montar_telefones(nao_acionados)
    if not com_os_aberta.empty:
        com_os_aberta, _ = montar_telefones(com_os_aberta)
    if not mp_em_dia.empty:
        mp_em_dia, _ = montar_telefones(mp_em_dia)

    # ---------------- 11. Excel final ----------------
    def preparar(df_alvo, com_motivo=False):
        df_alvo = df_alvo.copy()
        if not df_alvo.empty:
            df_alvo['Vencimento MP'] = df_alvo['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
        else:
            df_alvo['Vencimento MP'] = ''
        cols = (['Motivo'] if com_motivo else []) + [
            'FOZ_CodigoItem__c', 'Account.Name', 'Account.CNPJ__c', 'Qtd_Contratos_Cliente',
            'Account.FOZ_Classificacao__c', 'Account.FOZ_StatusPosicaoFinanceira__c',
            'Vencimento MP', 'Dias_Atraso', 'Prestador_CEP', 'Capacidade'
        ] + [c for c in df_alvo.columns if c.startswith('Telefone ')]
        cols = [c for c in cols if c in df_alvo.columns]
        return df_alvo[cols].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente',
            'Account.CNPJ__c': 'CNPJ', 'Qtd_Contratos_Cliente': 'Qtd Itens Cliente',
            'Account.FOZ_Classificacao__c': 'Classificação',
            'Account.FOZ_StatusPosicaoFinanceira__c': 'Status Financeiro',
            'Dias_Atraso': 'Dias Atraso', 'Prestador_CEP': 'Grade/Franquia',
            'Capacidade': 'Vagas na Região'
        })
        
    def preparar_os_aberta(df_alvo):
        df_alvo = df_alvo.copy()
        if not df_alvo.empty:
            df_alvo['Vencimento MP'] = df_alvo['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
        else:
            df_alvo['Vencimento MP'] = ''
        cols = [
            'FOZ_CodigoItem__c', 'Account.Name', 'Account.CNPJ__c', 'Qtd_Contratos_Cliente',
            'Account.FOZ_Classificacao__c', 'Account.FOZ_StatusPosicaoFinanceira__c',
            'Numero_Caso', 'Tipo_Servico',
            'Vencimento MP', 'Dias_Atraso', 'Prestador_CEP'
        ] + [c for c in df_alvo.columns if c.startswith('Telefone ')]
        cols = [c for c in cols if c in df_alvo.columns]
        return df_alvo[cols].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente',
            'Account.CNPJ__c': 'CNPJ', 'Qtd_Contratos_Cliente': 'Qtd Itens Cliente',
            'Account.FOZ_Classificacao__c': 'Classificação',
            'Account.FOZ_StatusPosicaoFinanceira__c': 'Status Financeiro',
            'Numero_Caso': 'Nº OS', 'Tipo_Servico': 'Tipo Serviço',
            'Dias_Atraso': 'Dias Atraso', 'Prestador_CEP': 'Grade/Franquia'
        })

    def preparar_em_dia(df_alvo):
        df_alvo = df_alvo.copy()
        if not df_alvo.empty:
            df_alvo['Vencimento MP Sistema'] = df_alvo['FOZ_DataProximaMP__c'].dt.strftime('%d/%m/%Y')
            df_alvo['Vencimento MP Regra Acionamento'] = (df_alvo['FOZ_DataProximaMP__c'] + pd.DateOffset(months=1)).dt.strftime('%d/%m/%Y')
        else:
            df_alvo['Vencimento MP Sistema'] = ''
            df_alvo['Vencimento MP Regra Acionamento'] = ''
            
        cols = [
            'FOZ_CodigoItem__c', 'Account.Name', 'Account.CNPJ__c', 'Qtd_Contratos_Cliente',
            'Account.FOZ_Classificacao__c', 'Account.FOZ_StatusPosicaoFinanceira__c',
            'Vencimento MP Sistema', 'Vencimento MP Regra Acionamento', 'Prestador_CEP'
        ] + [c for c in df_alvo.columns if c.startswith('Telefone ')]
        cols = [c for c in cols if c in df_alvo.columns]
        return df_alvo[cols].rename(columns={
            'FOZ_CodigoItem__c': 'Cód. Item', 'Account.Name': 'Cliente',
            'Account.CNPJ__c': 'CNPJ', 'Qtd_Contratos_Cliente': 'Qtd Itens Cliente',
            'Account.FOZ_Classificacao__c': 'Classificação',
            'Account.FOZ_StatusPosicaoFinanceira__c': 'Status Financeiro',
            'Prestador_CEP': 'Grade/Franquia'
        })

    sufixo = carteira.replace(' ', '_')
    nome_arquivo = os.path.join(
        PASTA, f"Mailing_{sufixo}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    )
    with pd.ExcelWriter(nome_arquivo, engine='xlsxwriter') as writer:
        preparar(mailing).to_excel(writer, index=False, sheet_name='Mailing_Acionavel')
        preparar_os_aberta(com_os_aberta).to_excel(writer, index=False, sheet_name='Com_OS_Aberta')
        preparar(nao_acionados, com_motivo=True).to_excel(writer, index=False, sheet_name='Sem_Capacidade')
        preparar_em_dia(mp_em_dia).to_excel(writer, index=False, sheet_name='MP_EmDia')

    print("\n" + "=" * 60)
    print(f"✅ Arquivo gerado: {nome_arquivo}")
    print(f"   Aba 'Mailing_Acionavel': {len(mailing)} contratos (até {n_tel_m} telefones por cliente)")
    print(f"   Aba 'Com_OS_Aberta': {len(com_os_aberta)} contratos")
    print(f"   Aba 'Sem_Capacidade': {len(nao_acionados)} contratos")
    print(f"   Aba 'MP_EmDia': {len(mp_em_dia)} contratos")
    print("=" * 60)
    print("\n⚠️  LEMBRETE LGPD: este arquivo contém dados pessoais (telefones).")
    print("   Compartilhe apenas com quem precisa e não suba para repositórios públicos.")


if __name__ == '__main__':
    main()
