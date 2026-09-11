import streamlit as st
import pypdf
import pandas as pd
import os
from google import genai

st.set_page_config(page_title="Treinador TAF CFO CBMPE", page_icon="🏃‍♂️", layout="wide")

st.title("🏃‍♂️ Treinador Inteligente TAF - CFO CBMPE")
st.caption("Preparação física progressiva e adaptada ao seu edital.")

# Recupera a chave API salva nas configurações do Streamlit Cloud
api_key = st.secrets.get("GEMINI_API_KEY", None)

if not api_key:
    api_key = st.sidebar.text_input("Sua Chave API do Gemini:", type="password")

# Perfil Físico
st.sidebar.header("⚙️ Perfil do Atleta")
peso = st.sidebar.number_input("Peso Atual (kg):", min_value=40.0, max_value=200.0, value=80.0, step=0.5)
altura = st.sidebar.number_input("Altura (m):", min_value=1.40, max_value=2.30, value=1.75, step=0.01)

imc = peso / (altura ** 2)
st.sidebar.metric(label="IMC", value=f"{imc:.1f}")

if imc < 18.5:
    classificacao_imc = "Abaixo do peso"
elif 18.5 <= imc < 25:
    classificacao_imc = "Peso ideal"
elif 25 <= imc < 30:
    classificacao_imc = "Sobrepeso (atenção às articulações)"
else:
    classificacao_imc = "Obesidade (baixo impacto inicial)"

st.sidebar.info(f"**Condição:** {classificacao_imc}")

historico = st.sidebar.selectbox(
    "Histórico Físico:",
    ["Sedentário atual (já correu até 10km no passado)", "Sedentário total", "Iniciante ativo", "Intermediário"]
)

# Abas Principais
tab1, tab2, tab3, tab4 = st.tabs(["📄 1. Edital & Metas", "🎯 2. Plano Semanal", "📝 3. Registrar Treino", "🤖 4. Onde Melhorar"])

# ABA 1: Edital
with tab1:
    st.header("Upload e Leitura do Edital")
    uploaded_file = st.file_uploader("Envie o PDF do Edital do CBMPE:", type=["pdf"])

    if uploaded_file and api_key:
        if st.button("🔍 Extrair Metas do TAF"):
            with st.spinner("Analisando o PDF..."):
                reader = pypdf.PdfReader(uploaded_file)
                texto_edital = "".join([page.extract_text() or "" for page in reader.pages])

                try:
                    client = genai.Client(api_key=api_key)
                    prompt = f"Extraia com precisão as exigências físicas MASCULINAS do TAF do edital: {texto_edital[:18000]}. Ignore a natação por enquanto."
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    st.session_state['regras_taf'] = response.text
                    st.success("Metas extraídas!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if 'regras_taf' in st.session_state:
        st.markdown(st.session_state['regras_taf'])

# ABA 2: Plano de Treino
with tab2:
    st.header("Gerador de Treinos Progressivos")
    semana = st.number_input("Semana Atual:", min_value=1, max_value=24, value=1)

    if st.button("🚀 Gerar Treino da Semana"):
        if api_key:
            with st.spinner("Gerando cronograma seguro..."):
                try:
                    client = genai.Client(api_key=api_key)
                    regras = st.session_state.get('regras_taf', 'Corrida 12min (2.400m), Barra e Abdominal.')
                    prompt = f"""
                    Crie um plano semanal de treinos (Segunda a Domingo) para TAF militar.
                    Atleta: IMC {imc:.1f} ({classificacao_imc}), {historico}, Semana {semana}.
                    Restrição: Sem natação.
                    Foco: Prevenção de lesões (canelite), corrida fracionada (caminha/corre) e fortalecimento core/membros inferiores.
                    Metas TAF: {regras}
                    """
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    st.session_state['treino_semanal'] = response.text
                    st.success("Plano gerado!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if 'treino_semanal' in st.session_state:
        st.markdown(st.session_state['treino_semanal'])

# ABA 3: Diário
with tab3:
    st.header("Registrar Treino Realizado")
    with st.form("form_treino"):
        data = st.date_input("Data")
        modalidade = st.selectbox("Exercício:", ["Corrida / Caminhada", "Barra Fixa", "Abdominal", "Flexão", "Fortalecimento"])
        resultado = st.text_input("Resultado (ex: Corri 3km em 20min / 15 abdominais):")
        esforco = st.slider("Esforço Percebido (1 a 10):", 1, 10, 5)
        obs = st.text_area("Sentiu alguma dor ou desconforto?")
        salvar = st.form_submit_button("💾 Salvar Treino")

        if salvar:
            novo_dado = {"Data": str(data), "Exercício": modalidade, "Resultado": resultado, "Esforço": esforco, "Obs": obs}
            df = pd.concat([pd.read_csv("historico.csv"), pd.DataFrame([novo_dado])], ignore_index=True) if os.path.exists("historico.csv") else pd.DataFrame([novo_dado])
            df.to_csv("historico.csv", index=False)
            st.success("Treino registrado!")

    if os.path.exists("historico.csv"):
        st.dataframe(pd.read_csv("historico.csv"), use_container_width=True)

# ABA 4: Análise Inteligente
with tab4:
    st.header("🤖 Análise Diagnóstica da IA")
    if st.button("📊 Analisar Evolução"):
        if os.path.exists("historico.csv") and api_key:
            with st.spinner("Analisando histórico..."):
                df = pd.read_csv("historico.csv")
                client = genai.Client(api_key=api_key)
                prompt = f"Analise o histórico de treinos para TAF militar do candidato (IMC {imc:.1f}): {df.to_string(index=False)}. Diga onde melhorar, riscos de lesão e ajustes para a próxima semana."
                response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                st.markdown(response.text)
