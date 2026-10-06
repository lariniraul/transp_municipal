"""Execute: python -m streamlit run app.py"""
from decimal import Decimal
import math

import pandas as pd
import streamlit as st

from api import consultar_mes, meses_periodo, municipios, moeda, valor_decimal

st.set_page_config(page_title="Consulta Municipal • SP", page_icon="🏛️", layout="wide")
st.title("Consulta Municipal • SP")
st.caption("Receitas e despesas dos municípios jurisdicionados ao TCE-SP. Valores e registros conforme publicados na fonte.")


@st.cache_data(ttl=86400, show_spinner="Carregando municípios…")
def carregar_municipios():
    return municipios()


NOMES = {
    "competencia_consulta": "Competência", "orgao": "Órgão", "mes": "Mês",
    "ds_fonte_recurso": "Fonte do recurso", "ds_cd_aplicacao_fixo": "Aplicação",
    "ds_alinea": "Alínea", "ds_subalinea": "Descrição da receita",
    "vl_arrecadacao": "Arrecadação (R$)", "evento": "Movimentação",
    "nr_empenho": "Empenho", "id_fornecedor": "CPF/CNPJ do fornecedor",
    "nm_fornecedor": "Fornecedor", "dt_emissao_despesa": "Data da despesa",
    "vl_despesa": "Valor (R$)",
}

with st.sidebar:
    st.header("Nova consulta")
    tipo = st.radio("Menu", ["Receitas", "Despesas"])
    try:
        lista = carregar_municipios()
        opcoes = {r["municipio"]: r["municipio_extenso"] for r in lista}
    except ValueError as erro:
        st.warning(f"{erro} Você pode informar o identificador manualmente.")
        opcoes = None

    with st.form("consulta"):
        if opcoes:
            chaves = list(opcoes)
            cidade = st.selectbox("Cidade / SP", chaves,
                index=chaves.index("cosmopolis") if "cosmopolis" in chaves else 0,
                format_func=lambda chave: opcoes[chave])
            nome_cidade = opcoes[cidade]
        else:
            cidade = st.text_input("Identificador do município", "cosmopolis").strip().lower()
            nome_cidade = cidade
            st.caption("Use o identificador da API, como cosmopolis ou ribeirao-preto.")
        inicio = st.text_input("Mês inicial (MM/AAAA)", "01/2026")
        fim = st.text_input("Mês final (MM/AAAA)", "01/2026")
        executar = st.form_submit_button("Consultar", type="primary", use_container_width=True)
    st.caption("O intervalo inclui os meses inicial e final. A consulta inicial inclui todas as fontes e órgãos retornados.")
    st.markdown("[Documentação e fonte dos dados](https://transparencia.tce.sp.gov.br/apis)")

if executar:
    try:
        meses = meses_periodo(inicio, fim)
        if not cidade:
            raise ValueError("Informe o município.")
    except ValueError as erro:
        st.error(str(erro))
        st.stop()
    registros, situacoes = [], []
    progresso = st.progress(0, text="Iniciando consulta…")
    for indice, (ano, mes) in enumerate(meses):
        referencia = f"{mes:02d}/{ano}"
        try:
            lote = consultar_mes(tipo.lower(), cidade, ano, mes)
            registros.extend(lote)
            situacoes.append({"Mês": referencia, "Situação": "Retornado" if lote else "Sem registros", "Registros": len(lote), "Detalhe": ""})
        except ValueError as erro:
            situacoes.append({"Mês": referencia, "Situação": "Falha", "Registros": 0, "Detalhe": str(erro)})
        progresso.progress((indice + 1) / len(meses), text=f"Consultado: {referencia}")
    progresso.empty()
    st.session_state.resultado = dict(registros=registros, situacoes=situacoes,
        tipo=tipo, cidade=nome_cidade, inicio=inicio, fim=fim)
    st.session_state.consulta_id = st.session_state.get("consulta_id", 0) + 1

resultado = st.session_state.get("resultado")
if not resultado:
    st.info("Escolha a consulta no menu e clique em Consultar. Os resultados serão exibidos aqui.")
    st.stop()

# O cabeçalho identifica os filtros efetivamente consultados, mesmo após editar o menu.
st.subheader(f"{resultado['tipo']} · {resultado['cidade']} / SP")
st.caption(f"Período consultado: {resultado['inicio']} a {resultado['fim']}")
problemas = [r for r in resultado["situacoes"] if r["Situação"] != "Retornado"]
if problemas:
    st.warning("Há meses com falha ou sem registros. Os resultados podem estar incompletos; ausência de registros não significa valor zero.")
with st.expander("Disponibilidade por mês", expanded=True):
    st.dataframe(pd.DataFrame(resultado["situacoes"]), hide_index=True, use_container_width=True)
if not resultado["registros"]:
    st.info("Nenhum registro disponível nesta consulta. Verifique o período ou tente novamente mais tarde.")
    st.stop()

df = pd.DataFrame(resultado["registros"])
cid = st.session_state.consulta_id
receitas = resultado["tipo"] == "Receitas"
campo_valor = "vl_arrecadacao" if receitas else "vl_despesa"
colunas_filtro = ["orgao", "ds_fonte_recurso"] if receitas else ["orgao", "evento"]
st.subheader("Resumo do período completo")
resumo_mensal = []
for situacao in resultado["situacoes"]:
    mes_texto, ano_texto = situacao["Mês"].split("/")
    competencia = f"{ano_texto}-{mes_texto}"
    dados_mes = df[df["competencia_consulta"] == competencia]
    if dados_mes.empty:
        resumo_mensal.append({"Mês": situacao["Mês"], "Situação": situacao["Situação"],
            "Registros": 0, "Movimentação": "—", "Soma dos registros": "—"})
        continue
    grupos = [("Arrecadação", dados_mes)] if receitas else dados_mes.groupby("evento", dropna=False)
    for evento, grupo in grupos:
        resumo_mensal.append({"Mês": situacao["Mês"], "Situação": situacao["Situação"],
            "Registros": len(grupo), "Movimentação": str(evento),
            "Soma dos registros": moeda(sum(grupo[campo_valor].map(valor_decimal), Decimal("0")))})
st.dataframe(pd.DataFrame(resumo_mensal), hide_index=True, use_container_width=True)
st.caption("Este resumo inclui todos os meses consultados e não muda com os filtros de detalhes abaixo.")
st.subheader("Filtrar registros detalhados")
competencias = sorted(df["competencia_consulta"].unique())
mes_detalhe = st.selectbox("Mês dos detalhes", ["Todos os meses"] + competencias,
    format_func=lambda v: v if v == "Todos os meses" else f"{v[5:7]}/{v[:4]}",
    key=f"{cid}_mes_detalhe")
if mes_detalhe != "Todos os meses":
    df = df[df["competencia_consulta"] == mes_detalhe]
f1, f2 = st.columns(2)
for pos, coluna in enumerate(colunas_filtro):
    if coluna in df:
        with [f1, f2][pos]:
            escolhidos = st.multiselect(NOMES[coluna], sorted(df[coluna].dropna().astype(str).unique()),
                key=f"{cid}_{coluna}", placeholder="Todos")
        if escolhidos:
            df = df[df[coluna].astype(str).isin(escolhidos)]
busca = st.text_input("Buscar na tabela", key=f"{cid}_busca", placeholder="Descrição, fornecedor, empenho…")
if busca:
    mascara = df.astype(str).apply(lambda c: c.str.contains(busca, case=False, regex=False, na=False)).any(axis=1)
    df = df[mascara]
st.caption(f"{len(df):,} registros após os filtros. Os totais abaixo e a exportação refletem estes filtros.")
if df.empty:
    st.info("Nenhum registro corresponde aos filtros da tabela.")
    st.stop()

valores = df[campo_valor].map(valor_decimal)
if receitas:
    st.metric("Arrecadação — todos os registros filtrados (todas as páginas)", moeda(sum(valores, Decimal("0"))))
    agrupador = "ds_fonte_recurso"
else:
    st.info("Movimentações separadas: empenhado, liquidado e pago podem representar etapas do mesmo gasto. Os totais abaixo não constituem um saldo líquido.")
    agrupador = "evento"

if agrupador in df:
    resumo = {}
    for grupo, valor in zip(df[agrupador].fillna("Não informado"), valores):
        resumo[str(grupo)] = resumo.get(str(grupo), Decimal("0")) + valor
    st.dataframe(pd.DataFrame([
        {NOMES[agrupador]: grupo, "Soma dos registros": moeda(valor)}
        for grupo, valor in sorted(resumo.items())
    ]), hide_index=True, use_container_width=True)

st.subheader("Registros detalhados")
opcao_tamanho = st.selectbox("Linhas por página", ["Todos", 25, 50, 100], key=f"{cid}_tamanho")
por_pagina = len(df) if opcao_tamanho == "Todos" else opcao_tamanho
paginas = max(1, math.ceil(len(df) / por_pagina))
# O seletor adapta-se ao total após aplicar filtros.
pagina = st.selectbox("Página", range(1, paginas + 1), key=f"{cid}_pagina_{paginas}")
tabela = df.copy()
tabela[campo_valor] = valores.map(moeda)
colunas = ["competencia_consulta"] + [c for c in tabela if c != "competencia_consulta"]
tabela = tabela[colunas].rename(columns=NOMES)
st.dataframe(tabela.iloc[(pagina - 1) * por_pagina:pagina * por_pagina],
    hide_index=True, use_container_width=True)
meses_visiveis = ", ".join(tabela.iloc[(pagina - 1) * por_pagina:pagina * por_pagina]["Competência"].unique())
st.caption(f"Página {pagina} de {paginas} · Meses nesta página: {meses_visiveis}. Role a tabela para ver os demais registros e colunas.")
with st.expander("Exportar resultados (opcional)"):
    st.download_button("Salvar CSV de todos os registros filtrados",
        df.rename(columns=NOMES).to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"{resultado['tipo'].lower()}_filtradas.csv", mime="text/csv")
