import streamlit as st
import json
import base64
import requests
import datetime
import hashlib
import re
import pandas as pd
import plotly.express as px
import pypdf
from google import genai

# =============================================================================
# CONFIGURAÇÃO DE PÁGINA E ÍCONE PWA/MOBILE
# =============================================================================
st.set_page_config(
    page_title="TAF Pro - Treino & Evolução",
    page_icon="🏋️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# CORREÇÃO: nome do modelo isolado numa constante.
# O código original usava "gemini-3.6-flash", que não corresponde a nenhum
# modelo documentado pela Google (conferido em 14/09/2026). Antes de usar em
# produção, confira o nome exato em https://ai.google.dev/gemini-api/docs/models
# "gemini-2.5-flash" é válido hoje, mas a Google já avisou que será desativado
# em 16/10/2026 — troque para o modelo vigente quando essa data se aproximar.
GEMINI_MODEL = "gemini-2.5-flash"


# =============================================================================
# HELPERS DE SEGURANÇA / SANITIZAÇÃO
# =============================================================================
def normalizar_usuario(nome: str) -> str:
    """Converte o nome digitado em um identificador seguro para nome de arquivo.
    CORREÇÃO: o código original usava o texto digitado quase sem filtro para
    montar o caminho do arquivo no GitHub (`dados_{usuario}.json`). Isso permitia
    caracteres como '/', o que é um risco de path traversal."""
    nome = (nome or "").strip().lower()
    nome = re.sub(r"\s+", "_", nome)
    nome = re.sub(r"[^a-z0-9_\-]", "", nome)
    return nome or "usuario"


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def agora_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# =============================================================================
# CAMADA DE PERSISTÊNCIA (GITHUB COMO BANCO DE DADOS)
# =============================================================================
def _github_get(path):
    """Lê um arquivo JSON do repositório. Retorna (dados, sha, erro)."""
    if not github_token:
        return None, None, "GITHUB_TOKEN não configurado nos Secrets do Streamlit."
    url = f"https://api.github.com/repos/{repo_name}/contents/{path}"
    headers = {"Authorization": f"Bearer {github_token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException as e:
        return None, None, f"Falha de rede ao ler {path}: {e}"
    if r.status_code == 200:
        res = r.json()
        conteudo = base64.b64decode(res["content"]).decode("utf-8")
        return json.loads(conteudo), res["sha"], None
    if r.status_code == 404:
        return {}, None, None  # arquivo ainda não existe: não é erro
    return None, None, f"Erro {r.status_code} ao ler {path}: {r.text[:200]}"


def _github_put(path, dados, sha, mensagem):
    """Grava um arquivo JSON no repositório. Retorna (novo_sha, aviso_ou_erro).
    Se o retorno for (None, erro) a gravação falhou de fato.
    Se o retorno for (sha, aviso) a gravação funcionou, mas houve algo a avisar
    (ex.: conflito de concorrência resolvido sobrescrevendo outra alteração)."""
    if not github_token:
        return None, "GITHUB_TOKEN não configurado nos Secrets do Streamlit."
    url = f"https://api.github.com/repos/{repo_name}/contents/{path}"
    headers = {"Authorization": f"Bearer {github_token}"}
    conteudo_b64 = base64.b64encode(
        json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")
    payload = {"message": mensagem, "content": conteudo_b64}
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
    except requests.RequestException as e:
        return None, f"Falha de rede ao salvar {path}: {e}"

    if r.status_code in (200, 201):
        return r.json()["content"]["sha"], None

    if r.status_code == 409:
        # CORREÇÃO CRÍTICA: no código original, um conflito de gravação (ex.:
        # dois dispositivos salvando quase ao mesmo tempo) era simplesmente
        # ignorado — a função retornava o sha antigo sem avisar ninguém, e a
        # tela ainda mostrava "salvo com sucesso". Aqui buscamos a versão mais
        # recente e tentamos gravar de novo uma vez, avisando o usuário.
        _, sha_atual, erro_leitura = _github_get(path)
        if erro_leitura:
            return None, erro_leitura
        payload["sha"] = sha_atual
        try:
            r2 = requests.put(url, headers=headers, json=payload, timeout=15)
        except requests.RequestException as e:
            return None, f"Falha de rede ao salvar {path} após conflito: {e}"
        if r2.status_code in (200, 201):
            return (
                r2.json()["content"]["sha"],
                "Havia uma alteração mais recente salva por outro dispositivo/usuário; "
                "ela foi sobrescrita por esta gravação.",
            )
        return None, f"Conflito de gravação não resolvido (erro {r2.status_code})."

    return None, f"Erro {r.status_code} ao salvar {path}: {r.text[:200]}"


def carregar_dados_github(usuario):
    dados, sha, erro = _github_get(f"dados_{usuario}.json")
    if erro:
        st.sidebar.error(f"❌ {erro}")
        return {}, None
    return (dados or {}), sha


def salvar_dados_github(usuario, dados, sha=None):
    """Retorna (novo_sha, sucesso: bool). CORREÇÃO: agora o chamador sabe de
    verdade se a gravação funcionou, em vez de sempre ler 'sucesso' na tela."""
    novo_sha, msg = _github_put(f"dados_{usuario}.json", dados, sha, f"Atualiza dados de {usuario}")
    if novo_sha is None:
        st.sidebar.error(f"❌ Falha ao salvar seus dados: {msg}")
        return sha, False
    if msg:
        st.sidebar.warning(f"⚠️ {msg}")
    return novo_sha, True


def carregar_editais_globais():
    dados, sha, erro = _github_get("editais_globais.json")
    if erro:
        st.error(f"❌ {erro}")
        return {}, None
    return (dados or {}), sha


def salvar_editais_globais(editais, sha=None):
    novo_sha, msg = _github_put(
        "editais_globais.json", editais, sha, "Atualiza repositório global de editais"
    )
    if novo_sha is None:
        st.error(f"❌ Falha ao salvar o repositório de editais: {msg}")
        return sha, False
    if msg:
        st.warning(f"⚠️ {msg}")
    return novo_sha, True


def normalizar_edital(entrada):
    """Garante que todo edital tenha o formato {'_meta': {...}, 'cargos': {...}}.
    CORREÇÃO (atribuição de autoria): o formato antigo guardava só os cargos,
    sem indicar quem cadastrou ou atualizou o edital. Editais salvos antes
    desta correção são convertidos automaticamente ao serem lidos, sem precisar
    reprocessar o PDF."""
    if isinstance(entrada, dict) and "cargos" in entrada and "_meta" in entrada:
        return entrada
    return {
        "_meta": {
            "criado_por": "desconhecido (cadastrado antes desta versão)",
            "criado_em": None,
            "atualizado_por": None,
            "atualizado_em": None,
            "arquivo_origem": None,
        },
        "cargos": entrada if isinstance(entrada, dict) else {},
    }


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
                    {"nome": "Abdominal Remador", "series": 4, "reps": "40 repetições", "detalhes": "Ritmo constante"},
                ],
            },
            {
                "id": 2,
                "dia_nome": "Dia 2 - Corrida de Resistência (12 min)",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento", "series": 1, "reps": "10 min", "detalhes": "Trote leve"},
                    {"nome": "Simulado Corrida 12 min", "series": 1, "reps": "12 min", "detalhes": "Ritmo alvo (2400m+)"},
                ],
            },
            {
                "id": 3,
                "dia_nome": "Dia 3 - Pernas & Core",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Agachamento Livre", "series": 4, "reps": "25 reps", "detalhes": "Cadência controlada"},
                    {"nome": "Abdominal Remador", "series": 4, "reps": "35 reps", "detalhes": "Soltar ar na subida"},
                ],
            },
        ],
    }


# =============================================================================
# LOGIN & PERFIL (SIDEBAR)
# =============================================================================
st.sidebar.title("🏋️‍♂️ TAF Pro - Perfil")
usuario_raw = st.sidebar.text_input("Seu Nome / Login:", value="jeyverson")
usuario_input = normalizar_usuario(usuario_raw)
if usuario_raw.strip() and normalizar_usuario(usuario_raw) != usuario_raw.strip().lower().replace(" ", "_"):
    st.sidebar.caption(f"Login normalizado para: `{usuario_input}`")

# CORREÇÃO (contaminação entre perfis): no código original, trocar o nome no
# campo sem clicar em "Carregar" fazia o app continuar usando os dados já
# carregados na sessão — possivelmente de OUTRO perfil — e podia salvá-los por
# cima do perfil novo. Agora, toda vez que o login muda, os dados são
# recarregados automaticamente do GitHub.
if st.session_state.get("usuario_carregado") != usuario_input:
    dados_remotos, sha_remoto = carregar_dados_github(usuario_input)
    st.session_state["dados"] = dados_remotos if dados_remotos else {}
    st.session_state["sha"] = sha_remoto
    st.session_state["usuario_carregado"] = usuario_input
    st.session_state["pin_ok"] = False

if st.sidebar.button("🔄 Recarregar Meus Dados Agora"):
    dados_remotos, sha_remoto = carregar_dados_github(usuario_input)
    st.session_state["dados"] = dados_remotos if dados_remotos else {}
    st.session_state["sha"] = sha_remoto
    st.session_state["pin_ok"] = False
    st.rerun()

dados_usuario = st.session_state["dados"]

# -----------------------------------------------------------------------
# PROTEÇÃO SIMPLES POR PIN
# -----------------------------------------------------------------------
# Importante: isto NÃO é um sistema de autenticação robusto — não existe forma
# de impedir alguém de digitar o nome de outra pessoa no campo de login. O que
# o PIN evita é o caso mais comum: alguém acessar/editar/apagar por engano (ou
# curiosidade) os dados de outro perfil. Se este app for usado por pessoas que
# você não confia totalmente, considere um login de verdade (ex.: Google OAuth
# via st.secrets, ou a biblioteca streamlit-authenticator).
if dados_usuario.get("pin_hash"):
    if not st.session_state.get("pin_ok"):
        st.sidebar.info("🔒 Perfil protegido por PIN.")
        pin_tentativa = st.sidebar.text_input(
            "Digite o PIN para continuar:", type="password", key=f"pin_{usuario_input}"
        )
        if pin_tentativa:
            if hash_pin(pin_tentativa) == dados_usuario["pin_hash"]:
                st.session_state["pin_ok"] = True
                st.rerun()
            else:
                st.sidebar.error("PIN incorreto.")
        st.stop()
else:
    st.sidebar.warning("⚠️ Este perfil ainda não tem PIN de proteção.")
    with st.sidebar.form("form_criar_pin"):
        novo_pin = st.text_input("Criar um PIN (mín. 4 dígitos):", type="password")
        confirmar_pin = st.form_submit_button("Definir PIN")
        if confirmar_pin:
            if len(novo_pin) >= 4:
                dados_usuario["pin_hash"] = hash_pin(novo_pin)
                novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
                if ok:
                    st.session_state["sha"] = novo_sha
                    st.session_state["pin_ok"] = True
                    st.sidebar.success("PIN definido e salvo!")
                    st.rerun()
            else:
                st.sidebar.error("Use pelo menos 4 dígitos.")
    st.session_state["pin_ok"] = True  # permite uso normal enquanto o PIN não é definido

# Garante estrutura padrão de dados (substitui o "if 'dados' not in
# session_state" monolítico do código original por defaults por campo — assim
# um perfil carregado do GitHub que só tenha PARTE dos campos não quebra o app)
dados_usuario.setdefault("peso", 80.0)
dados_usuario.setdefault("altura", 1.75)
dados_usuario.setdefault("edital_ativo", None)
dados_usuario.setdefault("cargo_ativo", None)
dados_usuario.setdefault("plano_semanal", plano_padrao())
dados_usuario.setdefault("historico_evolucoes", [])
dados_usuario.setdefault(
    "chat_ia",
    [{"role": "assistant", "content": "Olá! Sou seu Assistente TAF IA. Posso ajudar você a adaptar seu treino ou sanar dúvidas sobre seu edital!"}],
)

# Carrega Editais Globais do Repositório
editais_globais, sha_editais = carregar_editais_globais()
st.session_state["editais_globais"] = editais_globais
st.session_state["sha_editais"] = sha_editais

if st.sidebar.button("💾 Salvar Tudo na Nuvem"):
    novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
    if ok:
        st.session_state["sha"] = novo_sha
        st.sidebar.success("Tudo salvo com sucesso no GitHub!")
    # CORREÇÃO: se `ok` for False, salvar_dados_github já mostrou st.sidebar.error
    # com o motivo — antes disso o app mostrava "sucesso" de qualquer forma.

if dados_usuario.get("edital_ativo") and dados_usuario.get("cargo_ativo"):
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**📌 Concurso Ativo:** {dados_usuario['edital_ativo']}")
    st.sidebar.markdown(f"**🎯 Cargo:** {dados_usuario['cargo_ativo']}")

# =============================================================================
# NAVEGAÇÃO PRINCIPAL
# =============================================================================
st.title("🛡️ Central TAF Militar & Treinos")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🎯 Treino de Hoje", "📅 Cronograma Semanal", "🤖 IA Assistente", "📊 Minha Evolução", "📄 Editais & Cargos"]
)

# -----------------------------------------------------------------------
# TAB 1: TREINO DE HOJE
# -----------------------------------------------------------------------
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
            novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
            if ok:
                st.session_state["sha"] = novo_sha
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
                        "obs": obs,
                    }
                    dados_usuario["historico_evolucoes"].append(hist_item)
                    novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
                    if ok:
                        st.session_state["sha"] = novo_sha
                        st.success(f"Treino gravado com sucesso para a data {data_str}! Próximo treino liberado.")
                        st.rerun()
                    else:
                        st.error("O registro NÃO foi salvo na nuvem (veja o erro na barra lateral). Tente salvar novamente antes de sair.")
                else:
                    st.warning("Marque a caixinha de verificação para concluir o treino.")

# -----------------------------------------------------------------------
# TAB 2: CRONOGRAMA SEMANAL FIXO
# -----------------------------------------------------------------------
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

# -----------------------------------------------------------------------
# TAB 3: IA ASSISTENTE DE PERSONALIZAÇÃO
# -----------------------------------------------------------------------
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

        # CORREÇÃO CRÍTICA: o código original tinha um "except Exception: pass"
        # e, se a chamada à IA falhasse, exibia de qualquer forma a frase fixa
        # "Entendido! Adicionei o ajuste solicitado..." — ou seja, confirmava uma
        # ação que nunca aconteceu. Agora, se a IA falhar, o app avisa
        # explicitamente e deixa claro que nada foi alterado.
        resposta = None
        erro_ia = None
        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                res = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=(
                        f"O aluno do TAF pediu: {prompt_user}. Responda objetivamente orientando "
                        "como incorporar este mini-circuito ou exercício extra ao treino sem sobrecarregar."
                    ),
                )
                resposta = res.text
            except Exception as e:
                erro_ia = str(e)
        else:
            erro_ia = "a chave GEMINI_API_KEY não está configurada nos Secrets"

        if resposta is None:
            resposta = (
                f"⚠️ Não consegui consultar a IA agora ({erro_ia}). "
                "Nada foi alterado automaticamente no seu treino — se quiser, "
                "ajuste manualmente na aba 'Cronograma Semanal'."
            )

        chat_historico.append({"role": "assistant", "content": resposta})
        with st.chat_message("assistant"):
            st.write(resposta)

        dados_usuario["chat_ia"] = chat_historico
        novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
        if ok:
            st.session_state["sha"] = novo_sha

# -----------------------------------------------------------------------
# TAB 4: GRÁFICOS E EVOLUÇÃO
# -----------------------------------------------------------------------
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

# -----------------------------------------------------------------------
# TAB 5: EDITAIS (BANCO COMPARTILHADO, COM ATRIBUIÇÃO E CONFIRMAÇÃO DE EXCLUSÃO)
# -----------------------------------------------------------------------
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
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt_analise)

                txt_resp = response.text.strip()
                if "```json" in txt_resp:
                    txt_resp = txt_resp.split("```json")[1].split("```")[0].strip()
                elif "```" in txt_resp:
                    txt_resp = txt_resp.split("```")[1].split("```")[0].strip()

                cargos_mapeados = json.loads(txt_resp)

                # CORREÇÃO (atribuição de autoria): registramos quem cadastrou/
                # atualizou o edital e quando, preservando o histórico se o
                # edital já existia.
                entrada_existente = editais_globais.get(nome_edital_input)
                agora = agora_iso()
                if entrada_existente:
                    entrada = normalizar_edital(entrada_existente)
                    entrada["_meta"]["atualizado_por"] = usuario_input
                    entrada["_meta"]["atualizado_em"] = agora
                    entrada["_meta"]["arquivo_origem"] = uploaded_pdf.name
                else:
                    entrada = {
                        "_meta": {
                            "criado_por": usuario_input,
                            "criado_em": agora,
                            "atualizado_por": usuario_input,
                            "atualizado_em": agora,
                            "arquivo_origem": uploaded_pdf.name,
                        },
                        "cargos": {},
                    }
                entrada["cargos"] = cargos_mapeados
                editais_globais[nome_edital_input] = entrada

                novo_sha, ok = salvar_editais_globais(editais_globais, st.session_state.get("sha_editais"))
                if ok:
                    st.session_state["sha_editais"] = novo_sha
                    st.success(f"Edital '{nome_edital_input}' salvo/substituído no banco global com sucesso!")
                    st.rerun()

            except json.JSONDecodeError:
                st.error(
                    "A IA não retornou um JSON válido para este edital. "
                    "Tente novamente ou verifique se o PDF tem texto selecionável (não é uma imagem escaneada)."
                )
            except Exception as e:
                st.error(f"Erro ao processar o edital: {e}. Tente novamente.")

    st.markdown("---")
    st.subheader("🎯 Escolha do Edital & Cargo para Treino")

    if not editais_globais:
        st.info("Nenhum edital cadastrado no repositório ainda. Faça o upload do primeiro PDF acima!")
    else:
        lista_editais = list(editais_globais.keys())
        edital_sel = st.selectbox("Escolha o Edital/Concurso:", lista_editais)

        entrada_sel = normalizar_edital(editais_globais[edital_sel])
        meta = entrada_sel["_meta"]
        cargos_disponiveis = list(entrada_sel["cargos"].keys())

        if not cargos_disponiveis:
            st.warning("Este edital não tem cargos cadastrados.")
        else:
            cargo_sel = st.selectbox("Escolha o Cargo:", cargos_disponiveis)

            st.markdown(f"### 📌 Regras do TAF para **{cargo_sel}** ({edital_sel}):")
            st.info(entrada_sel["cargos"][cargo_sel])

            rodape = f"📥 Cadastrado por **{meta.get('criado_por', 'desconhecido')}**"
            if meta.get("criado_em"):
                rodape += f" em {meta['criado_em']}"
            if meta.get("atualizado_em"):
                rodape += f" · Última atualização por **{meta.get('atualizado_por')}** em {meta['atualizado_em']}"
            st.caption(rodape)

            col_atv, col_del = st.columns([3, 1])
            with col_atv:
                if st.button("🚀 Definir como Meu Cargo Ativo"):
                    dados_usuario["edital_ativo"] = edital_sel
                    dados_usuario["cargo_ativo"] = cargo_sel
                    novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
                    if ok:
                        st.session_state["sha"] = novo_sha
                        st.success(f"Cargo '{cargo_sel}' ({edital_sel}) ativado no seu perfil!")
                        st.rerun()

            with col_del:
                # CORREÇÃO: exclusão de um edital compartilhado agora exige
                # confirmação em duas etapas (antes era um clique só e sem volta,
                # afetando todos os usuários do app).
                confirmar_key = f"confirma_exclusao_{edital_sel}"
                if not st.session_state.get(confirmar_key):
                    if st.button(f"🗑️ Excluir '{edital_sel}'"):
                        st.session_state[confirmar_key] = True
                        st.rerun()
                else:
                    st.warning(f"Confirma excluir **{edital_sel}** para TODOS os usuários? Isso não pode ser desfeito.")
                    c_sim, c_nao = st.columns(2)
                    if c_sim.button("✅ Sim, excluir"):
                        del editais_globais[edital_sel]
                        novo_sha, ok = salvar_editais_globais(editais_globais, st.session_state.get("sha_editais"))
                        if ok:
                            st.session_state["sha_editais"] = novo_sha
                            st.success(f"Edital {edital_sel} excluído do repositório!")
                        st.session_state[confirmar_key] = False
                        st.rerun()
                    if c_nao.button("↩️ Cancelar"):
                        st.session_state[confirmar_key] = False
                        st.rerun()
