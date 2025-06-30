import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import base64
import io
import matplotlib.pyplot as plt
import requests
from bs4 import BeautifulSoup
import re
import ast

from cota_de_inundação_bacias_uruguai,_taquari_e_caí import (
    extrair_estacoes_sace,
    gerar_grafico_html_json,
    extrair_dados_sgb,
    criar_mapa_completo
)

# URLs das bacias
urls = [
    "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=uruguai",
    "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=taquari",
    "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=cai"
]

# Carrega os dados
df_completo = None
@st.cache_data
def carregar_dados():
    from cota_de_inundação_bacias_uruguai,_taquari_e_caí import df_completo
    return df_completo

df_completo = carregar_dados()

# Título
st.title("Monitoramento de Cotas de Inundação - Bacias Uruguai, Taquari e Caí")

# Seletor de estação
estacoes = df_completo["Nome"].dropna().unique()
estacao_selecionada = st.selectbox("Selecione uma estação:", sorted(estacoes))

# Filtra os dados da estação
dados_estacao = df_completo[df_completo["Nome"] == estacao_selecionada].iloc[0]
link = dados_estacao["Link_graf"]

# Exibe gráfico
st.subheader(f"Gráfico da estação: {estacao_selecionada}")
if link.endswith(".json"):
    html = gerar_grafico_html_json(
        link,
        nome_estacao=dados_estacao["Nome"],
        cota_aten=dados_estacao["Cota de Atenção (cm)"],
        cota_alerta=dados_estacao["Cota de Alerta (cm)"],
        cota_inundacao=dados_estacao["Cota de Inundação (cm)"]
    )
    st.components.v1.html(html, height=400)
else:
    df = extrair_dados_sgb(link)
    if df is not None and not df.empty:
        fig, ax = plt.subplots()
        df.plot(x='timestamp', y='nivel', ax=ax, legend=False)
        ax.set_title(f"Nível do Rio - {dados_estacao['Nome']}")
        ax.set_ylabel("Nível (cm)")
        ax.set_xlabel("Data")
        fig.autofmt_xdate()
        if pd.notna(dados_estacao["Cota de Atenção (cm)"]):
            ax.axhline(dados_estacao["Cota de Atenção (cm)"], color='gold', linestyle='--', label='Atenção')
        if pd.notna(dados_estacao["Cota de Alerta (cm)"]):
            ax.axhline(dados_estacao["Cota de Alerta (cm)"], color='orange', linestyle='--', label='Alerta')
        if pd.notna(dados_estacao["Cota de Inundação (cm)"]):
            ax.axhline(dados_estacao["Cota de Inundação (cm)"], color='red', linestyle='--', label='Inundação')
        ax.legend()
        st.pyplot(fig)
    else:
        st.warning("Dados não disponíveis para esta estação.")

# Exibe o mapa completo
st.subheader("Mapa Interativo das Estações")
mapa = criar_mapa_completo(df_completo)
st_data = st_folium(mapa, width=700, height=500)
