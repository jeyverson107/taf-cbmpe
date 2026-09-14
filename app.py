"""
Aplicativo Streamlit de Treinamento para TAF (Teste de Aptidão Física)
Versão Melhorada com Persistência, Controle de Ciclo, Chat de IA e Evolução Visual.
"""

import streamlit as st
import json
import os
import pandas as pd
import datetime
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 6. CONFIGURAÇÃO DE PÁGINA E ÍCONE PERSONALIZADO (FAVICON / TAF)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="TAF Pro - Treino & Evolução",
    page_icon="🏋️‍♂️",  # Ícone visual de treino
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeção de Meta Tags para PWA / Web Clip no Celular (Ícone na Tela Inicial)
pwa_html = """
<head>
    <link rel="apple-touch-icon" sizes="180x180" href="https://img.icons8.com/color/180/running-fit.png">
    <link rel="icon" type="image/png" sizes="32x32" href="https://img.icons8.com/color/32/running-fit.png">
    <meta name="apple-mobile-web-app-title" content="TAF Treinos">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
</head>
"""
st.markdown(pwa_html, unsafe_allow_html=True)

DATA_FILE = "taf_user_data.json"

# -----------------------------------------------------------------------------
# 1. FUNÇÕES DE PERSISTÊNCIA DE DADOS (JSON LOCAL)
# -----------------------------------------------------------------------------
def load_all_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_all_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_data(username):
    all_data = load_all_data()
    return all_data.get(username.lower().strip(), None)

def save_user_data(username, user_payload):
    all_data = load_all_data()
    all_data[username.lower().strip()] = user_payload
    save_all_data(all_data)

# -----------------------------------------------------------------------------
# ESTRUTURA INICIAL DO PLANO PADRÃO DO TAF
# -----------------------------------------------------------------------------
def generate_default_weekly_plan():
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
                    {"nome": "Prancha Abdominal", "series": 3, "reps": "1 minuto", "detalhes": "Core firme"}
                ]
            },
            {
                "id": 2,
                "dia_nome": "Dia 2 - Corrida de Resistência (12 min)",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento / Mobilidade", "series": 1, "reps": "10 min", "detalhes": "Trotar leve + educativos"},
                    {"nome": "Simulado Corrida 12 min", "series": 1, "reps": "12 minutos", "detalhes": "Manter ritmo alvo (ex: 2400m+)"},
                    {"nome": "Caminhada Regenerativa", "series": 1, "reps": "5 min", "detalhes": "Desaceleração"}
                ]
            },
            {
                "id": 3,
                "dia_nome": "Dia 3 - Potência de Membros Inferiores & Core",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Agachamento Livre", "series": 4, "reps": "25 repetições", "detalhes": "Sem peso ou leve"},
                    {"nome": "Salto Horizontal (Impulso)", "series": 5, "reps": "3 saltos máximos", "detalhes": "Medir distância"},
                    {"nome": "Abdominal Supra", "series": 4, "reps": "35 repetições", "detalhes": "Soltar ar na subida"}
                ]
            },
            {
                "id": 4,
                "dia_nome": "Dia 4 - Intervalado / Tiros de Velocidade",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento Ativo", "series": 1, "reps": "8 min", "detalhes": "Trote leve"},
                    {"nome": "Tiros de 400 metros", "series": 5, "reps": "400m cada", "detalhes": "Descanso 2 min entre tiros"},
                    {"nome": "Trote Final", "series": 1, "reps": "5 min", "detalhes": "Recuperação"}
                ]
            },
            {
                "id": 5,
                "dia_nome": "Dia 5 - Simulado Completo TAF",
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {"nome": "Barra Fixa", "series": 1, "reps": "Máx em 1 min", "detalhes": "Padrão edital"},
                    {"nome": "Abdominal Remador", "series": 1, "reps": "Máx em 1 min", "detalhes": "Padrão edital"},
                    {"nome": "Flexão de Braço", "series": 1, "reps": "Máx em 1 min", "detalhes": "Padrão edital"},
                    {"nome": "Corrida 12 min", "series": 1, "reps": "12 minutos", "detalhes": "Anotar metragem final"}
                ]
            }
        ]
    }

# Initialize Session State Variables
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}
if "plano_semanal" not in st.session_state:
    st.session_state.plano_semanal = None
if "historico_evolucoes" not in st.session_state:
    st.session_state.historico_evolucoes = []
if "chat_ia_mensagens" not in st.session_state:
    st.session_state.chat_ia_mensagens = [
        {"role": "assistant", "content": "Olá! Sou seu Assistente TAF IA. Posso incorporar novos mini-circuitos, adaptar cargas ou tirar dúvidas sem alterar a estrutura básica do seu plano semanal!"}
    ]

# -----------------------------------------------------------------------------
# BARRA LATERAL - IDENTIFICAÇÃO E CARREGAMENTO DE DADOS (PONTO 1)
# -----------------------------------------------------------------------------
st.sidebar.title("🏋️‍♂️ TAF Pro - Login & Perfil")
input_nome = st.sidebar.text_input("Digite seu Nome/Matrícula:", value=st.session_state.user_name)

if st.sidebar.button("📂 Carregar Meus Dados Salvos"):
    if input_nome.strip():
        dados = get_user_data(input_nome)
        if dados:
            st.session_state.user_name = input_nome.strip()
            st.session_state.user_profile = dados.get("perfil", {})
            st.session_state.plano_semanal = dados.get("plano_semanal", None)
            st.session_state.historico_evolucoes = dados.get("historico_evolucoes", [])
            st.session_state.chat_ia_mensagens = dados.get("chat_ia", st.session_state.chat_ia_mensagens)
            st.sidebar.success(f"Dados e Plano Semanal de {input_nome} carregados com sucesso!")
        else:
            st.sidebar.warning("Usuário não encontrado. Um novo perfil será criado ao salvar.")
            st.session_state.user_name = input_nome.strip()
    else:
        st.sidebar.error("Por favor, digite seu nome.")

if st.sidebar.button("💾 Salvar Estado Atual"):
    if st.session_state.user_name:
        payload = {
            "perfil": st.session_state.user_profile,
            "plano_semanal": st.session_state.plano_semanal,
            "historico_evolucoes": st.session_state.historico_evolucoes,
            "chat_ia": st.session_state.chat_ia_mensagens
        }
        save_user_data(st.session_state.user_name, payload)
        st.sidebar.success("Tudo salvo com sucesso no banco de dados local!")
    else:
        st.sidebar.error("Identifique-se primeiro.")

st.sidebar.markdown("---")
st.sidebar.caption("App TAF v2.5 - Otimizado para PWA & Mobile")

# -----------------------------------------------------------------------------
# NAVEGAÇÃO PRINCIPAL EM ABAS
# -----------------------------------------------------------------------------
st.title("🛡️ Central de Preparação Física TAF")

aba_treino, aba_plano, aba_ia, aba_evolucao, aba_sugestoes = st.tabs([
    "🎯 Treino de Hoje (Diário)",
    "📅 Cronograma Semanal",
    "🤖 IA Assistente",
    "📊 Minha Evolução",
    "💡 Sugestões & Dicas"
])

# -----------------------------------------------------------------------------
# ABA 1: REGISTRO DIÁRIO & AVANÇO AUTOMÁTICO DO CICLO (PONTO 2)
# -----------------------------------------------------------------------------
with aba_treino:
    st.header("🎯 Treino de Hoje & Progresso do Ciclo")
    
    if not st.session_state.plano_semanal:
        st.info("Nenhum plano ativo encontrado. Vá até a aba 'Cronograma Semanal' para criar ou carregar seu plano.")
    else:
        plano = st.session_state.plano_semanal
        treinos = plano.get("treinos", [])
        
        # Encontrar o primeiro treino pendente
        treino_pendente = None
        index_pendente = -1
        for idx, t in enumerate(treinos):
            if not t.get("concluido", False):
                treino_pendente = t
                index_pendente = idx
                break
        
        if treino_pendente is None:
            st.balloons()
            st.success("🎉 Parabéns! Você concluiu TODO o cronograma desta semana!")
            st.markdown("Você agora está liberado para gerar um novo plano para a próxima semana.")
            if st.button("🔄 Reiniciar Ciclo / Gerar Novo Plano Semanal"):
                novo_plano = generate_default_weekly_plan()
                novo_plano["ciclo_id"] = plano.get("ciclo_id", 1) + 1
                st.session_state.plano_semanal = novo_plano
                if st.session_state.user_name:
                    save_user_data(st.session_state.user_name, {
                        "perfil": st.session_state.user_profile,
                        "plano_semanal": st.session_state.plano_semanal,
                        "historico_evolucoes": st.session_state.historico_evolucoes,
                        "chat_ia": st.session_state.chat_ia_mensagens
                    })
                st.rerun()
        else:
            st.subheader(f"📌 {treino_pendente['dia_nome']} (Pendente)")
            st.caption("Atenção: O próximo treino só será liberado após o registro de conclusão deste treino.")
            
            st.markdown("### Exercícios Previstos:")
            for item in treino_pendente["exercicios"]:
                col1, col2, col3 = st.columns([2, 1, 2])
                col1.markdown(f"**{item['nome']}**")
                col2.markdown(f"`{item['series']}x {item['reps']}`")
                col3.caption(f"ℹ️ {item['detalhes']}")
            
            st.markdown("---")
            st.markdown("### 📝 Registrar Desempenho e Concluir Treino")
            
            with st.form("form_registro_treino"):
                rpe = st.slider("Nível de Esforço Percebido (RPE 1-10):", 1, 10, 7)
                corrida_m = st.number_input("Metragem percorrida na corrida (se houver):", min_value=0, max_value=5000, value=2400, step=50)
                barras = st.number_input("Repetições de Barra / Isometria (s):", min_value=0, max_value=100, value=10)
                flexoes = st.number_input("Repetições de Flexão:", min_value=0, max_value=200, value=30)
                obs = st.text_area("Observações sobre o treino (ex: tempo em mini-circuito, dores, sensações):")
                
                marcar_concluido = st.checkbox("✅ Marcar este treino como REALIZADO e avançar o circuito", value=False)
                
                btn_salvar = st.form_submit_button("💾 Salvar Registro de Hoje")
                
                if btn_salvar:
                    if marcar_concluido:
                        # Atualizar estado do treino
                        st.session_state.plano_semanal["treinos"][index_pendente]["concluido"] = True
                        st.session_state.plano_semanal["treinos"][index_pendente]["data_conclusao"] = str(datetime.date.today())
                        
                        # Salvar no histórico de evolução (Ponto 4)
                        registro_hist = {
                            "data": str(datetime.date.today()),
                            "treino": treino_pendente["dia_nome"],
                            "rpe": rpe,
                            "corrida_m": corrida_m,
                            "barras": barras,
                            "flexoes": flexoes,
                            "obs": obs
                        }
                        st.session_state.historico_evolucoes.append(registro_hist)
                        
                        # Auto-salvar no JSON
                        if st.session_state.user_name:
                            save_user_data(st.session_state.user_name, {
                                "perfil": st.session_state.user_profile,
                                "plano_semanal": st.session_state.plano_semanal,
                                "historico_evolucoes": st.session_state.historico_evolucoes,
                                "chat_ia": st.session_state.chat_ia_mensagens
                            })
                        
                        st.success("🎉 Treino marcado como REALIZADO! O próximo treino do circuito já está disponível.")
                        st.rerun()
                    else:
                        st.warning("Registro salvo como rascunho. O treino permanece pendente até marcar o checkbox de realização.")

# -----------------------------------------------------------------------------
# ABA 2: VISUALIZAÇÃO DO CRONOGRAMA SEMANAL E PERSISTÊNCIA
# -----------------------------------------------------------------------------
with aba_plano:
    st.header("📅 Plano Semanal Salvo")
    
    if st.session_state.plano_semanal is None:
        st.warning("Nenhum plano semanal encontrado.")
        if st.button("➕ Gerar Novo Plano Semanal Padrão TAF"):
            st.session_state.plano_semanal = generate_default_weekly_plan()
            if st.session_state.user_name:
                save_user_data(st.session_state.user_name, {
                    "perfil": st.session_state.user_profile,
                    "plano_semanal": st.session_state.plano_semanal,
                    "historico_evolucoes": st.session_state.historico_evolucoes,
                    "chat_ia": st.session_state.chat_ia_mensagens
                })
            st.rerun()
    else:
        plano = st.session_state.plano_semanal
        st.info(f"Ciclo Ativo nº {plano.get('ciclo_id', 1)} | Criado em: {plano.get('criado_em')}")
        
        for t in plano["treinos"]:
            status_icon = "✅ (Concluído)" if t.get("concluido") else "⏳ (Pendente)"
            with st.expander(f"{t['dia_nome']} — {status_icon}"):
                if t.get("data_conclusao"):
                    st.caption(f"Realizado em: {t['data_conclusao']}")
                df_ex = pd.DataFrame(t["exercicios"])
                st.table(df_ex)

# -----------------------------------------------------------------------------
# ABA 3: CHAT DE INTERAÇÃO COM A IA (PONTO 3)
# -----------------------------------------------------------------------------
with aba_ia:
    st.header("🤖 Assistente Virtual & Personalização de Treinos")
    st.markdown("""
    Use esta aba para tirar dúvidas ou **solicitar a adição de novos elementos ao seu treino** (ex: mini-circuitos, corridas cronometradas, abdominais extras) sem alterar o plano semanal mestre.
    """)
    
    # Exibir histórico de chat
    for msg in st.session_state.chat_ia_mensagens:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
    # Entrada do Usuário
    user_prompt = st.chat_input("Ex: Adicionar um mini-circuito de corrida + barra no treino de amanhã...")
    if user_prompt:
        st.session_state.chat_ia_mensagens.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.write(user_prompt)
            
        # Lógica simulada de resposta inteligente da IA para incorporar ao treino
        resposta_ia = ""
        prompt_lower = user_prompt.lower()
        
        if "circuito" in prompt_lower or "mini" in prompt_lower or "barra" in prompt_lower or "corrida" in prompt_lower:
            resposta_ia = (
                "Excelente ideia! Adicionei como um **Bloco Extra de Rendimento** ao seu treino atual. "
                "Recomendo a seguinte estrutura:

"
                "- **Mini-Circuito TAF (3 a 5 Voltas por tempo):**
"
                "  1. 400m Corrida em ritmo forte
"
                "  2. 15 Abdominais Remadores
"
                "  3. 8 Barras Fixas Pronadas

"
                "⏱️ *Dica:* Cronometre o tempo total de todas as voltas e anote o número de repetições na aba de 'Treino de Hoje' para acompanhar a evolução do rendimento ao longo do tempo!"
            )
            # Opcional: injetar no treino pendente atual sem apagar o restante
            if st.session_state.plano_semanal:
                treinos = st.session_state.plano_semanal["treinos"]
                for t in treinos:
                    if not t.get("concluido"):
                        t["exercicios"].append({
                            "nome": "🔥 Mini-Circuito Adaptativo (IA)",
                            "series": 3,
                            "reps": "Cronometrado",
                            "detalhes": "400m corrida + 15 abdominais + 8 barras"
                        })
                        break
        else:
            resposta_ia = (
                f"Entendido! Analisei seu pedido ('{user_prompt}'). "
                "Ajustei as recomendações de recuperação e volume sem alterar a estrutura global do seu cronograma semanal."
            )
            
        st.session_state.chat_ia_mensagens.append({"role": "assistant", "content": resposta_ia})
        with st.chat_message("assistant"):
            st.write(resposta_ia)
            
        if st.session_state.user_name:
            save_user_data(st.session_state.user_name, {
                "perfil": st.session_state.user_profile,
                "plano_semanal": st.session_state.plano_semanal,
                "historico_evolucoes": st.session_state.historico_evolucoes,
                "chat_ia": st.session_state.chat_ia_mensagens
            })

# -----------------------------------------------------------------------------
# ABA 4: HISTÓRICO E GRÁFICOS DE EVOLUÇÃO (PONTO 4)
# -----------------------------------------------------------------------------
with aba_evolucao:
    st.header("📊 Evolução Detalhada (Dia a Dia, Semana a Semana)")
    
    if not st.session_state.historico_evolucoes:
        st.info("Nenhum histórico de treino registrado ainda. Realize os treinos na aba 'Treino de Hoje' para visualizar seus gráficos de evolução.")
    else:
        df_hist = pd.DataFrame(st.session_state.historico_evolucoes)
        df_hist["data"] = pd.to_datetime(df_hist["data"])
        
        st.subheader("📈 Progresso na Corrida dos 12 minutos (Metros)")
        fig_corrida = px.line(df_hist, x="data", y="corrida_m", markers=True, title="Evolução de Distância Percorrida (m)")
        fig_corrida.add_hline(y=2400, line_dash="dash", line_color="green", annotation_text="Meta TAF Padrão (2400m)")
        st.plotly_chart(fig_corrida, use_container_width=True)
        
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.subheader("💪 Evolução na Barra Fixa")
            fig_barras = px.bar(df_hist, x="data", y="barras", title="Repetições de Barra", color_discrete_sequence=["#2b5c8f"])
            st.plotly_chart(fig_barras, use_container_width=True)
            
        with col_g2:
            st.subheader("🤸 Evolução nas Flexões")
            fig_flex = px.bar(df_hist, x="data", y="flexoes", title="Repetições de Flexão", color_discrete_sequence=["#e67e22"])
            st.plotly_chart(fig_flex, use_container_width=True)
            
        st.subheader("📋 Tabela Completa de Histórico")
        st.dataframe(df_hist.sort_values(by="data", ascending=False), use_container_width=True)

# -----------------------------------------------------------------------------
# ABA 5: SUGESTÕES & MELHORES PRÁTICAS DA INTERNET (PONTO 5)
# -----------------------------------------------------------------------------
with aba_sugestoes:
    st.header("💡 Melhores Práticas & Sugestões de Mercado")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        ### 🏆 Recursos de Destaque dos Melhores Apps TAF:
        1. **Simulador de Pontuação por Edital:**
           - Cálculo automático de pontos de acordo com a tabela da banca (Cespe, FGV, Vunesp, Exército, Marinha, etc.).
        2. **Cronômetro Regressivo com Alerta Sonoro:**
           - Sinal sonoro aos 12 minutos de corrida ou aos 60 segundos de abdominal.
        3. **Modo Conexão Offline:**
           - Permitir salvar o treino em PDF ou cache PWA para áreas sem sinal de internet (como pistas de atletismo).
        """)
    with col2:
        st.markdown("""
        ### 🎯 Estratégia de Perceptibilidade de Esforço (RPE):
        - Monitorar a carga interna (RPE) evita **overtraining** ou cansaço excessivo na semana do teste real.
        - **Integração de Vídeos de Técnica:**
           - Adicionar links curtos para a execução correta da barra sem "kipping" ou da flexão com ângulo correto.
        """)
