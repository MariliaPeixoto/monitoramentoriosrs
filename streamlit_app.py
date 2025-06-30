import streamlit as st
import pandas as pd
import requests
import matplotlib.pyplot as plt
import folium
from folium import IFrame
from bs4 import BeautifulSoup
import re
import ast
import io
import base64
from urllib.parse import urlparse, parse_qs
from streamlit_folium import st_folium

st.set_page_config(layout="wide")
st.title("Monitoramento de Cotas de Inundação - Rio Grande do Sul")

@st.cache_data
def extrair_estacoes_sgb(urls):
    all_dados = []
    pattern = re.compile(
        r"""const\s+(estacao\w+)\s*=\s*L\.marker\(\[\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\s*\],\s*\{\s*icon:\s*(\w+)""", re.MULTILINE
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
                    "Icone": icone
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
    df_comsc = extrair_estacoes_sgb(urls)
    estacoes_excluir = [
        'estacaouruguai50186','estacaouruguai51102','estacaouruguai26218','estacaouruguai52105',
        'estacaouruguai61253','estacaouruguai2439','estacaouruguai2235','estacaouruguai2133',
        'estacaouruguai1117','estacaouruguai2029'
    ]
    df = df_comsc[~df_comsc['Estação'].isin(estacoes_excluir)]
    return df

@st.cache_data
def carregar_df_graf():
    url = "https://raw.githubusercontent.com/MariliaPeixoto/monitoramentoriosrs/main/df_graf.csv"
    return pd.read_csv(url)

@st.cache_data
def gerar_grafico_html_json(link, nome_estacao, cota_aten, cota_alerta, cota_inundacao):
    try:
        response = requests.get(link)
        response.raise_for_status()
        dados = response.json()
        df = pd.DataFrame(dados.items(), columns=['DataHora', 'Nivel'])
        df['DataHora'] = pd.to_datetime(df['DataHora'])
        plt.figure(figsize=(8, 4))
        plt.plot(df['DataHora'], df['Nivel'], linestyle='-', linewidth=2, label='Nível do rio', color='#88CDF6')
        if not pd.isna(cota_aten):
            plt.axhline(y=cota_aten/100, color='gold', linestyle='--', label='Cota de Atenção')
        if not pd.isna(cota_alerta):
            plt.axhline(y=cota_alerta/100, color='orange', linestyle='--', label='Cota de Alerta')
        if not pd.isna(cota_inundacao):
            plt.axhline(y=cota_inundacao/100, color='red', linestyle='--', label='Cota de Inundação')
        plt.title(f'Nível do Rio - {nome_estacao}')
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
        return f'<h4>{nome_estacao}</h4><img src="data:image/png;base64,{imagem_base64}" width="450"/>'
    except Exception as e:
        return f"<p>Erro ao gerar gráfico JSON: {e}</p>"

@st.cache_data
def extrair_dados_sgb(link):
    try:
        response = requests.get(link)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        script = next((s.string for s in soup.find_all('script') if s.string and 'const labels' in s.string and 'const valoresCota' in s.string), None)
        if not script:
            return None
        labels = ast.literal_eval(re.search(r"const labels\s*=\s*(\[[^\]]*\])", script).group(1))
        valores = ast.literal_eval(re.search(r"const valoresCota\s*=\s*(\[[^\]]*\])", script).group(1))
        return pd.DataFrame({'timestamp': pd.to_datetime(labels), 'nivel': valores})
    except Exception as e:
        print(f"[SACE] Erro ao extrair de {link}: {e}")
        return None

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
        if link.endswith('.json'):
            popup_html = gerar_grafico_html_json(
                link,
                nome_estacao=row['Nome'],
                cota_aten=row['Cota de Atenção (cm)'],
                cota_alerta=row['Cota de Alerta (cm)'],
                cota_inundacao=row['Cota de Inundação (cm)']
            )
        else:
            dados = extrair_dados_sgb(link)
            if dados is not None and not dados.empty:
                fig, ax = plt.subplots()
                dados.plot(x='timestamp', y='nivel', ax=ax,linestyle='-', linewidth=2, label='Nível do rio', legend=False, color='#88CDF6')
                ax.set_title(f"Nível do Rio - {row['Nome']}")
                ax.set_ylabel('Nível (cm)')
                ax.set_xlabel('Data')
                fig.autofmt_xdate()
                if pd.notna(row['Cota de Atenção (cm)']):
                    ax.axhline(row['Cota de Atenção (cm)'], color='gold', linestyle='--', label='Cota de Atenção')
                if pd.notna(row['Cota de Alerta (cm)']):
                    ax.axhline(row['Cota de Alerta (cm)'], color='orange', linestyle='--', label='Cota de Alerta')
                if pd.notna(row['Cota de Inundação (cm)']):
                    ax.axhline(row['Cota de Inundação (cm)'], color='red', linestyle='--', label='Cota de Inundação')
                ax.legend()
                buf = io.BytesIO()
                fig.savefig(buf, format='png')
                buf.seek(0)
                img_base64 = base64.b64encode(buf.read()).decode('utf-8')
                buf.close()
                plt.close(fig)
                popup_html = f"<h4>{row['Nome']}</h4><img src='data:image/png;base64,{img_base64}' width='450'/>"
            else:
                popup_html = f"<p>{row['Nome']}<br><i>Sem dados disponíveis</i></p>"
        popup = folium.Popup(IFrame(html=popup_html, width=470, height=370), max_width=470)
        cor = icone_cores.get(row['Icone'], 'blue')
        folium.Marker(
            location=[row['Latitude'], row['Longitude']],
            popup=popup,
            tooltip=row['Nome'],
            icon=folium.Icon(color=cor)
        ).add_to(mapa)
        # Legenda (HTML)
        legenda_html = '''
        <div style="position: fixed;
        bottom: 50px; left: 50px; width: 180px; height: 180px;
        background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
        padding: 10px; color: black;">
        <b>Legenda</b><br>
        <i class="fa fa-tint" style="color:#6FAC25"></i> Normal<br>
        <i class="fa fa-tint" style="color:gray"></i> Sem Transmissão<br>
        <i class="fa fa-tint" style="color:#FFC88C"></i> Cota de Atenção<br>
        <i class="fa fa-tint" style="color:#F0932F"></i> Cota de Alerta<br>
        <i class="fa fa-tint" style="color:#D13D29"></i> Cota de Inundação<br>
        <i class="fa fa-tint" style="color:purple"></i> Cota de Inundação Severa<br>
          </div>
        '''
        mapa.get_root().html.add_child(folium.Element(legenda_html))       
        # Adiciona o CSS do Font Awesome
        font_awesome_css = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css'
        mapa.get_root().header.add_child(folium.Element(font_awesome_css))
    return mapa

df_estacoes = carregar_dados()
df_graf = carregar_df_graf()

df_completo = pd.merge(df_graf, df_estacoes, left_on='Estação', right_on='Estação', how='left')

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

st.subheader("Mapa Interativo das Estações")
mapa = criar_mapa_completo(df_completo)
st_data = st_folium(mapa, width=1200, height=700, returned_objects=[])
