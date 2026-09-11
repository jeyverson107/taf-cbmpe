import streamlit as st
import pypdf
import pandas as pd
import os
from google import genai

st.set_page_config(page_title="Treinador TAF Militar", page_icon="🏃‍♂️", layout="wide")

st.title("🏃‍♂️ Treinador Inteligente TAF")
st.caption("Preparação física individualizada e adaptada ao seu edital.")

# Chave API
api_key = st.secrets.get("GEMINI_API_KEY", None)

if not api_key:
    api_key = st.sidebar.text_input("Sua Chave API do Gemini:", type="password")

# ==========================================
# PERFIL DO USUÁRIO (IDENTIFICAÇÃO)
# ==========================================
st.sidebar.header("👤 Identificação do Atleta")
usuario = st.sidebar.text_input("Seu Nome / Login:", value="Atleta1").strip().lower().replace(" ", "_")

if not usuario:
    usuario = "padrao"

# Arquivo de histórico exclusivo deste usuário
arquivo_historico = f"historico_{usuario}.csv"

st.sidebar.header("⚙️ Perfil Físico")
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

historico_fisico = st.sidebar.selectbox(
    "Histórico Físico:",
    ["Sedentário atual (já correu no passado)", "Sedentário total", "Iniciante ativo", "Intermediário"]
)

# ABAS
tab1, tab2, tab3, tab4 = st.tabs(["📄 1. Edital & Metas", "🎯 2. Plano Semanal", "📝 3. Registrar Treino", "🤖 4. Onde Melhorar"])

# ABA 1: Edital
with tab1:
    st.header("Upload e Leitura do Edital")
    uploaded_file = st.file_uploader(f"Envie o PDF do Edital para {usuario.capitalize()}:", type=["pdf"])

    if uploaded_file and api_key:
        if st.button("🔍 Extrair Metas do TAF"):
            with st.spinner("Analisando o PDF..."):
                reader = pypdf.PdfReader(uploaded_file)
                texto_edital = "".join([page.extract_text() or "" for page in reader.pages])

                try:
                    client = genai.Client(api_key=api_key)
                    prompt = f"Extraia com precisão as exigências físicas MASCULINAS/FEMININAS do TAF do edital: {texto_edital[:18000]}. Ignore a natação por enquanto se solicitado."
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    st.session_state[f'regras_taf_{usuario}'] = response.text
                    st.success("Metas extraídas com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if f'regras_taf_{usuario}' in st.session_state:
        st.markdown(st.session_state[f'regras_taf_{usuario}'])

# ABA 2: Plano Semanal
with tab2:
    st.header(f"Plano de Treino para {usuario.capitalize()}")
    semana = st.number_input("Semana Atual:", min_value=1, max_value=24, value=1)

    if st.button("🚀 Gerar Treino da Semana"):
        if api_key:
            with st.spinner("Gerando cronograma seguro..."):
                try:
                    client = genai.Client(api_key=api_key)
                    regras = st.session_state.get(f'regras_taf_{usuario}', 'Corrida 12min, Barra e Abdominal.')
                    prompt = f"""
                    Crie um plano semanal de treinos (Segunda a Domingo) para TAF militar.
                    Atleta: {usuario}, IMC {imc:.1f} ({classificacao_imc}), Condição: {historico_fisico}, Semana {semana}.
                    Foco: Prevenção de lesões (canelite), corrida fracionada (caminha/corre) e fortalecimento core/membros inferiores.
                    Metas do TAF deste atleta: {regras}
                    """
                    response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                    st.session_state[f'treino_{usuario}'] = response.text
                    st.success("Plano gerado!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if f'treino_{usuario}' in st.session_state:
        st.markdown(st.session_state[f'treino_{usuario}'])

# ABA 3: Diário do Usuário
with tab3:
    st.header(f"Diário de Treinos - {usuario.capitalize()}")
    with st.form("form_treino"):
        data = st.date_input("Data")
        modalidade = st.selectbox("Exercício:", ["Corrida / Caminhada", "Barra Fixa", "Abdominal", "Flexão", "Fortalecimento"])
        resultado = st.text_input("Resultado (ex: Corri 3km em 20min / 15 abdominais):")
        esforco = st.slider("Esforço Percebido (1 a 10):", 1, 10, 5)
        obs = st.text_area("Sentiu alguma dor ou desconforto?")
        salvar = st.form_submit_button("💾 Salvar Treino")

        if salvar:
            novo_dado = {"Atleta": usuario, "Data": str(data), "Exercício": modalidade, "Resultado": resultado, "Esforço": esforco, "Obs": obs}
            
            if os.path.exists(arquivo_historico):
                df = pd.read_csv(arquivo_historico)
                df = pd.concat([df, pd.DataFrame([novo_dado])], ignore_index=True)
            else:
                df = pd.DataFrame([novo_dado])
                
            df.to_csv(arquivo_historico, index=False)
            st.success(f"Treino de {usuario.capitalize()} registrado!")

    if os.path.exists(arquivo_historico):
        st.subheader("Seus Registros:")
        st.dataframe(pd.read_csv(arquivo_historico), use_container_width=True)

# ABA 4: Análise por Atleta
with tab4:
    st.header(f"🤖 Análise Diagnóstica para {usuario.capitalize()}")
    if st.button("📊 Analisar Minha Evolução"):
        if os.path.exists(arquivo_historico) and api_key:
            with st.spinner("Analisando histórico individual..."):
                df = pd.read_csv(arquivo_historico)
                client = genai.Client(api_key=api_key)
                prompt = f"Analise o histórico de treinos do atleta {usuario} (IMC {imc:.1f}): {df.to_string(index=False)}. Diga onde melhorar, riscos de lesão e ajustes para o TAF dele."
                response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt)
                st.markdown(response.text)
        else:
            st.warning("Registre pelo menos um treino nesta conta para poder analisar!")
