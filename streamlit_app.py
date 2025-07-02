import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse, parse_qs
import matplotlib.pyplot as plt
import ast
import io
import base64
from folium import IFrame

# Configurações da página
st.set_page_config(
    page_title="Monitoramento rios - RS",
    page_icon="https://raw.githubusercontent.com/MariliaPeixoto/monitoramentoriosrs/main/enchente.png",
    layout="wide",
    initial_sidebar_state='expanded'
)

col1, col2, col3 = st.columns([1,4,1])
col3.image('https://github.com/andrejarenkow/csv/blob/master/logo_cevs%20(2).png?raw=true', width=150)
col2.title('Monitoramento de Cotas de Inundação - Rio Grande do Sul')
col1.image('https://github.com/andrejarenkow/csv/blob/master/logo_estado%20(3)%20(1).png?raw=true', width=230)

st.set_page_config(layout="wide")
st.title("Monitoramento de Cotas de Inundação - RS")

@st.cache_data
def extrair_estacoes_sace(urls):
    all_dados = []
    pattern = re.compile(
        r"""const\s+(estacao\w+)\s*=\s*L\.marker\(\[\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\],\s*\{\s*icon:\s*(\w+)""",
        re.MULTILINE
    )
    for url in urls:
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            script_text = "\n".join(script.string or "" for script in soup.find_all("script"))
            query = parse_qs(urlparse(url).query)
            bacia = query.get('bacia', ['desconhecida'])[0]
            matches = pattern.findall(script_text)
            for nome, lat, lon, icone in matches:
                all_dados.append({
                    "Bacia": bacia,
                    "Estação": nome,
                    "Latitude": float(lat),
                    "Longitude": float(lon),
                    "Ícone": icone
                })
        except Exception as e:
            print(f"Erro ao processar {url}: {e}")
    return pd.DataFrame(all_dados)

@st.cache_data
def carregar_dados():
    urls = [
        "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=uruguai",
        "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=taquari",
        "https://www.sgb.gov.br/sace/sace_nivel/estacoes_mapa.php?bacia=cai"
    ]
    df_comsc = extrair_estacoes_sace(urls)
    estacoes_excluir = [
        'estacaouruguai50186','estacaouruguai51102','estacaouruguai26218','estacaouruguai52105',
        'estacaouruguai61253','estacaouruguai2439','estacaouruguai2235','estacaouruguai2133',
        'estacaouruguai1117','estacaouruguai2029'
    ]
    df = df_comsc[~df_comsc['Estação'].isin(estacoes_excluir)]
    url = "https://raw.githubusercontent.com/MariliaPeixoto/monitoramentoriosrs/main/df_graf.csv"
    df_graf = pd.read_csv(url)
    df_completo = pd.merge(df_graf, df, on='Estação', how='left')
    coordenadas = {
        'Porto Alegre': (-30.027158, -51.232180),
        'São Leopoldo': (-29.758580, -51.146231),
        'São Sebastião do Caí': (-29.590666, -51.384399),
        'Feliz': (-29.456949,-51.309573),
        'Taquara': (-29.641439,-50.802475),
        'Gravataí': (-29.963965,-50.979510),
        'Dona Francisca': (-29.627423,-53.352575)
    }
    for estacao, (lat, lon) in coordenadas.items():
        df_completo.loc[df_completo['Nome'] == estacao, 'Latitude'] = lat
        df_completo.loc[df_completo['Nome'] == estacao, 'Longitude'] = lon
    return df_completo

def gerar_grafico_html_json(link, nome_estacao, cota_aten, cota_alerta, cota_inundacao):
    try:
        response = requests.get(link)
        response.raise_for_status()
        dados = response.json()
        df = pd.DataFrame(dados.items(), columns=['DataHora', 'Nivel'])
        df['DataHora'] = pd.to_datetime(df['DataHora'])
        df['Nivel'] = df['Nivel'].astype(float)
        ultimo_nivel = df['Nivel'].iloc[-1] * 100
        if pd.notna(cota_inundacao) and ultimo_nivel >= cota_inundacao:
            categoria = 'CotaDeInundao'
        elif pd.notna(cota_alerta) and ultimo_nivel >= cota_alerta:
            categoria = 'CotaDeAlerta'
        elif pd.notna(cota_aten) and ultimo_nivel >= cota_aten:
            categoria = 'CotaDeAteno'
        else:
            categoria = 'Normal'
        plt.figure(figsize=(8, 4))
        plt.plot(df['DataHora'], df['Nivel'], linestyle='-', linewidth=2, label='Nível do rio', color='#88CDF6')
        if not pd.isna(cota_aten):
            plt.axhline(y=cota_aten/100, color='gold', linestyle='--', label='Cota de Atenção')
        if not pd.isna(cota_alerta):
            plt.axhline(y=cota_alerta/100, color='orange', linestyle='--', label='Cota de Alerta')
        if not pd.isna(cota_inundacao):
            plt.axhline(y=cota_inundacao/100, color='red', linestyle='--', label='Cota de Inundação')
        plt.title(f'{nome_estacao}')
        plt.xlabel('Data e Hora')
        plt.ylabel('Nível (m)')
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        imagem_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        html = f'<h4>{nome_estacao}</h4><img src="data:image/png;base64,{imagem_base64}" width="450"/>'
        return html, categoria
    except Exception as e:
        return f"<p>Erro ao gerar gráfico JSON: {e}</p>", 'SemTransmisso'

def criar_mapa_completo(df_completo):
    mapa = folium.Map(location=[df_completo['Latitude'].mean(), df_completo['Longitude'].mean()], zoom_start=7)
    icone_cores = {
        'Normal': 'green',
        'CotaDeAteno': 'beige',
        'CotaDeAlerta': 'orange',
        'CotaDeInundao': 'red',
        'CotaDeInundaoSevera': 'darkred',
        'SemTransmisso': 'gray'
    }
    for _, row in df_completo.iterrows():
        link = row['Link_graf']
        popup_html = ""
        categoria = row['Ícone']
        if link.endswith('.json'):
            popup_html, categoria = gerar_grafico_html_json(
                link,
                nome_estacao=row['Nome'],
                cota_aten=row['Cota de Atenção (cm)'],
                cota_alerta=row['Cota de Alerta (cm)'],
                cota_inundacao=row['Cota de Inundação (cm)']
            )
        else:
            popup_html = f"<p>{row['Nome']}<br><i>Sem dados disponíveis</i></p>"
        popup = folium.Popup(IFrame(html=popup_html, width=470, height=370), max_width=470)
        cor = icone_cores.get(categoria, 'blue')
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=popup,
            tooltip=row['Nome'],
            icon=folium.Icon(color=cor)
        ).add_to(mapa)
    return mapa

df_completo = carregar_dados()
mapa_final = criar_mapa_completo(df_completo)
folium_static(mapa_final, width=1200, height=700, returned_objects=[])
