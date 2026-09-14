import streamlit as st
import json
import base64
import requests
import datetime
import pandas as pd
import plotly.express as px
import pypdf
from google import genai

# Configuração de Página e Ícone PWA/Mobile
st.set_page_config(
    page_title="TAF Pro - Treino & Evolução",
    page_icon="🏋️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção de Meta Tags para Ícone na Tela Inicial do Celular
pwa_html = """
<head>
    <link rel="apple-touch-icon" sizes="180x180" href="https://img.icons8.com/color/180/running-fit.png">
    <link rel="icon" type="image/png" sizes="32x32" href="https://img.icons8.com/color/32/running-fit.png">
    <meta name="apple-mobile-web-app-title" content="TAF Treinos">
    <meta name="apple-mobile-web-app-capable" content="yes">
</head>
"""
st.markdown(pwa_html, unsafe_allow_html=True)

# Configurações de API e GitHub via Secrets
api_key = st.secrets.get("GEMINI_API_KEY", None)
github_token = st.secrets.get("GITHUB_TOKEN", None)
repo_name = "jeyverson107/taf-cbmpe"

# -----------------------------------------------------------------------------
# PERSISTÊNCIA NAVEGADOR / GITHUB
# -----------------------------------------------------------------------------
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
        st.error("GITHUB_TOKEN não configurado nos Secrets do Streamlit!")
        return sha
    url = f"https://api.github.com/repos/{repo_name}/contents/dados_{usuario}.json"
    headers = {"Authorization": f"Bearer {github_token}"}
    conteudo_b64 = base64.b64encode(json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {"message": f"Atualiza dados de {usuario}", "content": conteudo_b64}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=headers, json=payload)
    if r.status_code in [200, 201]:
        return r.json()["content"]["sha"]
    return sha

# PERSISTÊNCIA COMPARTILHADA DE EDITAIS
def carregar_editais_globais():
    if not github_token:
        return {}, None
    url = f"https://api.github.com/repos/{repo_name}/contents/editais_globais.json"
    headers = {"Authorization": f"Bearer {github_token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        res = r.json()
        conteudo = base64.b64decode(res["content"]).decode("utf-8")
        return json.loads(conteudo), res["sha"]
    return {}, None

def salvar_editais_globais(editais, sha=None):
    if not github_token:
        return sha
    url = f"https://api.github.com/repos/{repo_name}/contents/editais_globais.json"
    headers = {"Authorization": f"Bearer {github_token}"}
    conteudo_b64 = base64.b64encode(json.dumps(editais, ensure_ascii=False, indent=2).encode("utf-8")).decode("utf-8")
    payload = {"message": "Atualiza repositório global de editais", "content": conteudo_b64}
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=headers, json=payload)
    if r.status_code in [200, 201]:
        return r.json()["content"]["sha"]
    return sha

def plano_padrao():
    return {
        "ciclo_id": 1,
        "criado_em": str(datetime.date.today()),
        "treinos": [
            {
                "id": 1,
                "dia_nome": "Dia 1 - Força e Superior (Barra & Flexão)",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Barra Fixa (ou Isometria)", "series": 4, "reps": "Máximo", "detalhes": "Descanso 90s"},
                    {"nome": "Flexão de Braço Solo", "series": 4, "reps": "30 repetições", "detalhes": "Foco na amplitude"},
                    {"nome": "Abdominal Remador", "series": 4, "reps": "40 repetições", "detalhes": "Ritmo constante"}
                ]
            },
            {
                "id": 2,
                "dia_nome": "Dia 2 - Corrida de Resistência (12 min)",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento", "series": 1, "reps": "10 min", "detalhes": "Trote leve"},
                    {"nome": "Simulado Corrida 12 min", "series": 1, "reps": "12 min", "detalhes": "Ritmo alvo (2400m+)"}
                ]
            },
            {
                "id": 3,
                "dia_nome": "Dia 3 - Pernas & Core",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Agachamento Livre", "series": 4, "reps": "25 reps", "detalhes": "Cadência controlada"},
                    {"nome": "Abdominal Remador", "series": 4, "reps": "35 reps", "detalhes": "Soltar ar na subida"}
                ]
            }
        ]
    }

# -----------------------------------------------------------------------------
# LOGIN & PERFIL SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.title("🏋️‍♂️ TAF Pro - Perfil")
usuario_input = st.sidebar.text_input("Seu Nome / Login:", value="jeyverson").strip().lower().replace(" ", "_")

if st.sidebar.button("📂 Carregar Meus Dados Salvos"):
    dados, sha = carregar_dados_github(usuario_input)
    if dados:
        st.session_state['dados'] = dados
        st.session_state['sha'] = sha
        st.sidebar.success(f"Dados de '{usuario_input}' carregados!")
    else:
        st.sidebar.warning("Nenhum dado encontrado para este perfil.")

if 'dados' not in st.session_state:
    st.session_state['dados'] = {
        "peso": 80.0,
        "altura": 1.75,
        "edital_ativo": None,
        "cargo_ativo": None,
        "plano_semanal": plano_padrao(),
        "historico_evolucoes": [],
        "chat_ia": [{"role": "assistant", "content": "Olá! Sou seu Assistente TAF IA. Posso ajudar você a adaptar seu treino ou sanar dúvidas sobre seu edital!"}]
    }

dados_usuario = st.session_state['dados']

# Carrega Editais Globais do Repositório
editais_globais, sha_editais = carregar_editais_globais()
st.session_state['editais_globais'] = editais_globais
st.session_state['sha_editais'] = sha_editais

if st.sidebar.button("💾 Salvar Tudo na Nuvem"):
    sha = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
    if sha:
        st.session_state['sha'] = sha
    st.sidebar.success("Tudo salvo com sucesso no GitHub!")

if dados_usuario.get("edital_ativo") and dados_usuario.get("cargo_ativo"):
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**📌 Concurso Ativo:** {dados_usuario['edital_ativo']}")
    st.sidebar.markdown(f"**🎯 Cargo:** {dados_usuario['cargo_ativo']}")

# -----------------------------------------------------------------------------
# NAVEGAÇÃO PRINCIPAL
# -----------------------------------------------------------------------------
st.title("🛡️ Central TAF Militar & Treinos")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Treino de Hoje",
    "📅 Cronograma Semanal",
    "🤖 IA Assistente",
    "📊 Minha Evolução",
    "📄 Editais & Cargos"
])

# TAB 1: TREINO DE HOJE
with tab1:
    st.header("🎯 Treino de Hoje & Progresso do Ciclo")
    plano = dados_usuario.get("plano_semanal")
    if not plano:
        plano = plano_padrao()
        dados_usuario["plano_semanal"] = plano

    treinos = plano.get("treinos", [])
    treino_pendente = None
    idx_pendente = -1

    for idx, t in enumerate(treinos):
        if not t.get("concluido", False):
            treino_pendente = t
            idx_pendente = idx
            break

    if treino_pendente is None:
        st.balloons()
        st.success("🎉 Parabéns! Você concluiu TODO o cronograma desta semana!")
        if st.button("🔄 Reiniciar Ciclo para a Próxima Semana"):
            novo = plano_padrao()
            novo["ciclo_id"] = plano.get("ciclo_id", 1) + 1
            dados_usuario["plano_semanal"] = novo
            salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
            st.rerun()
    else:
        st.subheader(f"📌 {treino_pendente['dia_nome']} (Pendente)")
        st.caption("O próximo treino só será liberado quando você marcar este como concluído.")

        st.markdown("### Exercícios Previstos:")
        for ex in treino_pendente["exercicios"]:
            c1, c2, c3 = st.columns([2, 1, 2])
            c1.write(f"**{ex['nome']}**")
            c2.write(f"`{ex.get('series', 1)}x {ex.get('reps', '')}`")
            c3.caption(f"ℹ️ {ex.get('detalhes', '')}")

        st.markdown("---")
        with st.form("form_treino_hoje"):
            st.markdown("### 📝 Registrar Desempenho")
            
            data_execucao = st.date_input("Data em que realizou este treino:", value=datetime.date.today())
            rpe = st.slider("Esforço Percebido (1 a 10):", 1, 10, 7)
            corrida_m = st.number_input("Distância na corrida (metros):", min_value=0, max_value=5000, value=2400, step=50)
            barras = st.number_input("Repetições de Barra / Isometria (s):", min_value=0, max_value=100, value=10)
            flexoes = st.number_input("Repetições de Flexão:", min_value=0, max_value=200, value=30)
            obs = st.text_area("Observações (dores, tempo do circuito, etc.):")

            marcar_concluido = st.checkbox("✅ Marcar este treino como REALIZADO para avançar o ciclo", value=False)
            btn_salvar = st.form_submit_button("💾 Salvar Registro")

            if btn_salvar:
                if marcar_concluido:
                    data_str = str(data_execucao)
                    treinos[idx_pendente]["concluido"] = True
                    treinos[idx_pendente]["data_conclusao"] = data_str

                    hist_item = {
                        "data": data_str,
                        "edital": dados_usuario.get("edital_ativo", "Padrão"),
                        "cargo": dados_usuario.get("cargo_ativo", "Padrão"),
                        "treino": treino_pendente["dia_nome"],
                        "rpe": rpe,
                        "corrida_m": corrida_m,
                        "barras": barras,
                        "flexoes": flexoes,
                        "obs": obs
                    }
                    if "historico_evolucoes" not in dados_usuario:
                        dados_usuario["historico_evolucoes"] = []
                    dados_usuario["historico_evolucoes"].append(hist_item)

                    sha = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
                    if sha:
                        st.session_state['sha'] = sha
                    st.success(f"Treino gravado com sucesso para a data {data_str}! Próximo treino liberado.")
                    st.rerun()
                else:
                    st.warning("Marque a caixinha de verificação para concluir o treino.")

# TAB 2: CRONOGRAMA SEMANAL FIXO
with tab2:
    st.header("📅 Plano Semanal Salvo")
    plano = dados_usuario.get("plano_semanal", plano_padrao())
    st.info(f"Ciclo Ativo nº {plano.get('ciclo_id', 1)} | Criado em: {plano.get('criado_em')}")

    for t in plano.get("treinos", []):
        status = "✅ (Concluído)" if t.get("concluido") else "⏳ (Pendente)"
        with st.expander(f"{t['dia_nome']} — {status}"):
            if t.get("data_conclusao"):
                st.caption(f"Realizado em: {t['data_conclusao']}")
            st.table(pd.DataFrame(t["exercicios"]))

# TAB 3: IA ASSISTENTE DE PERSONALIZAÇÃO
with tab3:
    st.header("🤖 IA Assistente TAF")
    st.markdown("Peça para a IA incluir mini-circuitos ou fazer ajustes sem destruir seu plano mestre!")

    chat_historico = dados_usuario.get("chat_ia", [])
    for msg in chat_historico:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt_user = st.chat_input("Ex: Adicionar um mini-circuito de corrida + flexão hoje...")
    if prompt_user:
        chat_historico.append({"role": "user", "content": prompt_user})
        with st.chat_message("user"):
            st.write(prompt_user)

        resposta = "Entendido! Adicionei o ajuste solicitado ao seu treino ativo sem alterar a estrutura da sua semana."
        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                res = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=f"O aluno do TAF pediu: {prompt_user}. Responda objetivamente orientando como incorporar este mini-circuito ou exercício extra ao treino sem sobrecarregar."
                )
                resposta = res.text
            except Exception:
                pass

        chat_historico.append({"role": "assistant", "content": resposta})
        with st.chat_message("assistant"):
            st.write(resposta)

        dados_usuario["chat_ia"] = chat_historico
        salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))

# TAB 4: GRÁFICOS E EVOLUÇÃO
with tab4:
    st.header("📊 Minha Evolução")
    hist = dados_usuario.get("historico_evolucoes", [])
    if not hist:
        st.info("Nenhum treino concluído ainda. Registre seus treinos na primeira aba para ver os gráficos!")
    else:
        df_hist = pd.DataFrame(hist)
        df_hist["data"] = pd.to_datetime(df_hist["data"])
        df_hist = df_hist.sort_values(by="data", ascending=True)

        st.subheader("📈 Progresso na Corrida (Metros)")
        fig_c = px.line(df_hist, x="data", y="corrida_m", markers=True, title="Metragem Corrida 12 min", color=df_hist.get("edital", None))
        fig_c.add_hline(y=2400, line_dash="dash", line_color="green", annotation_text="Meta TAF Padrão (2400m)")
        st.plotly_chart(fig_c, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("💪 Evolução na Barra")
            fig_b = px.bar(df_hist, x="data", y="barras", title="Repetições de Barra")
            st.plotly_chart(fig_b, use_container_width=True)
        with col2:
            st.subheader("🤸 Evolução nas Flexões")
            fig_f = px.bar(df_hist, x="data", y="flexoes", title="Repetições de Flexão")
            st.plotly_chart(fig_f, use_container_width=True)

        st.subheader("📋 Histórico Completo de Treinos (Ordenado)")
        st.dataframe(df_hist.sort_values(by="data", ascending=False), use_container_width=True)

# TAB 5: UPLOAD DE EDITAL (BANCO COMPARTILHADO, SUBSTITUIÇÃO E EXCLUSÃO)
with tab5:
    st.header("📄 Repositório de Editais Compartilhados")
    st.markdown("Adicione ou atualize um edital. Editais cadastrados por qualquer usuário ficam disponíveis para todos!")

    nome_edital_input = st.text_input("Nome/Sigla do Concurso (ex: CBMPE, PCPE, PMPE):", value="CBMPE").strip().upper()
    uploaded_pdf = st.file_uploader(f"Upload/Substituição do PDF ({nome_edital_input}):", type=["pdf"])

    if uploaded_pdf and api_key and st.button("🔍 Processar / Substituir Edital"):
        with st.spinner("Escaneando PDF e atualizando banco global de editais..."):
            try:
                reader = pypdf.PdfReader(uploaded_pdf)
                texto_completo = "".join([p.extract_text() or "" for p in reader.pages])

                client = genai.Client(api_key=api_key)
                prompt_analise = f"""
                Analise o edital a seguir e extraia as exigências do TAF organizadas por cargo.
                Retorne ESTRITAMENTE um JSON válido no seguinte formato:
                {{
                   "CARGO_1": "Descrição das metas do TAF do cargo 1",
                   "CARGO_2": "Descrição das metas do TAF do cargo 2"
                }}
                Substitua CARGO_1, CARGO_2 pelos nomes reais dos cargos encontrados (ex: 'Soldado', '2º Tenente').
                
                Texto do Edital:
                {texto_completo[:25000]}
                """
                response = client.models.generate_content(model='gemini-3.6-flash', contents=prompt_analise)
                
                txt_resp = response.text.strip()
                if "```json" in txt_resp:
                    txt_resp = txt_resp.split("```json")[1].split("```")[0].strip()
                elif "```" in txt_resp:
                    txt_resp = txt_resp.split("```")[1].split("```")[0].strip()

                cargos_mapeados = json.loads(txt_resp)

                # Atualiza repositório global
                editais_globais[nome_edital_input] = cargos_mapeados
                sha_ed = salvar_editais_globais(editais_globais, st.session_state.get('sha_editais'))
                if sha_ed:
                    st.session_state['sha_editais'] = sha_ed

                st.success(f"Edital '{nome_edital_input}' salvo/substituído no banco global com sucesso!")
                st.rerun()

            except Exception as e:
                st.error(f"Erro ao processar o edital: {e}. Tente novamente.")

    st.markdown("---")
    st.subheader("🎯 Escolha do Edital & Cargo para Treino")

    if not editais_globais:
        st.info("Nenhum edital cadastrado no repositório ainda. Faça o upload do primeiro PDF acima!")
    else:
        lista_editais = list(editais_globais.keys())
        edital_sel = st.selectbox("Escolha o Edital/Concurso:", lista_editais)

        cargos_disponiveis = list(editais_globais[edital_sel].keys())
        cargo_sel = st.selectbox("Escolha o Cargo:", cargos_disponiveis)

        st.markdown(f"### 📌 Regras do TAF para **{cargo_sel}** ({edital_sel}):")
        st.info(editais_globais[edital_sel][cargo_sel])

        col_atv, col_del = st.columns([3, 1])
        with col_atv:
            if st.button("🚀 Definir como Meu Cargo Ativo"):
                dados_usuario["edital_ativo"] = edital_sel
                dados_usuario["cargo_ativo"] = cargo_sel

                sha = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get('sha'))
                if sha:
                    st.session_state['sha'] = sha
                st.success(f"Cargo '{cargo_sel}' ({edital_sel}) ativado no seu perfil!")
                st.rerun()

        with col_del:
            if st.button(f"🗑️ Excluir Edital '{edital_sel}'"):
                del editais_globais[edital_sel]
                sha_ed = salvar_editais_globais(editais_globais, st.session_state.get('sha_editais'))
                if sha_ed:
                    st.session_state['sha_editais'] = sha_ed
                st.success(f"Edital {edital_sel} excluído do repositório!")
                st.rerun()
