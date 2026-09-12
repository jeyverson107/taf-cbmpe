import streamlit as st
import pypdf
import pandas as pd
import json
import base64
import requests
from google import genai

st.set_page_config(page_title="Treinador TAF Militar", page_icon="🏃‍♂️", layout="wide")

st.title("🏃‍♂️ Treinador Inteligente TAF")
st.caption("Preparação física individualizada com armazenamento permanente em nuvem.")

# Configurações de API e GitHub
api_key = st.secrets.get("GEMINI_API_KEY", None)
github_token = st.secrets.get("GITHUB_TOKEN", None)
repo_name = "jeyverson107/taf-cbmpe"

if not api_key:
    api_key = st.sidebar.text_input("Sua Chave API do Gemini:", type="password")

# ==========================================
# FUNÇÕES DE PERSISTÊNCIA VIA GITHUB
# ==========================================
def carregar_dados_github(usuario):
    if not github_token:
        return {}, None
    url = f"https://api.github.com/repos/{repo_name}/contents/dados_{usuario}.json"
    headers = {"Authorization": f"Bearer {github_token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        res = r.json()
        conteudo = base64.b64decode(res["content"]).decode("utf-8")
        return json.loads(conteudo), res["sha"]
    return {}, None

def salvar_dados_github(usuario, dados, sha=None):
    if not github_token:
        st.error("GITHUB_TOKEN não configurado nos Secrets!")
        return
    url = f"https://api.github.com/repos/{repo_name}/contents/dados_{usuario}.json"
    headers = {"Authorization": f"Bearer {github_token}"}
    conteudo_b64 = base64.b64encode(json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {"message": f"Atualiza dados de {usuario}", "content": conteudo_b64}
    if sha:
        payload["sha"] = sha
    requests.put(url, headers=headers, json=payload)

# ==========================================
# LOGIN E IDENTIFICAÇÃO
# ==========================================
st.sidebar.header("👤 Perfil & Login")
usuario_input = st.sidebar.text_input("Seu Nome / Login:", value="jeyverson").strip().lower().replace(" ", "_")

if st.sidebar.button("📂 Carregar Meus Dados Salvos"):
    dados, sha = carregar_dados_github(usuario_input)
    if dados:
        st.session_state['dados'] = dados
        st.session_state['sha'] = sha
        st.sidebar.success("Dados carregados com sucesso!")
    else:
        st.sidebar.warning("Nenhum dado encontrado para este usuário. Crie um novo perfil!")

if 'dados' not in st.session_state:
    st.session_state['dados'] = {"peso": 80.0, "altura": 1.75, "historico_fisico": "Sedentário atual", "regras_taf": "", "treino_semanal": "", "diario": []}

dados_usuario = st.session_state['dados']

# Perfil Físico
st.sidebar.subheader("⚙️ Dados Físicos")
peso = st.sidebar.number_input("Peso (kg):", min_value=40.0, max_value=200.0, value=float(dados_usuario.get("peso", 80.0)))
altura = st.sidebar.number_input("Altura (m):", min_value=1.40, max_value=2.30, value=float(dados_usuario.get("altura", 1.75)))

imc = peso / (altura ** 2)
st.sidebar.metric(label="IMC", value=f"{imc:.1f}")

historico_fisico = st.sidebar.selectbox(
    "Histórico Físico:",
    ["Sedentário atual", "Sedentário total", "Iniciante ativo", "Intermediário"],
    index=0
)

if st.sidebar.button("💾 Salvar Perfil em Nuvem"):
    dados_usuario["peso"] = peso
    dados_usuario["altura"] = altura
    dados_usuario["historico_fisico"] = historico_fisico
    salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
    st.sidebar.success("Perfil salvo permanentemente!")

# ABAS
tab1, tab2, tab3, tab4 = st.tabs(["📄 1. Edital & Metas", "🎯 2. Plano Semanal", "📝 3. Diário de Treino", "🤖 4. Onde Melhorar"])

# ABA 1: Edital
with tab1:
    st.header("Upload e Leitura do Edital")
    uploaded_file = st.file_uploader(f"PDF do Edital de {usuario_input.capitalize()}:", type=["pdf"])

    if uploaded_file and api_key:
        if st.button("🔍 Extrair e Salvar Metas do TAF"):
            with st.spinner("Lendo PDF e salvando na nuvem..."):
                reader = pypdf.PdfReader(uploaded_file)
                texto_edital = "".join([page.extract_text() or "" for page in reader.pages])

                try:
                    client = genai.Client(api_key=api_key)
                    prompt = f"Extraia as exigências físicas do TAF do edital: {texto_edital[:18000]}."
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    dados_usuario["regras_taf"] = response.text
                    salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
                    st.success("Metas extraídas e salvas permanentemente!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if dados_usuario.get("regras_taf"):
        st.subheader("📌 Metas do Seu Edital (Salvas):")
        st.markdown(dados_usuario["regras_taf"])

# ABA 2: Plano Semanal
with tab2:
    st.header("Plano de Treino Semanal")
    semana = st.number_input("Semana Atual:", min_value=1, max_value=24, value=1)

    if st.button("🚀 Gerar e Salvar Plano Semanal"):
        if api_key:
            with st.spinner("Gerando cronograma..."):
                try:
                    client = genai.Client(api_key=api_key)
                    regras = dados_usuario.get("regras_taf", "Corrida 12min, Barra e Abdominal.")
                    prompt = f"Crie um plano de treinos para TAF. Atleta: {usuario_input}, IMC {imc:.1f}, Semana {semana}. Restrição: Sem natação. Metas: {regras}"
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    dados_usuario["treino_semanal"] = response.text
                    salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
                    st.success("Plano semanal gerado e salvo!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if dados_usuario.get("treino_semanal"):
        st.markdown(dados_usuario["treino_semanal"])

# ABA 3: Diário
with tab3:
    st.header("Diário de Treinos")
    with st.form("form_treino"):
        data = st.date_input("Data")
        modalidade = st.selectbox("Exercício:", ["Corrida / Caminhada", "Barra Fixa", "Abdominal", "Flexão", "Fortalecimento"])
        resultado = st.text_input("Resultado (ex: Corri 3km em 20min):")
        esforco = st.slider("Esforço Percebido (1 a 10):", 1, 10, 5)
        obs = st.text_area("Sentiu alguma dor?")
        salvar = st.form_submit_button("💾 Salvar Registro no Banco de Dados")

        if salvar:
            novo_registro = {"Data": str(data), "Exercício": modalidade, "Resultado": resultado, "Esforço": esforco, "Obs": obs}
            if "diario" not in dados_usuario:
                dados_usuario["diario"] = []
            dados_usuario["diario"].append(novo_registro)
            salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
            st.success("Treino salvo permanentemente na nuvem!")

    if dados_usuario.get("diario"):
        st.subheader("Seu Histórico Salvo:")
        st.dataframe(pd.DataFrame(dados_usuario["diario"]), use_container_width=True)

# ABA 4: Análise
with tab4:
    st.header("🤖 Análise Diagnóstica")
    if st.button("📊 Analisar Evolução Salva"):
        if dados_usuario.get("diario") and api_key:
            with st.spinner("Analisando dados do banco de dados..."):
                client = genai.Client(api_key=api_key)
                prompt = f"Analise o histórico de treinos do atleta {usuario_input}: {json.dumps(dados_usuario['diario'])}. Diga onde melhorar e riscos de lesão."
                response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                st.markdown(response.text)
        else:
            st.warning("Registre pelo menos um treino para poder analisar!")
