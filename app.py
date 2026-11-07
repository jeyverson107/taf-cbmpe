import os
import streamlit as st
import streamlit.components.v1 as components
import json
import base64
import requests
import datetime
import hashlib
import hmac
import secrets as pysecrets
import re
import unicodedata
import pandas as pd
import plotly.express as px
import pypdf
from google import genai

# =============================================================================
# CONFIGURAÇÃO DE PÁGINA E ÍCONE PWA/MOBILE
# =============================================================================
st.set_page_config(
    page_title="TAF Pro - Treino & Evolução",
    page_icon=os.path.join(os.path.dirname(os.path.abspath(__file__)), "icone.png"),
    layout="wide",
    initial_sidebar_state="auto",  # no celular começa fechada (o login fica no meio da tela)
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

# Repositório do CÓDIGO (público). Os editais (informação pública) ficam aqui.
CODE_REPO = "jeyverson107/taf-cbmpe"
# Repositório dos DADOS PESSOAIS (deve ser PRIVADO). Enquanto o secret
# DATA_REPO não for configurado, o app continua usando o repositório público,
# exatamente como antes — nada quebra. Quando DATA_REPO for configurado, cada
# perfil é copiado automaticamente do público para o privado no 1º acesso.
DATA_REPO = st.secrets.get("DATA_REPO", CODE_REPO)

# Nome do modelo da IA. Pode ser trocado pelo secret GEMINI_MODEL, sem mexer
# no código. Confira o nome válido em https://ai.google.dev/gemini-api/docs/models
GEMINI_MODEL = st.secrets.get("GEMINI_MODEL", "gemini-3.6-flash")

# Cronômetro por exercício (componente próprio, em componentes/cronometro/index.html).
# Ele devolve o resultado para o app quando você toca em "Finalizar".
_cronometro_componente = components.declare_component(
    "cronometro_taf", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "componentes", "cronometro")
)

TIPOS_EXERCICIO = ["forca", "isometria", "corrida", "tempo", "cronometrado", "distancia"]
TIPOS_EXERCICIO_DESC = {
    "forca": "séries x repetições",
    "isometria": "sustentação em segundos por série (prancha, barra isométrica)",
    "corrida": "distância + tempo",
    "tempo": "duração livre (aquecimento, caminhada, mobilidade)",
    "cronometrado": "tempo cronometrado (ex.: shuttle run, isometria)",
    "distancia": "distância/marca em metros (ex.: salto)",
}

# =============================================================================
# EDITAL CBMPE 2026 — índices transcritos do Edital de Abertura 002/2026
# (DOE-PE de 29/09/2026), item 14, Tabelas 14.1 (masculino) e 14.2 (feminino).
# Tempos em SEGUNDOS, distâncias em METROS.
# =============================================================================
NOME_EDITAL_2026 = "CBMPE 2026"
PROVAS_CBMPE_2026 = [
    {
        "id": "barra_dinamica", "nome": "Barra fixa – flexão e extensão (dinâmico)", "sexo": "M",
        "tipo_medida": "repeticoes", "melhor": "maior", "meta_masc": 8, "meta_fem": None,
        "dia_prova": 1, "tentativas": 1, "natacao": False,
        "observacao": "Pegada pronada, queixo acima da barra, extensão total dos cotovelos. Proibido kipping/balanço, "
                      "parar para descansar ou usar luva/magnésio (item 14.9).",
    },
    {
        "id": "barra_isometria", "nome": "Barra fixa – suspensão em isometria (estático)", "sexo": "F",
        "tipo_medida": "tempo", "melhor": "maior", "meta_masc": None, "meta_fem": 22,
        "dia_prova": 1, "tentativas": 1, "natacao": False,
        "observacao": "Queixo acima da barra sem apoiar, corpo retesado (item 14.10).",
    },
    {
        "id": "natacao_100m", "nome": "Natação 100 m", "sexo": "ambos",
        "tipo_medida": "tempo", "melhor": "menor", "meta_masc": 110, "meta_fem": 120,
        "dia_prova": 1, "tentativas": 1, "natacao": True,
        "observacao": "Qualquer estilo; não pode parar, apoiar na borda/raia nem tocar o fundo (item 14.15).",
    },
    {
        "id": "flexao_abdominal", "nome": "Flexão abdominal em 1 minuto", "sexo": "ambos",
        "tipo_medida": "repeticoes", "melhor": "maior", "meta_masc": 45, "meta_fem": 40,
        "dia_prova": 2, "tentativas": 1, "natacao": False,
        "observacao": "NÃO é o abdominal remador. Deitado de costas, joelhos a ~45º, pés paralelos (abertura do quadril) e "
                      "pés/joelhos SEGUROS por um avaliador; antebraços cruzados no peito com as mãos nos ombros o tempo todo. "
                      "Sobe até os cotovelos tocarem a coxa (entre o meio da coxa e o joelho) e desce até a parte inferior das "
                      "escápulas tocar o solo. Pausas permitidas dentro do 1 minuto; 1 tentativa (item 14.11).",
    },
    {
        "id": "salto_horizontal", "nome": "Salto horizontal (parado)", "sexo": "ambos",
        "tipo_medida": "distancia", "melhor": "maior", "meta_masc": 1.70, "meta_fem": 1.30,
        "dia_prova": 2, "tentativas": 2, "natacao": False,
        "observacao": "Pés paralelos atrás da linha, saída simultânea dos pés; vale a marca mais próxima da linha. "
                      "2 tentativas com 5 min de intervalo (item 14.12).",
    },
    {
        "id": "shuttle_run", "nome": "Shuttle run", "sexo": "ambos",
        "tipo_medida": "tempo", "melhor": "menor", "meta_masc": 11.40, "meta_fem": 13.40,
        "dia_prova": 2, "tentativas": 2, "natacao": False,
        "observacao": "Blocos a 9,14 m; colocar (não jogar) o bloco além da linha. 2 tentativas (item 14.13).",
    },
    {
        "id": "corrida_2400m", "nome": "Corrida de 2.400 m", "sexo": "ambos",
        "tipo_medida": "tempo", "melhor": "menor", "meta_masc": 756, "meta_fem": 889,
        "dia_prova": 2, "tentativas": 1, "natacao": False,
        "observacao": "Pode caminhar, mas NÃO pode parar nem sair da pista — parar reprova (item 14.14).",
    },
]
DESCRICAO_TAF_2026 = (
    "Edital de Abertura 002/2026 (CBMPE, Instituto AOCP), item 14. Exames de Aptidão Física eliminatórios "
    "para TODOS os cargos, em 2 dias consecutivos. Dia 1: barra fixa e natação. Dia 2: flexão abdominal, "
    "salto horizontal e corrida de 2.400 m (shuttle run consta da tabela de índices). "
    "Masculino: barra dinâmica mín. 8 reps; flexão abdominal mín. 45 em 1 min; salto horizontal mín. 1,70 m; "
    "shuttle run máx. 11,40 s; corrida 2.400 m máx. 12'36\"; natação 100 m máx. 1'50\". "
    "Feminino: barra isometria mín. 22 s; flexão abdominal mín. 40 em 1 min; salto mín. 1,30 m; "
    "shuttle run máx. 13,40 s; corrida 2.400 m máx. 14'49\"; natação 100 m máx. 2'00\". "
    "Exige atestado de cardiologista (com RQE) emitido nos 30 dias anteriores aos testes (item 14.4, c)."
)
EDITAL_CBMPE_2026 = {
    "_meta": {
        "criado_por": "jeyverson",
        "criado_em": "2026-10-29T09:00:00",
        "atualizado_por": "jeyverson",
        "atualizado_em": "2026-10-29T09:00:00",
        "arquivo_origem": "CBMPE2027.pdf (Edital de Abertura 002/2026 – DOE-PE 29/09/2026)",
    },
    "cargos": {
        "2º Tenente QOC (CFO)": DESCRICAO_TAF_2026,
        "Soldado QBMG": DESCRICAO_TAF_2026,
    },
    "provas": PROVAS_CBMPE_2026,
}
REGRAS_IMPORTANTES_2026 = [
    "Leve **atestado de cardiologista com RQE**, emitido nos **30 dias** anteriores aos testes, conforme o modelo do Anexo III (item 14.4, c). Sem ele você é eliminado.",
    "Não há segunda chamada. Se você se lesionar e não puder continuar durante o teste, é eliminado (itens 14.1.3 e 14.7.1). **Treinar sem se machucar é parte da prova.**",
    "**Corrida de 2.400 m:** pode caminhar, mas **não pode parar**. O relógio/GPS não vale como resultado oficial (item 14.14).",
    "**Barra:** 1 única tentativa, sem kipping, sem balanço e sem pausas para descansar (item 14.9).",
    "**Abdominal:** NÃO é o remador. É a flexão abdominal com braços cruzados no peito, mãos nos ombros e pés seguros pelo avaliador; os cotovelos tocam a coxa e as escápulas voltam ao solo (item 14.11).",
    "**Salto e shuttle run:** 2 tentativas, com 5 minutos de intervalo; vale a melhor (itens 14.12 e 14.13).",
    "**Atenção:** o item 14.3 cita \"flexão de braços\" e \"corrida de 50 metros\", mas a tabela de índices (14.1/14.2) traz barra fixa e shuttle run. Vale acompanhar retificações do edital.",
]


# =============================================================================
# HELPERS GERAIS
# =============================================================================
def normalizar_usuario(nome: str) -> str:
    """Converte o nome digitado em um identificador seguro para nome de arquivo."""
    nome = (nome or "").strip().lower()
    nome = re.sub(r"\s+", "_", nome)
    nome = re.sub(r"[^a-z0-9_\-]", "", nome)
    return nome


def sem_acento(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in txt if not unicodedata.combining(c)).lower()


def slug(txt: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", sem_acento(txt)).strip("_")
    return s or "prova"


def agora_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def fmt_tempo(seg) -> str:
    """Formata segundos: 11.4 -> 11,40 s ; 756 -> 12'36\" """
    if seg is None or pd.isna(seg):
        return "—"
    seg = float(seg)
    if seg < 60:
        return f"{seg:.2f} s".replace(".", ",") if seg != int(seg) else f"{int(seg)} s"
    m, s = divmod(round(seg), 60)
    return f"{m}'{s:02d}\""


def parse_tempo(texto):
    """Aceita '12:36', "12'36", '12m36', '1:50', '11.40', '11,40', '22'. Retorna segundos (float) ou None."""
    if texto is None:
        return None
    t = str(texto).strip().replace(",", ".").replace("”", "").replace('"', "").replace("''", "")
    if not t:
        return None
    m = re.match(r"^(\d+)\s*[:'m´`]\s*(\d{1,2}(?:\.\d+)?)\s*s?$", t)
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*s?$", t)
    if m:
        return float(m.group(1))
    return None


def parse_numero(texto):
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return None if pd.isna(texto) else float(texto)
    t = str(texto).strip().replace(",", ".")
    t = re.sub(r"[^0-9.]", "", t)
    try:
        return float(t) if t else None
    except ValueError:
        return None


def fmt_valor(prova, v) -> str:
    if v is None or pd.isna(v):
        return "—"
    if prova.get("tipo_medida") == "tempo":
        return fmt_tempo(v)
    if prova.get("tipo_medida") == "distancia":
        return f"{float(v):.2f} m".replace(".", ",")
    return f"{int(round(float(v)))} reps"


def parse_valor(prova, texto):
    return parse_tempo(texto) if prova.get("tipo_medida") == "tempo" else parse_numero(texto)


# -----------------------------------------------------------------------
# REGISTRO DETALHADO (07/11/2026): reps/segundos por série, execução e sensação
# -----------------------------------------------------------------------
STATUS_OPCOES = {"feito": "✅ Fiz", "parcial": "🟡 Parcial", "nao_fez": "❌ Não fiz"}
SENSACAO_OPCOES = {"facil": "😌 Fácil", "ok": "🙂 Ok", "dificil": "😣 Difícil"}
CAMPOS_DE_DADOS = ("reps_series", "seg_series", "reps_realizadas", "distancia_m", "tempo_seg", "duracao_min", "valor_m", "valor")


def tipo_registro(ex):
    """Tipo usado no registro. Exercícios de 'força' medidos em segundos (prancha,
    barra isométrica...) viram 'isometria' para anotar segundos, não repetições."""
    t = ex.get("tipo") or "forca"
    if t == "forca" and not ex.get("reps_series"):
        n = sem_acento(ex.get("nome", ""))
        r = sem_acento(str(ex.get("reps", "")))
        if any(k in n for k in ("prancha", "isometr", "sustenta")) or re.search(r"\d+\s*(s|seg|segundos?)\b", r):
            return "isometria"
    return t


def parse_series(texto, em_segundos=False):
    """'8 7 6 5' -> [8, 7, 6, 5]; em segundos aceita '45 40 1:05'. Retorna (lista, erro)."""
    t = (texto or "").strip()
    if not t:
        return [], None
    partes = [x for x in re.split(r"[\s;/,+\-]+", t) if x]
    valores = []
    for x in partes[:20]:
        if em_segundos:
            v = parse_tempo(x)
            if v is None or v < 0 or v > 3600:
                return None, f"'{x}' não é um tempo válido"
            valores.append(round(v, 1))
        else:
            if not x.isdigit() or int(x) > 500:
                return None, f"'{x}' não é um número de repetições válido"
            valores.append(int(x))
    return valores, None


def tem_dados(ex):
    return any(ex.get(k) not in (None, "", [], 0) for k in CAMPOS_DE_DADOS)


def resumo_series(ex):
    """Texto do resultado de força/isometria (aceita registros antigos)."""
    if ex.get("reps_series"):
        return " · ".join(str(x) for x in ex["reps_series"]) + f" reps (total {sum(ex['reps_series'])})"
    if ex.get("seg_series"):
        return " · ".join(fmt_tempo(x) for x in ex["seg_series"])
    if ex.get("series_realizadas") or ex.get("reps_realizadas"):
        return f"{ex.get('series_realizadas') or '—'} séries · melhor série {ex.get('reps_realizadas') or '—'} reps"
    return "—"


def etiquetas_execucao(ex):
    partes = []
    if ex.get("status"):
        partes.append(STATUS_OPCOES.get(ex["status"], ex["status"]))
    if ex.get("sensacao"):
        partes.append(SENSACAO_OPCOES.get(ex["sensacao"], ex["sensacao"]))
    if ex.get("variacao"):
        partes.append(f"variação: {ex['variacao']}")
    return " · ".join(partes)


def meta_texto(prova, meta):
    return "—" if meta is None else fmt_valor(prova, meta)


# =============================================================================
# PIN (com "sal" e PBKDF2 — muito mais difícil de quebrar que o SHA-256 puro)
# =============================================================================
PIN_ITER = 200_000


def gerar_registro_pin(pin: str) -> dict:
    sal = pysecrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(sal), PIN_ITER).hex()
    return {"sal": sal, "hash": h, "iter": PIN_ITER}


def conferir_pin(pin: str, dados: dict) -> bool:
    reg = dados.get("pin")
    if isinstance(reg, dict) and reg.get("sal") and reg.get("hash"):
        h = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(reg["sal"]), int(reg.get("iter", PIN_ITER))
        ).hex()
        return hmac.compare_digest(h, reg["hash"])
    if dados.get("pin_hash"):  # formato antigo (SHA-256 sem sal)
        return hmac.compare_digest(hashlib.sha256(pin.encode("utf-8")).hexdigest(), dados["pin_hash"])
    return False


def tem_pin(dados: dict) -> bool:
    return bool(dados.get("pin") or dados.get("pin_hash"))


# =============================================================================
# CAMADA DE PERSISTÊNCIA (GITHUB COMO BANCO DE DADOS)
# =============================================================================
def _github_get(path, repo):
    """Lê um arquivo JSON do repositório. Retorna (dados, sha, erro)."""
    if not github_token:
        return None, None, "GITHUB_TOKEN não configurado nos Secrets do Streamlit."
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
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
    return None, None, f"Erro {r.status_code} ao ler {path} em {repo}: {r.text[:200]}"


def _github_put(path, dados, sha, mensagem, repo):
    """Grava um arquivo JSON no repositório. Retorna (novo_sha, aviso_ou_erro)."""
    if not github_token:
        return None, "GITHUB_TOKEN não configurado nos Secrets do Streamlit."
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
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

    if r.status_code in (409, 422):
        # Conflito (outro dispositivo salvou antes): busca a versão mais recente
        # e grava de novo uma vez, avisando o usuário.
        _, sha_atual, erro_leitura = _github_get(path, repo)
        if erro_leitura:
            return None, erro_leitura
        if sha_atual:
            payload["sha"] = sha_atual
        else:
            payload.pop("sha", None)
        try:
            r2 = requests.put(url, headers=headers, json=payload, timeout=15)
        except requests.RequestException as e:
            return None, f"Falha de rede ao salvar {path} após conflito: {e}"
        if r2.status_code in (200, 201):
            return (
                r2.json()["content"]["sha"],
                "Havia uma alteração mais recente salva por outro dispositivo; ela foi sobrescrita por esta gravação.",
            )
        return None, f"Conflito de gravação não resolvido (erro {r2.status_code})."

    return None, f"Erro {r.status_code} ao salvar {path} em {repo}: {r.text[:200]}"


def carregar_dados_github(usuario):
    """Lê o perfil do repositório de dados. Se o repositório privado ainda não
    tiver o perfil, mas o público tiver, COPIA automaticamente (migração).
    Retorna (dados, sha, erro). Se houver erro, NÃO deixa entrar com um perfil
    vazio — isso poderia sobrescrever os dados verdadeiros ao salvar."""
    dados, sha, erro = _github_get(f"dados_{usuario}.json", DATA_REPO)
    if erro:
        return {}, None, erro
    if not dados and DATA_REPO != CODE_REPO:
        antigos, _, erro_pub = _github_get(f"dados_{usuario}.json", CODE_REPO)
        if not erro_pub and antigos:
            novo_sha, msg = _github_put(
                f"dados_{usuario}.json", antigos, None, f"Migra dados de {usuario} para o repositório privado", DATA_REPO
            )
            if novo_sha:
                st.session_state["aviso_migracao"] = True
                return antigos, novo_sha, None
            return {}, None, f"Não consegui copiar seus dados para o repositório privado: {msg}"
    return (dados or {}), sha, None


def salvar_dados_github(usuario, dados, sha=None):
    """Retorna (novo_sha, sucesso: bool)."""
    novo_sha, msg = _github_put(f"dados_{usuario}.json", dados, sha, f"Atualiza dados de {usuario}", DATA_REPO)
    if novo_sha is None:
        st.sidebar.error(f"❌ Falha ao salvar seus dados: {msg}")
        return sha, False
    if msg:
        st.sidebar.warning(f"⚠️ {msg}")
    return novo_sha, True


@st.cache_data(ttl=120, show_spinner=False)
def _ler_editais_cache():
    # Cache de 2 minutos: evita consultar o GitHub a cada clique.
    return _github_get("editais_globais.json", CODE_REPO)


def carregar_editais_globais():
    dados, sha, erro = _ler_editais_cache()
    if erro:
        st.error(f"❌ {erro}")
        dados = {}
    dados = dict(dados or {})
    if NOME_EDITAL_2026 not in dados:
        dados[NOME_EDITAL_2026] = json.loads(json.dumps(EDITAL_CBMPE_2026))
    return dados, sha


def salvar_editais_globais(editais, sha=None):
    novo_sha, msg = _github_put("editais_globais.json", editais, sha, "Atualiza repositório global de editais", CODE_REPO)
    _ler_editais_cache.clear()
    if novo_sha is None:
        st.error(f"❌ Falha ao salvar o repositório de editais: {msg}")
        return sha, False
    if msg:
        st.warning(f"⚠️ {msg}")
    return novo_sha, True


def normalizar_edital(entrada):
    """Garante o formato {'_meta': {...}, 'cargos': {...}, 'provas': [...]}."""
    if isinstance(entrada, dict) and "cargos" in entrada and "_meta" in entrada:
        entrada.setdefault("provas", [])
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
        "provas": [],
    }


# =============================================================================
# PROVAS DO TAF
# =============================================================================
def provas_do_usuario(entrada_edital, sexo, incluir_natacao):
    """Provas que valem para este usuário (filtra por sexo e pela natação)."""
    lista = []
    for p in entrada_edital.get("provas", []) or []:
        alvo = p.get("sexo", "ambos")
        if sexo == "Feminino" and alvo == "M":
            continue
        if sexo == "Masculino" and alvo == "F":
            continue
        if p.get("natacao") and not incluir_natacao:
            continue
        lista.append(p)
    return lista


def meta_para(prova, sexo):
    if sexo == "Feminino":
        return prova.get("meta_fem")
    return prova.get("meta_masc") if prova.get("meta_masc") is not None else prova.get("meta_fem")


def atingiu(prova, valor, meta):
    if valor is None or meta is None:
        return None
    return valor >= meta if prova.get("melhor", "maior") == "maior" else valor <= meta


def inferir_prova_id(nome, tipo, ids_validos):
    """Tenta reconhecer, pelo nome do exercício, se ele é a própria prova do TAF."""
    n = sem_acento(nome)
    candidato = None
    if "shuttle" in n:
        candidato = "shuttle_run"
    elif "salto" in n and "horizontal" in n:
        candidato = "salto_horizontal"
    elif "natac" in n and "100" in n:
        candidato = "natacao_100m"
    elif "flexao abdominal" in n or "abdominal 1 min" in n:
        candidato = "flexao_abdominal"
    elif tipo == "corrida" and ("2400" in n.replace(".", "") or "2,4 km" in n or "2.4 km" in n):
        candidato = "corrida_2400m"
    elif "barra" in n:
        variacoes_assistidas = ["negativa", "excentric", "australiana", "remada", "elastic", "assistid", "banco"]
        if any(v in n for v in variacoes_assistidas):
            candidato = None
        elif "isometr" in n or "suspens" in n:
            candidato = "barra_isometria"
        else:
            candidato = "barra_dinamica"
    return candidato if candidato in ids_validos else None


def valor_do_exercicio(ex, prova):
    """Extrai, de um exercício registrado, o valor que conta para a prova."""
    if ex.get("valor") is not None:  # registro de simulado
        return ex.get("valor")
    medida = prova.get("tipo_medida")
    tipo = ex.get("tipo")
    if medida == "repeticoes":
        v = ex.get("reps_realizadas")
        return v if v else None
    if medida == "tempo":
        if tipo == "corrida":
            dist = ex.get("distancia_m")
            # Só conta como prova se a distância for de fato a da prova (±2%).
            if prova["id"] == "corrida_2400m" and dist and abs(dist - 2400) <= 48:
                return ex.get("tempo_seg") or None
            return None
        return ex.get("tempo_seg") or None
    if medida == "distancia":
        return ex.get("valor_m") or None
    return None


def linhas_por_prova(historico, provas):
    """Monta uma tabela (data, prova_id, valor, origem) a partir do histórico."""
    mapa = {p["id"]: p for p in provas}
    linhas = []
    for item in historico:
        for ex in item.get("exercicios_realizados") or []:
            pid = ex.get("prova_id") or inferir_prova_id(ex.get("nome", ""), ex.get("tipo"), mapa.keys())
            if pid not in mapa:
                continue
            v = valor_do_exercicio(ex, mapa[pid])
            if v is None:
                continue
            linhas.append({
                "data": item.get("data"),
                "prova_id": pid,
                "valor": float(v),
                "origem": "Simulado" if item.get("tipo_registro") == "simulado" else "Treino",
            })
    return pd.DataFrame(linhas, columns=["data", "prova_id", "valor", "origem"])


def descrever_provas_para_ia(provas, sexo):
    if not provas:
        return "Índices oficiais do TAF: não cadastrados (NÃO invente índices)."
    linhas = []
    for p in provas:
        meta = meta_para(p, sexo)
        sentido = "mínimo" if p.get("melhor") == "maior" else "máximo"
        linhas.append(f"- [{p['id']}] {p['nome']}: {sentido} {meta_texto(p, meta)}. {p.get('observacao', '')}")
    return "Provas e índices oficiais do TAF que se aplicam a este aluno:\n" + "\n".join(linhas)


# =============================================================================
# PLANO DE TREINO
# =============================================================================
def plano_padrao():
    """Plano de adaptação usado apenas quando o usuário ainda não gerou um
    treino personalizado. Pensado para quem está saindo do sedentarismo."""
    return {
        "ciclo_id": 1,
        "criado_em": str(datetime.date.today()),
        "gerado_por_ia": False,
        "treinos": [
            {
                "id": 1, "dia_nome": "Dia 1 - Adaptação: força geral + caminhada/trote", "concluido": False, "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento e mobilidade", "series": 1, "reps": "8 min", "detalhes": "Caminhada leve e mobilidade de ombros, quadril e tornozelos", "tipo": "tempo"},
                    {"nome": "Remada australiana (barra baixa)", "series": 3, "reps": "6 a 10", "detalhes": "Corpo alinhado; pare 2 reps antes da falha", "tipo": "forca"},
                    {"nome": "Abdominal (padrão do edital, sem cronômetro)", "series": 3, "reps": "10 a 15", "detalhes": "Cotovelos tocam a coxa, escápulas voltam ao solo", "tipo": "forca"},
                    {"nome": "Caminhada com trotes", "series": 1, "reps": "20 min", "detalhes": "1 min trote / 2 min caminhada", "tipo": "tempo"},
                ],
            },
            {
                "id": 2, "dia_nome": "Dia 2 - Adaptação: pernas, core e explosão leve", "concluido": False, "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento e mobilidade", "series": 1, "reps": "8 min", "detalhes": "Inclua 2x10 polichinelos", "tipo": "tempo"},
                    {"nome": "Agachamento livre", "series": 3, "reps": "10 a 15", "detalhes": "Cadência controlada", "tipo": "forca"},
                    {"nome": "Prancha ventral", "series": 3, "reps": "20 a 30 s", "detalhes": "Coluna neutra", "tipo": "forca"},
                    {"nome": "Saltos verticais leves (educativo)", "series": 3, "reps": "5", "detalhes": "Aterrissagem suave, sem dor nos joelhos", "tipo": "forca"},
                ],
            },
            {
                "id": 3, "dia_nome": "Dia 3 - Adaptação: barra + corrida contínua leve", "concluido": False, "data_conclusao": None,
                "exercicios": [
                    {"nome": "Aquecimento e mobilidade", "series": 1, "reps": "8 min", "detalhes": "Trote leve", "tipo": "tempo"},
                    {"nome": "Barra negativa (com banco)", "series": 3, "reps": "3 a 5", "detalhes": "Descida de 3 a 5 segundos", "tipo": "forca"},
                    {"nome": "Corrida/caminhada contínua", "series": 1, "reps": "20 min", "detalhes": "Ritmo em que dá para conversar. Anote distância e tempo", "tipo": "corrida"},
                ],
            },
        ],
    }


def _extrair_json(txt):
    txt = (txt or "").strip()
    if "```json" in txt:
        txt = txt.split("```json")[1].split("```")[0].strip()
    elif "```" in txt:
        txt = txt.split("```")[1].split("```")[0].strip()
    return json.loads(txt)


def resumo_ciclo_para_ia(historico, ciclo_id):
    itens = [h for h in historico if ciclo_id is not None and h.get("ciclo_id") == ciclo_id] or historico[-6:]
    linhas = []
    for h in itens[-8:]:
        partes = []
        for ex in h.get("exercicios_realizados") or []:
            tags = etiquetas_execucao(ex)
            tags = f" [{tags}]" if tags else ""
            if ex.get("status") == "nao_fez":
                partes.append(f"{ex['nome']}: NÃO FEITO{tags}")
            elif ex.get("tipo") in ("forca", "isometria") and (ex.get("reps_series") or ex.get("seg_series")
                                                                or ex.get("reps_realizadas")):
                partes.append(f"{ex['nome']}: {resumo_series(ex)}{tags}")
            elif ex.get("tipo") == "corrida" and ex.get("distancia_m"):
                txt = f"{ex['nome']}: {ex['distancia_m']}m em {fmt_tempo(ex.get('tempo_seg'))}"
                if ex.get("voltas_seg"):
                    txt += (f" (voltas de {ex.get('pista_m') or '?'} m: "
                            + ", ".join(fmt_tempo(v) for v in ex["voltas_seg"]) + ")")
                partes.append(txt + tags)
            elif ex.get("tipo") in ("cronometrado",) and ex.get("tempo_seg"):
                partes.append(f"{ex['nome']}: {fmt_tempo(ex['tempo_seg'])}")
            elif ex.get("tipo") == "distancia" and ex.get("valor_m"):
                partes.append(f"{ex['nome']}: {ex['valor_m']} m")
            elif ex.get("valor") is not None:
                partes.append(f"{ex['nome']}: {ex['valor']}")
        obs = f" | obs: {h['obs']}" if h.get("obs") else ""
        esforco = f", esforço {h['rpe']}/10" if h.get("rpe") is not None else ""
        linhas.append(f"- {h.get('data')} ({h.get('treino')}){esforco}: " + "; ".join(partes) + obs)
    return "\n".join(linhas) if linhas else "Sem registros ainda."


def gerar_treino_personalizado(edital, cargo, descricao_taf, provas, perfil_fisico, config, historico, ciclo_id,
                               ciclo_resumo=None, medidas=None):
    """Chama a IA para montar o plano do ciclo (semana) `ciclo_id`. Retorna (plano, erro).
    `ciclo_resumo` = semana cujos registros/comentários a IA avalia (padrão: a semana anterior)."""
    if ciclo_resumo is None:
        ciclo_resumo = ciclo_id - 1
    if not api_key:
        return None, "GEMINI_API_KEY não configurada nos Secrets do Streamlit."

    sexo = (perfil_fisico or {}).get("sexo")
    dias = int(config.get("dias_por_semana", 3))
    semanas_restantes = ""
    if config.get("data_taf"):
        try:
            d = datetime.date.fromisoformat(config["data_taf"])
            semanas_restantes = f"Faltam cerca de {max(0, (d - datetime.date.today()).days // 7)} semanas para o TAF."
        except ValueError:
            pass
    natacao = (
        "Pode incluir natação." if config.get("incluir_natacao")
        else "NÃO inclua natação nem treino em piscina nesta fase (decisão do aluno)."
    )
    ids_validos = [p["id"] for p in provas]

    prompt = f"""
    Você é um preparador físico especialista em TAF de concursos militares brasileiros.
    Monte o plano da SEMANA {ciclo_id} de treino, com exatamente {dias} dias de treino.

    Concurso: {edital} — cargo: {cargo}
    {descricao_taf}
    {descrever_provas_para_ia(provas, sexo)}
    {semanas_restantes}

    {descrever_perfil_fisico(perfil_fisico)}
    {descrever_medidas(medidas)}
    Observações do aluno: {config.get('observacoes') or 'nenhuma'}
    {natacao}

    Resultados registrados recentemente (use para calibrar a progressão):
    {resumo_ciclo_para_ia(historico, ciclo_resumo)}

    REGRAS OBRIGATÓRIAS:
    1. Segurança em primeiro lugar: progressão gradual (no máximo ~10% de aumento de volume por semana).
       Se o esforço percebido recente foi alto (8 a 10) ou houve dor relatada, mantenha ou reduza a carga.
       A cada 4ª semana, faça uma semana mais leve (recuperação).
    2. Se o aluno for sedentário/iniciante, priorize adaptação (caminhada/trote intercalado, variações assistidas).
    3. Treine especificamente para as provas acima e use a técnica de execução descrita pelo edital.
    4. NÃO invente índices oficiais. Use apenas os informados acima.
    5. Quando um exercício for a execução da própria prova (teste ou simulado), preencha "prova_id"
       com um destes valores: {ids_validos}. Caso contrário, use null.
    6. Se houver restrições de saúde, adapte os exercícios e indique cautela no campo "detalhes".
    7. ABDOMINAL: a prova do CBMPE NÃO é o abdominal remador. NUNCA prescreva "abdominal remador".
       Treine o movimento da prova (item 14.11): braços cruzados no peito, mãos nos ombros, pés presos
       (parceiro ou apoio firme), cotovelos tocando a coxa e escápulas voltando ao solo. Nas séries comuns,
       chame o exercício de "Abdominal padrão do edital" (prova_id null); só use prova_id "flexao_abdominal"
       no teste de 1 minuto valendo como simulado. Como complemento, pode usar prancha e outros exercícios de core.
    8. Nos registros, cada exercício pode trazer execução (Fiz/Parcial/Não fiz), sensação (Fácil/Ok/Difícil),
       repetições ou segundos de CADA série e a variação usada. Exercício "Fácil" e completo → progrida;
       "Difícil", "Parcial" ou queda grande entre a 1ª e a última série → mantenha ou reduza; "Não fiz" → reavalie.
       Use "isometria" (segundos por série) para prancha e barra isométrica.

    Retorne ESTRITAMENTE um JSON válido (nada fora do JSON), no formato:
    {{"treinos": [{{"dia_nome": "Dia 1 - ...", "exercicios": [
        {{"nome": "...", "series": 3, "reps": "...", "detalhes": "...", "tipo": "forca", "prova_id": null}}
    ]}}]}}
    "tipo" deve ser um de: "forca" (séries/repetições), "isometria" (sustentação em segundos por série:
    prancha, barra isométrica), "corrida" (distância + tempo),
    "tempo" (duração livre: aquecimento, caminhada, mobilidade), "cronometrado" (tempo de uma
    execução: shuttle run, isometria na barra) ou "distancia" (marca em metros: salto horizontal).
    """
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        estrutura = _extrair_json(response.text)
        treinos_ia = estrutura.get("treinos")
        if not isinstance(treinos_ia, list) or not treinos_ia:
            return None, "A IA não retornou treinos em um formato reconhecível."

        treinos_formatados = []
        for t in treinos_ia:
            exercicios = t.get("exercicios") or []
            if not exercicios:
                continue
            treinos_formatados.append({
                "id": len(treinos_formatados) + 1,
                "dia_nome": t.get("dia_nome", f"Dia {len(treinos_formatados) + 1}"),
                "concluido": False,
                "data_conclusao": None,
                "exercicios": [
                    {
                        "nome": ex.get("nome", "Exercício"),
                        "series": ex.get("series", 1),
                        "reps": str(ex.get("reps", "")),
                        "detalhes": ex.get("detalhes", ""),
                        "tipo": ex.get("tipo") if ex.get("tipo") in TIPOS_EXERCICIO else "forca",
                        "prova_id": ex.get("prova_id") if ex.get("prova_id") in ids_validos else None,
                    }
                    for ex in exercicios
                ],
            })
        if not treinos_formatados:
            return None, "A IA retornou uma estrutura sem exercícios válidos."
        return {
            "ciclo_id": ciclo_id,
            "criado_em": str(datetime.date.today()),
            "gerado_por_ia": True,
            "edital_base": edital,
            "cargo_base": cargo,
            "treinos": treinos_formatados,
        }, None
    except json.JSONDecodeError:
        return None, "A IA não retornou um JSON válido. Tente novamente."
    except Exception as e:
        return None, str(e)


def repetir_plano(plano):
    """Cópia do plano atual com tudo desmarcado (usado quando a IA não está disponível)."""
    novo = json.loads(json.dumps(plano))
    novo["ciclo_id"] = plano.get("ciclo_id", 1) + 1
    novo["criado_em"] = str(datetime.date.today())
    for t in novo.get("treinos", []):
        t["concluido"] = False
        t["data_conclusao"] = None
    return novo


def contexto_ia_disponivel(dados):
    """Retorna (edital, cargo, descricao_taf, entrada) se o usuário tiver cargo ativo válido."""
    edital, cargo = dados.get("edital_ativo"), dados.get("cargo_ativo")
    if not (edital and cargo):
        return None
    entrada = normalizar_edital(editais_globais.get(edital, {}))
    descricao = entrada.get("cargos", {}).get(cargo)
    if not descricao:
        return None
    return edital, cargo, descricao, entrada


def avancar_ciclo(dados, usar_ia=True):
    """AUTOMAÇÃO: arquiva o ciclo concluído e monta o próximo, com progressão.
    Retorna uma mensagem para o usuário."""
    plano_atual = dados.get("plano_semanal") or plano_padrao()
    arquivo = dados.setdefault("ciclos_anteriores", [])
    arquivo.append({
        "ciclo_id": plano_atual.get("ciclo_id", 1),
        "criado_em": plano_atual.get("criado_em"),
        "encerrado_em": str(datetime.date.today()),
        "gerado_por_ia": plano_atual.get("gerado_por_ia", False),
        "treinos": [{"dia_nome": t.get("dia_nome"), "data_conclusao": t.get("data_conclusao")} for t in plano_atual.get("treinos", [])],
    })
    dados["ciclos_anteriores"] = arquivo[-26:]
    proximo_id = plano_atual.get("ciclo_id", 1) + 1

    ctx = contexto_ia_disponivel(dados)
    perfil = dados.get("perfil_fisico", {})
    if usar_ia and api_key and ctx and perfil_fisico_completo(perfil):
        edital, cargo, descricao, entrada = ctx
        cfg = dados.get("config_treino", {})
        provas = provas_do_usuario(entrada, perfil.get("sexo"), cfg.get("incluir_natacao", False))
        novo, erro = gerar_treino_personalizado(
            edital, cargo, descricao, provas, perfil, cfg, dados.get("historico_evolucoes", []), proximo_id,
            medidas=dados.get("medidas"),
        )
        if novo:
            dados["plano_semanal"] = novo
            return f"🤖 Semana {proximo_id} montada automaticamente pela IA, com progressão baseada nos seus registros."
        dados["plano_semanal"] = repetir_plano(plano_atual)
        return f"⚠️ A IA não respondeu ({erro}). Repeti a semana anterior como semana {proximo_id}; tente gerar de novo depois."
    dados["plano_semanal"] = repetir_plano(plano_atual)
    return f"🔁 Semana {proximo_id} criada repetindo os mesmos treinos."


# =============================================================================
# PERFIL FÍSICO
# =============================================================================
def perfil_fisico_completo(perfil: dict) -> bool:
    if not perfil:
        return False
    obrigatorios = ["idade", "altura_cm", "peso_kg", "nivel_atividade"]
    return all(perfil.get(c) not in (None, "", 0) for c in obrigatorios)


def descrever_perfil_fisico(perfil: dict) -> str:
    if not perfil:
        return ""
    partes = []
    if perfil.get("idade"):
        partes.append(f"{perfil['idade']} anos")
    if perfil.get("sexo") and perfil["sexo"] != "Prefiro não informar":
        partes.append(f"sexo {perfil['sexo']}")
    if perfil.get("altura_cm") and perfil.get("peso_kg"):
        partes.append(f"{perfil['altura_cm']:.0f}cm e {perfil['peso_kg']:.1f}kg")
    if perfil.get("nivel_atividade"):
        partes.append(f"nível de atividade atual: {perfil['nivel_atividade']}")
    if perfil.get("pratica_corrida"):
        dist = perfil.get("corrida_atual_distancia_m")
        tempo_seg = perfil.get("corrida_atual_tempo_seg")
        if dist and tempo_seg:
            partes.append(f"hoje consegue correr aproximadamente {dist}m em {tempo_seg // 60} min")
        else:
            partes.append("já consegue correr continuamente")
    else:
        partes.append("ainda NÃO consegue correr continuamente sem parar (iniciante em corrida)")
    if perfil.get("restricoes_saude"):
        partes.append(f"restrições/lesões relatadas: {perfil['restricoes_saude']}")
    return "Perfil físico do aluno: " + "; ".join(partes) + "."


def medidas_ordenadas(medidas):
    return sorted([m for m in (medidas or []) if m.get("data")], key=lambda m: m["data"])


def descrever_medidas(medidas) -> str:
    """Resumo das medidas semanais (peso, cintura, FC de repouso) para a IA."""
    ms = medidas_ordenadas(medidas)[-8:]
    if not ms:
        return "Medidas semanais: ainda não registradas."
    linhas = []
    for m in ms:
        partes = []
        if m.get("peso_kg"):
            partes.append(f"peso {m['peso_kg']:.1f} kg")
        if m.get("cintura_cm"):
            partes.append(f"cintura {m['cintura_cm']:.1f} cm")
        if m.get("fc_repouso"):
            partes.append(f"FC de repouso {int(m['fc_repouso'])} bpm")
        if m.get("obs"):
            partes.append(f"obs: {m['obs']}")
        linhas.append(f"- {m['data']}: " + ", ".join(partes))
    return ("Medidas semanais do aluno (da mais antiga para a mais recente). Use como sinal de adaptação "
            "(ex.: FC de repouso subindo + cansaço relatado = sinal para aliviar a carga):\n" + "\n".join(linhas))


# =============================================================================
# MIGRAÇÕES DE DADOS ANTIGOS
# =============================================================================
DETALHE_ABD_EDITAL = (
    "Movimento da prova (item 14.11), NÃO o remador: deitado, joelhos a ~45º, pés presos (parceiro ou apoio firme), "
    "braços cruzados no peito com as mãos nos ombros o tempo todo. Suba até os cotovelos tocarem a coxa e desça até "
    "as escápulas tocarem o chão. Repetição sem esses dois contatos não conta na prova."
)


def corrigir_abdominal_remador(dados):
    """07/11/2026: a prova do CBMPE não usa o abdominal remador. Troca, nos treinos
    AINDA NÃO FEITOS, o remador pelo abdominal do edital. O histórico não é alterado
    (o que você fez foi remador mesmo, e isso não conta como resultado da prova).
    Retorna True se mudou algo."""
    mudou = False
    for t in (dados.get("plano_semanal") or {}).get("treinos", []) or []:
        if t.get("concluido"):
            continue
        for ex in t.get("exercicios", []) or []:
            if "remador" not in sem_acento(ex.get("nome", "")):
                continue
            cronometrado = "cronometr" in sem_acento(ex.get("nome", "")) or "1 min" in sem_acento(str(ex.get("reps", "")))
            ex["nome"] = "Abdominal padrão do edital – séries de 1 minuto" if cronometrado else "Abdominal padrão do edital"
            ex["detalhes"] = DETALHE_ABD_EDITAL + (" Faça o máximo de repetições corretas em cada minuto." if cronometrado else "")
            ex["tipo"] = "forca"
            ex["prova_id"] = None
            mudou = True
    return mudou


def migrar_dados_antigos(dados):
    """Converte o 'diario' do formato antigo para o histórico atual (uma vez)."""
    if dados.get("diario") and not dados.get("diario_migrado"):
        for d in dados["diario"]:
            resultado = sem_acento(str(d.get("Resultado", "")))
            ex = {"nome": d.get("Exercício", "Registro antigo"), "tipo": "tempo", "duracao_min": None}
            m_km = re.search(r"(\d+(?:[.,]\d+)?)\s*km", resultado)
            m_m = re.search(r"(\d+)\s*m(?:etros)?\b", resultado)
            m_min = re.search(r"(\d+)\s*min", resultado)
            dist = float(m_km.group(1).replace(",", ".")) * 1000 if m_km else (float(m_m.group(1)) if m_m else None)
            if dist:
                ex = {"nome": ex["nome"], "tipo": "corrida", "distancia_m": int(dist),
                      "tempo_seg": int(m_min.group(1)) * 60 if m_min else None}
            dados.setdefault("historico_evolucoes", []).append({
                "data": d.get("Data"),
                "treino": "Registro do diário antigo",
                "rpe": d.get("Esforço"),
                "exercicios_realizados": [ex],
                "obs": d.get("Obs", ""),
                "origem": "diario_antigo",
            })
        dados["diario_migrado"] = True
    return dados


# =============================================================================
# LOGIN (05/11/2026): nome e PIN na MESMA tela, com botão "Entrar".
# Fica no meio da tela (no celular a barra lateral vem fechada).
# =============================================================================
st.sidebar.title("🏋️‍♂️ TAF Pro - Perfil")


def _entrar(usuario, dados, sha):
    st.session_state["usuario_logado"] = usuario
    st.session_state["dados"] = dados
    st.session_state["sha"] = sha
    st.query_params["u"] = usuario  # o link já abre com o seu nome preenchido


usuario_input = st.session_state.get("usuario_logado")
if not usuario_input:
    st.title("🛡️ Central TAF Militar & Treinos")
    st.subheader("🔐 Entrar")
    with st.form("form_login"):
        nome_login = st.text_input("Seu nome / login", value=st.query_params.get("u", ""), autocomplete="username")
        pin_login = st.text_input(
            "PIN", type="password", autocomplete="current-password",
            help="Se o seu perfil ainda não tem PIN, deixe em branco e crie um depois de entrar.",
        )
        entrar = st.form_submit_button("➡️ Entrar", type="primary", width="stretch")
    st.caption("Dica: salve nos favoritos o link do app com `?u=seunome` no final para já abrir com o seu nome.")
    if entrar:
        u = normalizar_usuario(nome_login)
        if not u:
            st.error("Digite seu nome/login.")
            st.stop()
        with st.spinner("Abrindo seu perfil..."):
            dados_remotos, sha_remoto, erro_carga = carregar_dados_github(u)
        if erro_carga:
            st.error(f"❌ Não consegui abrir seu perfil agora: {erro_carga}. Tente de novo em instantes.")
            st.stop()
        dados_remotos = migrar_dados_antigos(dados_remotos or {})
        corrigiu_abd = corrigir_abdominal_remador(dados_remotos)
        if tem_pin(dados_remotos):
            if not pin_login:
                st.error("🔒 Este perfil é protegido. Digite o PIN.")
                st.stop()
            if not conferir_pin(pin_login, dados_remotos):
                st.error("PIN incorreto.")
                st.stop()
            if dados_remotos.get("pin_hash"):
                # Atualiza o PIN antigo para o formato seguro, sem pedir nada ao usuário.
                dados_remotos["pin"] = gerar_registro_pin(pin_login)
                dados_remotos.pop("pin_hash", None)
                novo_sha, _ = salvar_dados_github(u, dados_remotos, sha_remoto)
                sha_remoto = novo_sha or sha_remoto
        elif pin_login:
            st.session_state["aviso_sem_pin"] = True
        if corrigiu_abd:
            novo_sha, _ = salvar_dados_github(u, dados_remotos, sha_remoto)
            sha_remoto = novo_sha or sha_remoto
            st.session_state["toast"] = "🔧 O abdominal remador do seu plano foi trocado pelo abdominal do edital."
        _entrar(u, dados_remotos, sha_remoto)
        st.rerun()
    st.stop()

dados_usuario = st.session_state["dados"]

st.sidebar.success(f"👤 Conectado como **{usuario_input}**")
c_rec, c_sair = st.sidebar.columns(2)
if c_rec.button("🔄 Recarregar", help="Busca de novo os seus dados salvos na nuvem"):
    dados_remotos, sha_remoto, erro_carga = carregar_dados_github(usuario_input)
    if erro_carga:
        st.sidebar.error(f"❌ {erro_carga}")
    else:
        st.session_state["dados"] = migrar_dados_antigos(dados_remotos or {})
        corrigir_abdominal_remador(st.session_state["dados"])
        st.session_state["sha"] = sha_remoto
        st.rerun()
if c_sair.button("🚪 Sair"):
    for k in ("usuario_logado", "dados", "sha"):
        st.session_state.pop(k, None)
    st.rerun()


def salvar():
    """Atalho: salva o perfil atual e atualiza o sha. Retorna True/False."""
    novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
    if ok:
        st.session_state["sha"] = novo_sha
    return ok


if st.session_state.pop("aviso_migracao", False):
    st.sidebar.success("🔐 Seus dados foram copiados para o repositório privado.")

# -----------------------------------------------------------------------
# PIN: perfis sem PIN podem criar um aqui.
# Não é um login robusto, mas impede o acesso/edição por engano de outro perfil.
# A proteção real dos dados é o repositório PRIVADO (secret DATA_REPO).
# -----------------------------------------------------------------------
if not tem_pin(dados_usuario):
    if st.session_state.pop("aviso_sem_pin", False):
        st.sidebar.info("O PIN digitado não foi usado: este perfil ainda não tem PIN. Crie um abaixo.")
    st.sidebar.warning("⚠️ Este perfil ainda não tem PIN de proteção.")
    with st.sidebar.form("form_criar_pin"):
        novo_pin = st.text_input("Criar um PIN (mín. 6 dígitos):", type="password", autocomplete="new-password")
        if st.form_submit_button("Definir PIN"):
            if len(novo_pin) >= 6:
                dados_usuario["pin"] = gerar_registro_pin(novo_pin)
                if salvar():
                    st.sidebar.success("PIN definido e salvo!")
                    st.rerun()
            else:
                st.sidebar.error("Use pelo menos 6 dígitos.")

# Estrutura padrão (perfis antigos que só tenham parte dos campos não quebram)
dados_usuario.setdefault("perfil_fisico", {})
dados_usuario.setdefault("edital_ativo", None)
dados_usuario.setdefault("cargo_ativo", None)
dados_usuario.setdefault("plano_semanal", plano_padrao())
dados_usuario.setdefault("historico_evolucoes", [])
dados_usuario.setdefault("medidas", [])
dados_usuario.setdefault("config_treino", {"dias_por_semana": 3, "incluir_natacao": False, "data_taf": None, "observacoes": ""})
dados_usuario.setdefault(
    "chat_ia",
    [{"role": "assistant", "content": "Olá! Sou seu Assistente TAF IA. Posso tirar dúvidas sobre o treino e o edital."}],
)

# -----------------------------------------------------------------------
# PERFIL FÍSICO
# -----------------------------------------------------------------------
perfil_atual = dados_usuario.get("perfil_fisico", {})
perfil_ok = perfil_fisico_completo(perfil_atual)

with st.sidebar.expander("👤 Meu Perfil Físico", expanded=not perfil_ok):
    if not perfil_ok:
        st.warning("Preencha para a IA conseguir montar um treino adequado ao seu nível.")
    st.caption(
        "Estas informações não substituem uma avaliação médica. Consulte um profissional antes de "
        "iniciar qualquer programa de exercícios. O edital exige atestado de cardiologista para o TAF."
    )
    with st.form("form_perfil_fisico"):
        idade = st.number_input("Idade", min_value=14, max_value=90, value=int(perfil_atual.get("idade") or 25))
        opcoes_sexo = ["Prefiro não informar", "Masculino", "Feminino"]
        sexo = st.selectbox(
            "Sexo (o edital tem índices diferentes por sexo)",
            opcoes_sexo,
            index=opcoes_sexo.index(perfil_atual["sexo"]) if perfil_atual.get("sexo") in opcoes_sexo else 0,
        )
        c1, c2 = st.columns(2)
        altura_cm = c1.number_input("Altura (cm)", min_value=100.0, max_value=230.0, value=float(perfil_atual.get("altura_cm") or 170.0), step=1.0)
        peso_kg = c2.number_input("Peso (kg)", min_value=30.0, max_value=250.0, value=float(perfil_atual.get("peso_kg") or 75.0), step=0.5)
        opcoes_nivel = [
            "Sedentário(a) — não pratico exercícios",
            "Iniciante — comecei a treinar há pouco tempo",
            "Intermediário(a) — treino com regularidade",
            "Avançado(a) — treino pesado/frequente",
        ]
        nivel_atividade = st.selectbox(
            "Nível de atividade física atual",
            opcoes_nivel,
            index=opcoes_nivel.index(perfil_atual["nivel_atividade"]) if perfil_atual.get("nivel_atividade") in opcoes_nivel else 0,
        )
        pratica_corrida = st.checkbox("Já consigo correr sem parar por pelo menos alguns minutos", value=perfil_atual.get("pratica_corrida", False))
        c3, c4 = st.columns(2)
        corrida_atual_m = c3.number_input("Se sim, ~quantos metros", min_value=0, value=int(perfil_atual.get("corrida_atual_distancia_m") or 0), step=100)
        corrida_atual_min = c4.number_input("Em ~quantos minutos", min_value=0, value=int((perfil_atual.get("corrida_atual_tempo_seg") or 0) // 60), step=1)
        restricoes = st.text_area("Lesões, dores ou restrições médicas (opcional, mas importante)", value=perfil_atual.get("restricoes_saude", ""))

        if st.form_submit_button("💾 Salvar Perfil Físico"):
            dados_usuario["perfil_fisico"] = {
                "idade": idade, "sexo": sexo, "altura_cm": altura_cm, "peso_kg": peso_kg,
                "nivel_atividade": nivel_atividade, "pratica_corrida": pratica_corrida,
                "corrida_atual_distancia_m": corrida_atual_m or None,
                "corrida_atual_tempo_seg": (corrida_atual_min * 60) if corrida_atual_min else None,
                "restricoes_saude": restricoes.strip(), "atualizado_em": agora_iso(),
            }
            if salvar():
                st.success("Perfil físico salvo!")
                st.rerun()

# -----------------------------------------------------------------------
# PREFERÊNCIAS DE TREINO
# -----------------------------------------------------------------------
cfg = dados_usuario["config_treino"]
with st.sidebar.expander("⚙️ Preferências de Treino"):
    with st.form("form_config"):
        dias_sem = st.slider("Dias de treino por semana", 2, 6, int(cfg.get("dias_por_semana", 3)))
        incluir_natacao = st.checkbox(
            "Incluir natação no plano", value=bool(cfg.get("incluir_natacao", False)),
            help="Deixe desligado enquanto não tiver acesso a piscina. Ligue quando puder treinar natação.",
        )
        tem_data = st.checkbox("Já sei a data do TAF", value=bool(cfg.get("data_taf")))
        data_padrao = datetime.date.fromisoformat(cfg["data_taf"]) if cfg.get("data_taf") else datetime.date.today() + datetime.timedelta(days=180)
        data_taf = st.date_input("Data do TAF", value=data_padrao, format="DD/MM/YYYY")
        observacoes = st.text_area(
            "Observações para a IA (ex.: horários, onde treina, equipamentos)",
            value=cfg.get("observacoes", ""),
        )
        if st.form_submit_button("💾 Salvar Preferências"):
            dados_usuario["config_treino"] = {
                "dias_por_semana": dias_sem, "incluir_natacao": incluir_natacao,
                "data_taf": str(data_taf) if tem_data else None, "observacoes": observacoes.strip(),
            }
            if salvar():
                st.success("Preferências salvas! Elas valem a partir do próximo treino gerado.")
                st.rerun()

# Carrega Editais Globais (com cache)
editais_globais, sha_editais = carregar_editais_globais()
st.session_state["sha_editais"] = sha_editais

if st.sidebar.button("💾 Salvar Tudo na Nuvem"):
    if salvar():
        st.sidebar.success("Tudo salvo com sucesso!")

if dados_usuario.get("edital_ativo") and dados_usuario.get("cargo_ativo"):
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**📌 Concurso Ativo:** {dados_usuario['edital_ativo']}")
    st.sidebar.markdown(f"**🎯 Cargo:** {dados_usuario['cargo_ativo']}")

if DATA_REPO == CODE_REPO:
    st.sidebar.warning(
        "🔓 Seus dados ainda estão no repositório **público**. Configure o secret `DATA_REPO` "
        "com um repositório privado para protegê-los."
    )

# Contexto do edital ativo, usado em várias abas
ctx_ativo = contexto_ia_disponivel(dados_usuario)
sexo_usuario = dados_usuario.get("perfil_fisico", {}).get("sexo")
provas_ativas = provas_do_usuario(ctx_ativo[3], sexo_usuario, cfg.get("incluir_natacao", False)) if ctx_ativo else []
ids_provas = [p["id"] for p in provas_ativas]
nomes_provas = {p["id"]: p["nome"] for p in provas_ativas}

# =============================================================================
# NAVEGAÇÃO PRINCIPAL
# =============================================================================
st.title("🛡️ Central TAF Militar & Treinos")

if cfg.get("data_taf"):
    dias_faltam = (datetime.date.fromisoformat(cfg["data_taf"]) - datetime.date.today()).days
    if dias_faltam >= 0:
        st.caption(f"⏳ Faltam **{dias_faltam} dias** (~{dias_faltam // 7} semanas) para o TAF.")

if ctx_ativo and dados_usuario.get("edital_ativo") != NOME_EDITAL_2026 and NOME_EDITAL_2026 in editais_globais:
    st.info(
        f"ℹ️ Seu concurso ativo é **{dados_usuario['edital_ativo']}**. Os índices oficiais do edital 002/2026 estão em "
        f"**{NOME_EDITAL_2026}** — ative-o na aba '📄 Editais & Cargos'."
    )

# -----------------------------------------------------------------------
# CRONÔMETRO DO TREINO (30/10/2026)
# Roda no próprio celular (JavaScript) e guarda o horário de início no aparelho.
# Por isso NÃO para quando a tela apaga, quando você aperta o botão power,
# sai da página, fecha o navegador ou a internet cai: o tempo é calculado
# pela diferença entre "agora" e o horário em que você tocou em Iniciar.
# -----------------------------------------------------------------------
def cronometro_treino(usuario):
    import streamlit.components.v1 as components
    chave = json.dumps("taf_crono_" + (usuario or "anonimo"))
    components.html("""
<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#31333F">
  <div style="font-weight:600;font-size:17px;margin-bottom:4px">⏱️ Cronômetro do treino</div>
  <div id="t" style="font-size:46px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:1px">00:00</div>
  <div id="st" style="font-size:13px;color:#666;margin:2px 0 8px"></div>
  <div style="display:flex;gap:6px;flex-wrap:wrap">
    <button id="b1" class="b p">▶️ Iniciar</button>
    <button id="b2" class="b">🏁 Volta</button>
    <button id="b3" class="b">🔄 Zerar</button>
  </div>
  <div id="v" style="font-size:14px;margin-top:8px;max-height:110px;overflow:auto"></div>
</div>
<style>
 .b{font-size:16px;padding:9px 14px;border-radius:8px;border:1px solid #ccc;background:#fff;cursor:pointer}
 .p{background:#ff4b4b;color:#fff;border-color:#ff4b4b}
</style>
<script>
const K = %s;
let s;
function ler(){ try { s = JSON.parse(localStorage.getItem(K)) || null; } catch(e) { s = null; }
                if (!s) s = {inicio: null, acum: 0, voltas: []}; }
function gravar(){ try { localStorage.setItem(K, JSON.stringify(s)); } catch(e) {} }
const total = () => s.acum + (s.inicio ? Date.now() - s.inicio : 0);
const p = n => String(n).padStart(2, "0");
function fmt(ms){ const t = Math.floor(ms/1000), h = Math.floor(t/3600), m = Math.floor(t%%3600/60), x = t%%60;
                  return (h ? h + ":" + p(m) : p(m)) + ":" + p(x); }
function desenha(){
  const ms = total();
  document.getElementById("t").textContent = fmt(ms);
  const b1 = document.getElementById("b1");
  b1.textContent = s.inicio ? "⏸️ Pausar" : (ms > 0 ? "▶️ Continuar" : "▶️ Iniciar");
  document.getElementById("st").textContent = s.inicio
    ? "Contando — pode apagar a tela ou guardar o celular: o tempo continua."
    : (ms > 0 ? "Pausado. Anote o tempo no formulário abaixo (" + Math.floor(ms/60000) + " min " + Math.floor(ms/1000)%%60 + " s)." : "Toque em Iniciar quando começar.");
  document.getElementById("v").innerHTML = s.voltas.map((v, i) =>
    "🏁 Volta " + (i+1) + ": <b>" + fmt(v - (i ? s.voltas[i-1] : 0)) + "</b> <span style='color:#888'>(total " + fmt(v) + ")</span>"
  ).reverse().join("<br>");
}
document.getElementById("b1").onclick = () => { ler();
  if (s.inicio) { s.acum += Date.now() - s.inicio; s.inicio = null; } else { s.inicio = Date.now(); }
  gravar(); desenha(); };
document.getElementById("b2").onclick = () => { ler(); if (total() > 0) { s.voltas.push(total()); gravar(); desenha(); } };
document.getElementById("b3").onclick = () => { ler();
  if (total() === 0 || confirm("Zerar o cronômetro?")) { s = {inicio: null, acum: 0, voltas: []}; gravar(); desenha(); } };
ler(); desenha();
setInterval(() => { ler(); desenha(); }, 500);
document.addEventListener("visibilitychange", () => { ler(); desenha(); });
</script>""" % chave, height=270)


# -----------------------------------------------------------------------
# MEDIDAS SEMANAIS (05/11/2026): peso, cintura e frequência cardíaca de repouso
# -----------------------------------------------------------------------
def medida_da_semana_pendente():
    ms = medidas_ordenadas(dados_usuario.get("medidas"))
    if not ms:
        return True
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(ms[-1]["data"])).days >= 7
    except ValueError:
        return True


def form_medidas(sufixo):
    with st.form(f"form_medidas_{sufixo}", clear_on_submit=True):
        st.caption("Meça sempre no mesmo dia da semana, de manhã, antes de comer e depois de ir ao banheiro. "
                   "Preencha só o que você mediu.")
        data_m = st.date_input("Data da medição", value=datetime.date.today(), format="DD/MM/YYYY", key=f"med_data_{sufixo}")
        c1, c2, c3 = st.columns(3)
        peso = c1.number_input("Peso (kg)", min_value=30.0, max_value=250.0, value=None, step=0.1, format="%.1f",
                               key=f"med_peso_{sufixo}")
        cintura = c2.number_input("Cintura (cm)", min_value=40.0, max_value=200.0, value=None, step=0.5, format="%.1f",
                                  key=f"med_cint_{sufixo}",
                                  help="Fita métrica na altura do umbigo, sem apertar, ao final de uma expiração normal.")
        fc = c3.number_input("FC de repouso (bpm)", min_value=30, max_value=150, value=None, step=1, key=f"med_fc_{sufixo}",
                             help="Ao acordar, ainda deitado: conte os batimentos no pulso por 60 segundos (ou use um relógio).")
        obs = st.text_input("Como foi a semana? (sono, dores, cansaço) — opcional", key=f"med_obs_{sufixo}")
        if st.form_submit_button("💾 Salvar medidas", type="primary"):
            if peso is None and cintura is None and fc is None:
                st.warning("Preencha pelo menos uma medida.")
                return
            data_str = str(data_m)
            anterior = next((m for m in dados_usuario["medidas"] if m.get("data") == data_str), {})
            nova = dict(anterior)
            nova["data"] = data_str
            if peso is not None:
                nova["peso_kg"] = round(float(peso), 1)
            if cintura is not None:
                nova["cintura_cm"] = round(float(cintura), 1)
            if fc is not None:
                nova["fc_repouso"] = int(fc)
            if obs.strip():
                nova["obs"] = obs.strip()
            nova["registrado_em"] = agora_iso()
            lista = [m for m in dados_usuario["medidas"] if m.get("data") != data_str] + [nova]
            dados_usuario["medidas"] = medidas_ordenadas(lista)
            # O peso mais recente passa a valer no Perfil Físico (a IA usa esse peso).
            com_peso = [m for m in dados_usuario["medidas"] if m.get("peso_kg")]
            if com_peso:
                dados_usuario.setdefault("perfil_fisico", {})["peso_kg"] = com_peso[-1]["peso_kg"]
            if salvar():
                st.session_state["toast"] = "✅ Medidas salvas!"
                st.rerun()


# -----------------------------------------------------------------------
# CRONÔMETRO POR EXERCÍCIO (05/11/2026)
# Os resultados ficam num "rascunho" salvo na nuvem até você salvar o treino,
# então nada se perde se o app recarregar no meio do treino.
# -----------------------------------------------------------------------
def alvo_corrida(ex):
    """Sugere a meta de distância da corrida a partir do exercício (ex.: '2.400 m')."""
    if ex.get("prova_id") == "corrida_2400m":
        return 2400
    m = re.search(r"(\d{1,2}\.\d{3}|\d{2,5})\s*m\b", f"{ex.get('nome', '')} {ex.get('reps', '')}")
    if m:
        v = int(m.group(1).replace(".", ""))
        return v if 100 <= v <= 20000 else None
    return None


def texto_tempo(seg):
    seg = float(seg)
    if seg < 60:
        return f"{seg:.2f}"
    return f"{int(seg // 60)}:{seg % 60:05.2f}"


def rascunho_atual(ck):
    r = dados_usuario.get("rascunho_treino")
    if not isinstance(r, dict) or r.get("ck") != ck:
        r = {"ck": ck, "resultados": {}, "ids": []}
    return r


def preencher_formulario(ck, i, tipo, res, forcar):
    """Coloca o resultado do cronômetro nos campos do formulário de registro."""
    def setar(k, v):
        if forcar or k not in st.session_state:
            st.session_state[k] = v
    t = res.get("tempo_seg")
    if not t:
        return
    if tipo == "corrida":
        setar(f"dist_{ck}_{i}", int(res["distancia_m"]) if res.get("distancia_m") else None)
        mi, se = divmod(int(round(t)), 60)
        setar(f"min_{ck}_{i}", mi)
        setar(f"seg_{ck}_{i}", se)
    elif tipo == "cronometrado":
        setar(f"crono_{ck}_{i}", texto_tempo(t))
    elif tipo == "tempo":
        setar(f"dur_{ck}_{i}", max(1, int(round(t / 60))))
    elif tipo == "isometria":
        setar(f"rs_{ck}_{i}", " ".join(f"{round(x):d}" for x in (res.get("tentativas_seg") or [t])))


def campos_registro(ex, kp, ini=None, r_crono=None):
    """Desenha os campos de registro de UM exercício (dentro de um st.form).
    `kp` = prefixo único das chaves; `ini` = registro já salvo (modo edição).
    Retorna (resposta, erro)."""
    ini = ini or {}
    r_crono = r_crono or {}
    tipo = tipo_registro(ini or ex)
    prova_id = ini.get("prova_id", ex.get("prova_id"))
    resp = {"nome": ex["nome"], "tipo": tipo, "prova_id": prova_id}
    erro = None

    # Simulado (só aparece ao editar um simulado salvo)
    if ini.get("tipo") == "simulado":
        p = (next((x for x in list(provas_ativas) + PROVAS_CBMPE_2026 if x["id"] == prova_id), None)
             or {"tipo_medida": "repeticoes"})
        v0 = ini.get("valor")
        txt0 = "" if v0 is None else (texto_tempo(v0) if p.get("tipo_medida") == "tempo" else
                                      (f"{v0:g}" if isinstance(v0, (int, float)) else str(v0)))
        txt = st.text_input("Resultado", value=txt0, key=f"sv_{kp}")
        v = parse_valor(p, txt)
        if txt.strip() and v is None:
            erro = f"{ex['nome']}: valor inválido"
        resp.update({"tipo": "simulado", "valor": v})
        return resp, erro

    c1, c2 = st.columns(2)
    status = c1.segmented_control("Execução", list(STATUS_OPCOES), format_func=STATUS_OPCOES.get,
                                  default=ini.get("status"), key=f"st_{kp}")
    sensacao = c2.segmented_control("Como foi", list(SENSACAO_OPCOES), format_func=SENSACAO_OPCOES.get,
                                    default=ini.get("sensacao"), key=f"se_{kp}")

    if tipo in ("forca", "isometria"):
        em_seg = tipo == "isometria"
        lista0 = ini.get("seg_series" if em_seg else "reps_series") or []
        txt0 = " ".join((f"{x:g}" if em_seg else str(x)) for x in lista0)
        alvo = f"alvo {ex.get('series')}x {ex.get('reps')}" if ex.get("reps") else ""
        rotulo = ("Segundos de cada série" if em_seg else "Repetições de cada série") + (f" ({alvo})" if alvo else "")
        txt = st.text_input(rotulo, value=txt0, key=f"rs_{kp}",
                            placeholder="ex.: 45 40 35" if em_seg else "ex.: 8 7 6 5",
                            help="Separe as séries por espaço. O app calcula o total e a melhor série.")
        if ini and not lista0 and (ini.get("series_realizadas") or ini.get("reps_realizadas")):
            st.caption(f"Registro antigo: {resumo_series(ini)}. Deixe o campo vazio para manter assim.")
        lista, err = parse_series(txt, em_segundos=em_seg)
        if err:
            erro = f"{ex['nome']}: {err}"
        elif lista:
            feitas = [x for x in lista if x > 0]
            if em_seg:
                resp.update({"seg_series": lista, "series_realizadas": len(feitas), "tempo_seg": max(lista)})
            else:
                resp.update({"reps_series": lista, "series_realizadas": len(feitas), "reps_realizadas": max(lista)})
        elif ini:  # registro antigo sem detalhe por série: mantém o que já tinha
            for k in ("series_realizadas", "reps_realizadas", "tempo_seg"):
                if ini.get(k) is not None:
                    resp[k] = ini[k]
        var = st.text_input("Variação/ajuste (opcional)", value=ini.get("variacao", ""), key=f"va_{kp}",
                            placeholder="ex.: joelhos no chão, com elástico, pés no banco")
        if var.strip():
            resp["variacao"] = var.strip()
    elif tipo == "corrida":
        c1, c2, c3 = st.columns(3)
        t0 = ini.get("tempo_seg")
        dist = c1.number_input("Distância (m)", min_value=0, value=ini.get("distancia_m"), step=50, key=f"dist_{kp}")
        mi = c2.number_input("Minutos", min_value=0, value=None if t0 is None else int(round(t0)) // 60, step=1, key=f"min_{kp}")
        se = c3.number_input("Segundos", min_value=0, max_value=59, value=None if t0 is None else int(round(t0)) % 60,
                             step=1, key=f"seg_{kp}")
        tempo = (mi or 0) * 60 + (se or 0)
        resp.update({"distancia_m": dist, "tempo_seg": tempo or None})
        voltas = r_crono.get("voltas_seg") or ini.get("voltas_seg")
        if voltas:
            resp["voltas_seg"] = voltas
            resp["pista_m"] = r_crono.get("pista_m") or ini.get("pista_m")
            st.caption(f"🏁 {len(voltas)} voltas de {resp['pista_m']} m: " + " · ".join(fmt_tempo(v) for v in voltas))
        if dist and tempo:
            ritmo = tempo / (dist / 1000)
            st.caption(f"Ritmo médio: {int(ritmo // 60)}:{int(round(ritmo % 60)):02d} min/km")
    elif tipo == "tempo":
        dur = st.number_input("Duração realizada (min)", min_value=0, value=ini.get("duracao_min"), step=1, key=f"dur_{kp}")
        resp["duracao_min"] = dur
    elif tipo == "cronometrado":
        t0 = ini.get("tempo_seg")
        txt = st.text_input("Tempo (ex.: 12.35 ou 1:05)", value="" if t0 is None else texto_tempo(t0), key=f"crono_{kp}")
        v = parse_tempo(txt)
        if txt.strip() and v is None:
            erro = f"{ex['nome']}: tempo inválido"
        resp["tempo_seg"] = v
        tent = r_crono.get("tentativas_seg") or ini.get("tentativas_seg")
        if tent and len(tent) > 1:
            resp["tentativas_seg"] = tent
    elif tipo == "distancia":
        v = st.number_input("Marca (m)", min_value=0.0, value=ini.get("valor_m"), step=0.01, format="%.2f", key=f"distm_{kp}")
        resp["valor_m"] = v

    if status == "nao_fez":
        for k in CAMPOS_DE_DADOS + ("series_realizadas", "voltas_seg", "pista_m", "tentativas_seg"):
            resp.pop(k, None)
    elif status is None and tem_dados(resp):
        status = "feito"
    if status:
        resp["status"] = status
    if sensacao:
        resp["sensacao"] = sensacao
    return resp, erro


def cronometro_do_exercicio(ck, i, ex, rasc):
    tipo = tipo_registro(ex)
    modo = "voltas" if tipo == "corrida" else "simples"
    res = _cronometro_componente(
        chave=f"taf_crono_ex_{usuario_input}_{ck}_{i}",
        modo=modo,
        titulo="🏃 Cronômetro de voltas" if modo == "voltas" else "⏱️ Cronômetro deste exercício",
        usuario=usuario_input,
        pista=400,
        alvo=alvo_corrida(ex) if modo == "voltas" else None,
        confirmados=rasc["ids"][-30:],
        key=f"cronoex_{ck}_{i}",
        default=None,
    )
    if isinstance(res, dict) and res.get("id") and res["id"] not in rasc["ids"]:
        rasc["ids"] = (rasc["ids"] + [res["id"]])[-30:]
        if res.get("tempo_seg"):
            anterior = rasc["resultados"].get(str(i)) or {}
            res["tentativas_seg"] = (anterior.get("tentativas_seg") or []) + [res["tempo_seg"]]
            rasc["resultados"][str(i)] = res
            preencher_formulario(ck, i, tipo, res, forcar=True)
        dados_usuario["rascunho_treino"] = rasc
        salvar()
        st.session_state["toast"] = "✅ Resultado do cronômetro registrado no formulário abaixo."
        st.rerun()
    r = rasc["resultados"].get(str(i))
    if r and modo == "simples" and tipo != "isometria" and len(r.get("tentativas_seg") or []) > 1:
        st.caption("Tentativas de hoje: " + " · ".join(fmt_tempo(x) for x in r["tentativas_seg"])
                   + " — o formulário ficou com a última; ajuste se quiser outra.")



tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🎯 Treino de Hoje", "📅 Cronograma", "🤖 IA Assistente", "📊 Minha Evolução", "📄 Editais & Cargos"]
)

# -----------------------------------------------------------------------
# TAB 1: TREINO DE HOJE
# -----------------------------------------------------------------------
if st.session_state.get("toast"):
    st.toast(st.session_state.pop("toast"))

with tab1:
    st.header("🎯 Treino de Hoje")
    if st.session_state.get("msg_ciclo"):
        st.success(st.session_state.pop("msg_ciclo"))

    if medida_da_semana_pendente():
        with st.expander("⚖️ Hora de registrar suas medidas da semana (peso, cintura, FC de repouso)"):
            form_medidas("hoje")

    plano = dados_usuario.get("plano_semanal") or plano_padrao()
    dados_usuario["plano_semanal"] = plano
    treinos = plano.get("treinos", [])
    idx_pendente = next((i for i, t in enumerate(treinos) if not t.get("concluido")), -1)

    feitos = sum(1 for t in treinos if t.get("concluido"))
    if treinos:
        st.progress(feitos / len(treinos), text=f"Semana {plano.get('ciclo_id', 1)}: {feitos} de {len(treinos)} treinos feitos")

    if idx_pendente == -1:
        st.success("🎉 Você concluiu todos os treinos desta semana!")
        c_a, c_b = st.columns(2)
        if c_a.button("⚡ Montar próxima semana com progressão", type="primary"):
            with st.spinner("Montando a próxima semana..."):
                msg = avancar_ciclo(dados_usuario, usar_ia=True)
            if salvar():
                st.session_state["msg_ciclo"] = msg
                st.rerun()
        if c_b.button("🔁 Repetir esta semana"):
            msg = avancar_ciclo(dados_usuario, usar_ia=False)
            if salvar():
                st.session_state["msg_ciclo"] = msg
                st.rerun()
    else:
        treino_pendente = treinos[idx_pendente]
        st.subheader(f"📌 {treino_pendente['dia_nome']}")
        st.caption("O próximo treino é liberado quando você marcar este como concluído.")

        ck = f"{plano.get('ciclo_id', 1)}_{treino_pendente.get('id', idx_pendente + 1)}"
        rasc = rascunho_atual(ck)
        for i_r, r in rasc["resultados"].items():
            if i_r.isdigit() and int(i_r) < len(treino_pendente["exercicios"]):
                preencher_formulario(ck, int(i_r), tipo_registro(treino_pendente["exercicios"][int(i_r)]), r, forcar=False)

        for i, ex in enumerate(treino_pendente["exercicios"]):
            etiqueta = f" · 🏁 prova: {nomes_provas.get(ex.get('prova_id'), '')}" if ex.get("prova_id") in nomes_provas else ""
            st.markdown(f"**{ex['nome']}** — `{ex.get('series', 1)}x {ex.get('reps', '')}`{etiqueta}")
            if ex.get("detalhes"):
                st.caption(f"ℹ️ {ex['detalhes']}")
            if tipo_registro(ex) in ("corrida", "cronometrado", "tempo", "isometria"):
                ja = " ✅" if str(i) in rasc["resultados"] else ""
                dica = " (cada Finalizar = 1 série)" if tipo_registro(ex) == "isometria" else ""
                with st.expander(f"⏱️ Cronômetro deste exercício{dica}{ja}", expanded=ex.get("tipo") == "corrida"):
                    cronometro_do_exercicio(ck, i, ex, rasc)

        st.markdown("---")
        with st.expander("⏱️ Cronômetro livre (descanso entre séries, etc.)"):
            cronometro_treino(usuario_input)
        st.markdown("---")
        with st.form("form_treino_hoje"):
            st.markdown("### 📝 Registrar Desempenho")
            st.caption("Deixe em branco o que você não fez — campos vazios não entram nos gráficos.")
            data_execucao = st.date_input("Data em que realizou este treino:", value=datetime.date.today(), format="DD/MM/YYYY")
            rpe = st.slider("Esforço percebido geral (1 = muito leve, 10 = máximo):", 1, 10, 6)

            st.caption("Em cada exercício: marque como foi a execução e anote o resultado. "
                       "Força: repetições de cada série separadas por espaço (ex.: 8 7 6 5).")
            respostas, erros = [], []
            for i, ex in enumerate(treino_pendente["exercicios"]):
                st.markdown(f"**{ex['nome']}** — alvo: `{ex.get('series', 1)}x {ex.get('reps', '')}`")
                resp, err = campos_registro(ex, f"{ck}_{i}", r_crono=rasc["resultados"].get(str(i)))
                respostas.append(resp)
                if err:
                    erros.append(err)
                st.divider()

            obs = st.text_area("Observações (dores, sensações, condições do dia):")
            if st.form_submit_button("💾 Salvar e concluir este treino", type="primary", width="stretch"):
                if erros:
                    st.error("Corrija antes de salvar:\n\n- " + "\n- ".join(erros))
                elif not any(tem_dados(r) or r.get("status") for r in respostas):
                    st.warning("Nada foi preenchido. Se não treinou algum exercício, marque **❌ Não fiz** nele — "
                               "assim o treino é concluído e a IA sabe o que ficou de fora.")
                else:
                    data_str = str(data_execucao)
                    treinos[idx_pendente]["concluido"] = True
                    treinos[idx_pendente]["data_conclusao"] = data_str
                    dados_usuario["historico_evolucoes"].append({
                        "data": data_str,
                        "edital": dados_usuario.get("edital_ativo"),
                        "cargo": dados_usuario.get("cargo_ativo"),
                        "ciclo_id": plano.get("ciclo_id", 1),
                        "treino": treino_pendente["dia_nome"],
                        "rpe": rpe,
                        "exercicios_realizados": respostas,
                        "obs": obs,
                    })
                    dados_usuario.pop("rascunho_treino", None)  # o rascunho do cronômetro já entrou no registro
                    msg = None
                    if all(t.get("concluido") for t in treinos):
                        # AUTOMAÇÃO: última sessão da semana → monta a próxima sozinho.
                        with st.spinner("Semana concluída! Montando a próxima com progressão..."):
                            msg = avancar_ciclo(dados_usuario, usar_ia=True)
                    if salvar():
                        st.session_state["msg_ciclo"] = (msg or f"Treino de {data_execucao:%d/%m/%Y} salvo! Próximo treino liberado.")
                        st.rerun()
                    else:
                        st.error("O registro NÃO foi salvo na nuvem (veja o erro na barra lateral). Tente de novo antes de sair.")

    # ---- Simulado completo do TAF ----
    if provas_ativas:
        st.markdown("---")
        with st.expander("🏁 Registrar simulado do TAF (sugestão: a cada 4 semanas)"):
            st.caption("Faça como no dia da prova. Deixe em branco as provas que não fez.")
            with st.form("form_simulado"):
                data_sim = st.date_input("Data do simulado", value=datetime.date.today(), format="DD/MM/YYYY", key="data_sim")
                valores = {}
                for p in provas_ativas:
                    meta = meta_para(p, sexo_usuario)
                    rotulo = f"{p['nome']} (meta: {meta_texto(p, meta)})"
                    if p["tipo_medida"] == "tempo":
                        valores[p["id"]] = st.text_input(rotulo + " — tempo, ex.: 12:50 ou 11.80", key=f"sim_{p['id']}")
                    else:
                        valores[p["id"]] = st.text_input(rotulo + (" — metros, ex.: 1,65" if p["tipo_medida"] == "distancia" else " — repetições"), key=f"sim_{p['id']}")
                obs_sim = st.text_area("Observações do simulado", key="obs_sim")
                if st.form_submit_button("💾 Salvar Simulado"):
                    exs = []
                    for p in provas_ativas:
                        v = parse_valor(p, valores[p["id"]])
                        if v is not None:
                            exs.append({"nome": p["nome"], "tipo": "simulado", "prova_id": p["id"], "valor": v})
                    if not exs:
                        st.warning("Nenhum valor válido preenchido.")
                    else:
                        dados_usuario["historico_evolucoes"].append({
                            "data": str(data_sim), "edital": dados_usuario.get("edital_ativo"),
                            "cargo": dados_usuario.get("cargo_ativo"), "treino": "Simulado TAF",
                            # Vincula o simulado à semana atual para a IA avaliá-lo na virada da semana.
                            "ciclo_id": plano.get("ciclo_id", 1),
                            "tipo_registro": "simulado", "rpe": None, "exercicios_realizados": exs, "obs": obs_sim,
                        })
                        if salvar():
                            st.session_state["msg_ciclo"] = f"Simulado salvo com {len(exs)} prova(s)! Veja em '📊 Minha Evolução'."
                            st.rerun()

# -----------------------------------------------------------------------
# TAB 2: CRONOGRAMA (visualização + edição manual)
# -----------------------------------------------------------------------
with tab2:
    st.header("📅 Plano da Semana")
    plano = dados_usuario.get("plano_semanal", plano_padrao())
    st.info(f"Semana nº {plano.get('ciclo_id', 1)} | Criada em: {plano.get('criado_em')}")
    if plano.get("gerado_por_ia"):
        st.success(f"🤖 Treino gerado por IA para **{plano.get('cargo_base')}** ({plano.get('edital_base')})")
    else:
        st.caption("Este é o treino de adaptação padrão. Gere um treino personalizado na aba 'IA Assistente'.")

    editar = st.toggle("✏️ Editar exercícios manualmente")
    opcoes_prova = [""] + ids_provas
    for ti, t in enumerate(plano.get("treinos", [])):
        status = "✅ Concluído" if t.get("concluido") else "⏳ Pendente"
        with st.expander(f"{t['dia_nome']} — {status}", expanded=editar and not t.get("concluido")):
            if t.get("data_conclusao"):
                st.caption(f"Realizado em: {t['data_conclusao']}")
            df_ex = pd.DataFrame(t["exercicios"]).reindex(columns=["nome", "series", "reps", "detalhes", "tipo", "prova_id"])
            df_ex["prova_id"] = df_ex["prova_id"].fillna("")
            df_ex["tipo"] = df_ex["tipo"].fillna("forca")
            if not editar:
                mostrar = df_ex[["nome", "series", "reps", "detalhes"]].rename(
                    columns={"nome": "Exercício", "series": "Séries", "reps": "Reps/Tempo", "detalhes": "Detalhes"}
                )
                st.dataframe(mostrar, hide_index=True, width="stretch")
            else:
                df_ex["series"] = pd.to_numeric(df_ex["series"], errors="coerce").fillna(1).astype(int)
                df_ex["reps"] = df_ex["reps"].astype(str)
                editado = st.data_editor(
                    df_ex, key=f"editor_treino_{ti}", num_rows="dynamic", hide_index=True, width="stretch",
                    column_config={
                        "nome": st.column_config.TextColumn("Exercício", required=True),
                        "series": st.column_config.NumberColumn("Séries", min_value=1, step=1),
                        "reps": st.column_config.TextColumn("Reps/Tempo"),
                        "detalhes": st.column_config.TextColumn("Detalhes"),
                        "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS_EXERCICIO, required=True,
                                                                 help="; ".join(f"{k}: {v}" for k, v in TIPOS_EXERCICIO_DESC.items())),
                        "prova_id": st.column_config.SelectboxColumn("É prova do TAF?", options=opcoes_prova),
                    },
                )
                if st.button("💾 Salvar este dia", key=f"salvar_treino_{ti}"):
                    novos = []
                    for _, r in editado.iterrows():
                        if not str(r.get("nome") or "").strip():
                            continue
                        novos.append({
                            "nome": str(r["nome"]).strip(),
                            "series": int(r["series"]) if pd.notna(r["series"]) else 1,
                            "reps": "" if pd.isna(r["reps"]) else str(r["reps"]),
                            "detalhes": "" if pd.isna(r["detalhes"]) else str(r["detalhes"]),
                            "tipo": r["tipo"] if r["tipo"] in TIPOS_EXERCICIO else "forca",
                            "prova_id": r["prova_id"] or None,
                        })
                    if not novos:
                        st.error("O dia precisa ter pelo menos um exercício.")
                    else:
                        t["exercicios"] = novos
                        if salvar():
                            st.success("Treino atualizado!")
                            st.rerun()

    anteriores = dados_usuario.get("ciclos_anteriores", [])
    if anteriores:
        with st.expander(f"🗂️ Semanas anteriores ({len(anteriores)})"):
            for c in reversed(anteriores):
                datas = ", ".join(x.get("data_conclusao") or "—" for x in c.get("treinos", []))
                st.markdown(f"- **Semana {c.get('ciclo_id')}** ({'IA' if c.get('gerado_por_ia') else 'padrão'}) — treinos em: {datas}")

# -----------------------------------------------------------------------
# TAB 3: IA ASSISTENTE
# -----------------------------------------------------------------------
with tab3:
    st.header("🤖 IA Assistente TAF")
    st.subheader("🎯 Gerar Treino Personalizado com IA")
    perfil_fisico = dados_usuario.get("perfil_fisico", {})
    if not perfil_fisico_completo(perfil_fisico):
        st.warning("Preencha seu **Perfil Físico** na barra lateral antes de gerar um treino.")
    elif not ctx_ativo:
        st.info("Você ainda não tem um edital/cargo ativo. Vá até a aba '📄 Editais & Cargos' e clique em 'Definir como Meu Cargo Ativo'.")
    else:
        edital_ativo, cargo_ativo, descricao_taf, _ = ctx_ativo
        st.caption(f"Baseado em: **{edital_ativo}**, cargo **{cargo_ativo}** · {cfg.get('dias_por_semana', 3)} dias/semana · "
                   f"natação {'incluída' if cfg.get('incluir_natacao') else 'fora do plano'}")
        st.caption(descrever_perfil_fisico(perfil_fisico))
        with st.expander("Ver as exigências usadas como base"):
            st.markdown(descrever_provas_para_ia(provas_ativas, sexo_usuario))
        st.caption("⚠️ Treino gerado por IA — não substitui avaliação médica ou de educador físico.")
        st.caption("Gerar aqui **substitui** a semana atual (a semana em andamento continua com o mesmo número).")

        if st.button("⚡ Gerar Meu Treino Personalizado Agora", type="primary"):
            if not api_key:
                st.error("GEMINI_API_KEY não configurada nos Secrets — não é possível gerar o treino.")
            else:
                with st.spinner("Montando um plano específico para o seu edital e seu perfil..."):
                    plano_novo, erro = gerar_treino_personalizado(
                        edital_ativo, cargo_ativo, descricao_taf, provas_ativas, perfil_fisico, cfg,
                        dados_usuario.get("historico_evolucoes", []),
                        dados_usuario.get("plano_semanal", {}).get("ciclo_id", 1),
                        # Refaz a semana atual avaliando os registros/comentários desta mesma semana.
                        ciclo_resumo=dados_usuario.get("plano_semanal", {}).get("ciclo_id", 1),
                        medidas=dados_usuario.get("medidas"),
                    )
                if erro:
                    st.error(f"Não consegui gerar o treino: {erro}")
                else:
                    dados_usuario["plano_semanal"] = plano_novo
                    if salvar():
                        st.session_state["msg_ciclo"] = "Novo treino gerado e salvo!"
                        st.rerun()

    st.markdown("---")
    st.markdown("Tire dúvidas sobre o treino, técnica das provas ou o edital:")
    st.caption("O chat só orienta — ele **não altera** seu plano. Para mudar exercícios, use '✏️ Editar' na aba Cronograma.")

    chat_historico = dados_usuario.get("chat_ia", [])
    for msg in chat_historico:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt_user = st.chat_input("Ex: Como melhorar minha técnica na flexão abdominal?")
    if prompt_user:
        chat_historico.append({"role": "user", "content": prompt_user})
        with st.chat_message("user"):
            st.write(prompt_user)

        partes_ctx = []
        if ctx_ativo:
            partes_ctx.append(f"Concurso: {ctx_ativo[0]}, cargo {ctx_ativo[1]}.")
            partes_ctx.append(descrever_provas_para_ia(provas_ativas, sexo_usuario))
        partes_ctx.append(descrever_perfil_fisico(perfil_fisico))
        partes_ctx.append(descrever_medidas(dados_usuario.get("medidas")))
        plano_txt = "; ".join(
            f"{t['dia_nome']}: " + ", ".join(e["nome"] for e in t["exercicios"])
            for t in dados_usuario.get("plano_semanal", {}).get("treinos", [])
        )
        partes_ctx.append(f"Plano atual: {plano_txt}")
        partes_ctx.append(f"Registros recentes:\n{resumo_ciclo_para_ia(dados_usuario.get('historico_evolucoes', []), None)}")
        conversa = "\n".join(f"{m['role']}: {m['content']}" for m in chat_historico[-7:-1])

        resposta, erro_ia = None, None
        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                res = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=(
                        "Você é um preparador físico especialista em TAF de concursos militares. Responda em "
                        "português do Brasil, de forma objetiva e segura. Você NÃO consegue alterar o plano do "
                        "aluno: se sugerir mudanças, diga que ele pode editá-las na aba 'Cronograma'. "
                        "Não invente índices de edital: use apenas os informados. O abdominal da prova do CBMPE NÃO é "
                        "o remador: é a flexão abdominal com braços cruzados no peito e pés seguros pelo avaliador (item 14.11).\n\n"
                        + "\n".join(partes_ctx)
                        + f"\n\nConversa recente:\n{conversa}\n\nPergunta do aluno: {prompt_user}"
                    ),
                )
                resposta = res.text
            except Exception as e:
                erro_ia = str(e)
        else:
            erro_ia = "a chave GEMINI_API_KEY não está configurada nos Secrets"

        if resposta is None:
            resposta = f"⚠️ Não consegui consultar a IA agora ({erro_ia}). Nada foi alterado no seu treino."

        chat_historico.append({"role": "assistant", "content": resposta})
        with st.chat_message("assistant"):
            st.write(resposta)
        dados_usuario["chat_ia"] = chat_historico[-40:]
        salvar()

    if len(chat_historico) > 1 and st.button("🧹 Limpar conversa"):
        dados_usuario["chat_ia"] = chat_historico[:1]
        if salvar():
            st.rerun()

# -----------------------------------------------------------------------
# TAB 4: EVOLUÇÃO
# -----------------------------------------------------------------------
with tab4:
    st.header("📊 Minha Evolução")

    # ---- Medidas semanais ----
    st.subheader("⚖️ Medidas semanais")
    medidas = medidas_ordenadas(dados_usuario.get("medidas"))
    with st.expander("➕ Registrar medidas", expanded=not medidas):
        form_medidas("evolucao")
    if medidas:
        df_m = pd.DataFrame(medidas).reindex(columns=["data", "peso_kg", "cintura_cm", "fc_repouso", "obs"])
        df_m["data"] = pd.to_datetime(df_m["data"])
        indicadores = [
            ("peso_kg", "Peso", "kg", "off"),
            ("cintura_cm", "Cintura", "cm", "inverse"),
            ("fc_repouso", "FC de repouso", "bpm", "inverse"),
        ]
        cols_m = st.columns(len(indicadores) + 1)
        for col, (campo, rotulo, un, cor) in zip(cols_m, indicadores):
            serie = df_m[["data", campo]].dropna()
            if serie.empty:
                col.metric(rotulo, "—")
                continue
            atual, primeiro = float(serie[campo].iloc[-1]), float(serie[campo].iloc[0])
            fmt_n = (lambda v: f"{v:.0f}") if campo == "fc_repouso" else (lambda v: f"{v:.1f}".replace(".", ","))
            delta = None if len(serie) < 2 else f"{fmt_n(atual - primeiro)} {un} desde o início"
            col.metric(rotulo, f"{fmt_n(atual)} {un}", delta, delta_color=cor)
        altura = dados_usuario.get("perfil_fisico", {}).get("altura_cm")
        pesos = df_m["peso_kg"].dropna()
        if altura and not pesos.empty:
            imc = float(pesos.iloc[-1]) / (float(altura) / 100) ** 2
            cols_m[-1].metric("IMC", f"{imc:.1f}".replace(".", ","),
                              help="Peso ÷ altura². É só uma referência geral: não diferencia músculo de gordura.")
        st.caption("Cintura e FC de repouso diminuindo costumam indicar melhora do condicionamento. "
                   "FC de repouso bem acima do seu normal pode ser sinal de cansaço acumulado ou de que algo não vai bem.")

        abas_m = st.tabs([r for _, r, _, _ in indicadores])
        for aba, (campo, rotulo, un, _) in zip(abas_m, indicadores):
            with aba:
                serie = df_m[["data", campo]].dropna()
                if serie.empty:
                    st.info(f"Nenhum registro de {rotulo.lower()} ainda.")
                else:
                    st.plotly_chart(px.line(serie, x="data", y=campo, markers=True, labels={campo: un, "data": "Data"}),
                                    width="stretch", key=f"graf_medida_{campo}")

        with st.expander(f"📋 Todas as medidas ({len(medidas)})"):
            tabela = df_m.sort_values("data", ascending=False).copy()
            tabela["data"] = tabela["data"].dt.strftime("%d/%m/%Y")
            st.dataframe(tabela.rename(columns={"data": "Data", "peso_kg": "Peso (kg)", "cintura_cm": "Cintura (cm)",
                                                "fc_repouso": "FC repouso (bpm)", "obs": "Observações"}),
                         hide_index=True, width="stretch")
            datas_m = [m["data"] for m in reversed(medidas)]
            c_d1, c_d2 = st.columns([3, 1])
            data_apagar = c_d1.selectbox("Apagar a medida do dia:", datas_m,
                                         format_func=lambda d: datetime.date.fromisoformat(d).strftime("%d/%m/%Y"))
            if c_d2.button("🗑️ Apagar", key="apagar_medida"):
                dados_usuario["medidas"] = [m for m in medidas if m.get("data") != data_apagar]
                if salvar():
                    st.session_state["toast"] = "Medida apagada."
                    st.rerun()
    st.markdown("---")

    hist = dados_usuario.get("historico_evolucoes", [])
    if not hist:
        st.info("Nenhum treino registrado ainda. Registre seus treinos na primeira aba para ver os gráficos!")
    else:
        # ---- Painel de metas do edital ----
        if provas_ativas:
            st.subheader("🎯 Você x Índices do Edital")
            df_prov = linhas_por_prova(hist, provas_ativas)
            if sexo_usuario not in ("Masculino", "Feminino"):
                st.caption("Informe seu sexo no Perfil Físico para comparar com o índice certo.")
            colunas = st.columns(min(3, len(provas_ativas)))
            for i, p in enumerate(provas_ativas):
                meta = meta_para(p, sexo_usuario)
                dados_p = df_prov[df_prov["prova_id"] == p["id"]] if not df_prov.empty else df_prov
                with colunas[i % len(colunas)]:
                    if dados_p.empty:
                        st.metric(p["nome"], "sem registro", help=f"Meta: {meta_texto(p, meta)}")
                    else:
                        melhor = dados_p["valor"].max() if p["melhor"] == "maior" else dados_p["valor"].min()
                        ok = atingiu(p, melhor, meta)
                        status = "✅ meta atingida" if ok else (f"meta {meta_texto(p, meta)}" if meta is not None else "")
                        st.metric(p["nome"], fmt_valor(p, melhor), status, delta_color="off")
            if not df_prov.empty:
                prova_sel = st.selectbox(
                    "Ver evolução da prova:", [p["id"] for p in provas_ativas if p["id"] in set(df_prov["prova_id"])],
                    format_func=lambda x: nomes_provas.get(x, x),
                )
                p = next(x for x in provas_ativas if x["id"] == prova_sel)
                d = df_prov[df_prov["prova_id"] == prova_sel].copy()
                d["data"] = pd.to_datetime(d["data"])
                d = d.sort_values("data")
                y = d["valor"] / 60 if p["tipo_medida"] == "tempo" and d["valor"].max() >= 60 else d["valor"]
                unidade = "min" if p["tipo_medida"] == "tempo" and d["valor"].max() >= 60 else (
                    "s" if p["tipo_medida"] == "tempo" else ("m" if p["tipo_medida"] == "distancia" else "reps"))
                fig = px.line(d.assign(y=y), x="data", y="y", markers=True, color="origem",
                              labels={"y": unidade, "data": "Data"}, title=p["nome"])
                meta = meta_para(p, sexo_usuario)
                if meta is not None:
                    meta_plot = meta / 60 if unidade == "min" else meta
                    fig.add_hline(y=meta_plot, line_dash="dash", line_color="green", annotation_text=f"Índice do edital ({meta_texto(p, meta)})")
                if p["melhor"] == "menor":
                    st.caption("Nesta prova, quanto **menor** o tempo, melhor.")
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("Ative um edital/cargo com índices cadastrados para comparar seus resultados com as metas.")

        # ---- Ritmo de corrida (todas as corridas registradas) ----
        corridas = []
        for h in hist:
            for ex in h.get("exercicios_realizados") or []:
                if ex.get("tipo") == "corrida" and ex.get("distancia_m") and ex.get("tempo_seg"):
                    corridas.append({"data": h["data"], "distancia_m": ex["distancia_m"], "tempo_seg": ex["tempo_seg"]})
        alvo_2400 = next((meta_para(p, sexo_usuario) for p in provas_ativas if p["id"] == "corrida_2400m"), None)
        if corridas:
            df_c = pd.DataFrame(corridas)
            df_c["data"] = pd.to_datetime(df_c["data"])
            df_c["ritmo"] = (df_c["tempo_seg"] / 60) / (df_c["distancia_m"] / 1000)
            st.subheader("⏱️ Ritmo das corridas (min/km) — quanto menor, melhor")
            fig_r = px.line(df_c.sort_values("data"), x="data", y="ritmo", markers=True, hover_data=["distancia_m"],
                            labels={"ritmo": "min/km", "data": "Data"})
            if alvo_2400:
                ritmo_alvo = (alvo_2400 / 60) / 2.4
                fig_r.add_hline(y=ritmo_alvo, line_dash="dash", line_color="green",
                                annotation_text=f"Ritmo da meta dos 2.400 m ({ritmo_alvo:.2f} min/km)")
            st.plotly_chart(fig_r, width="stretch")

        # ---- Voltas das corridas feitas com o cronômetro de voltas ----
        com_voltas = []
        for h in hist:
            for ex in h.get("exercicios_realizados") or []:
                if ex.get("tipo") == "corrida" and ex.get("voltas_seg"):
                    com_voltas.append((h.get("data"), ex))
        if com_voltas:
            st.subheader("🏁 Ritmo volta a volta")
            com_voltas.sort(key=lambda x: str(x[0]), reverse=True)
            esc = st.selectbox(
                "Corrida:", range(len(com_voltas)),
                format_func=lambda k: (f"{datetime.date.fromisoformat(com_voltas[k][0]):%d/%m/%Y} — {com_voltas[k][1].get('nome')} "
                                       f"({com_voltas[k][1].get('distancia_m') or '—'} m em {fmt_tempo(com_voltas[k][1].get('tempo_seg'))})"),
            )
            ex_v = com_voltas[esc][1]
            pista_v = ex_v.get("pista_m") or 400
            df_v = pd.DataFrame({"volta": range(1, len(ex_v["voltas_seg"]) + 1), "seg": ex_v["voltas_seg"]})
            df_v["tempo"] = df_v["seg"].apply(fmt_tempo)
            fig_v = px.bar(df_v, x="volta", y="seg", text="tempo", labels={"volta": f"Volta ({pista_v:.0f} m)", "seg": "segundos"})
            if alvo_2400:
                volta_meta = alvo_2400 / 2400 * pista_v
                fig_v.add_hline(y=volta_meta, line_dash="dash", line_color="green",
                                annotation_text=f"Volta no ritmo da meta ({fmt_tempo(volta_meta)})")
            st.plotly_chart(fig_v, width="stretch")
            st.caption("Voltas parecidas entre si = ritmo bem distribuído. Se as últimas ficam muito mais lentas, "
                       "a saída provavelmente foi rápida demais.")

        # ---- Esforço percebido ----
        df_rpe = pd.DataFrame([{"data": h["data"], "rpe": h.get("rpe")} for h in hist if h.get("rpe")])
        if not df_rpe.empty:
            df_rpe["data"] = pd.to_datetime(df_rpe["data"])
            st.subheader("😮‍💨 Esforço percebido por treino")
            st.caption("Esforço sempre em 9–10 é sinal de que a carga está alta demais para esta fase.")
            st.plotly_chart(px.bar(df_rpe.sort_values("data"), x="data", y="rpe", labels={"rpe": "Esforço (1-10)", "data": "Data"}), width="stretch")

        # ---- Exercícios de força e isometria (séries de treino) ----
        linhas_f = []
        for h in hist:
            for ex in h.get("exercicios_realizados") or []:
                if ex.get("tipo") not in ("forca", "isometria") or ex.get("status") == "nao_fez":
                    continue
                if ex.get("seg_series"):
                    melhor, total, un = max(ex["seg_series"]), sum(ex["seg_series"]), "segundos"
                elif ex.get("reps_series"):
                    melhor, total, un = max(ex["reps_series"]), sum(ex["reps_series"]), "repetições"
                elif ex.get("reps_realizadas"):
                    melhor, total, un = ex["reps_realizadas"], None, "repetições"  # registro antigo
                else:
                    continue
                nome_base = re.sub(r"\s*\(.*?\)", "", ex.get("nome", "")).strip() or ex.get("nome", "")
                linhas_f.append({"data": h.get("data"), "exercicio": nome_base, "Melhor série": melhor,
                                 "Total": total, "un": un, "detalhe": resumo_series(ex),
                                 "execução": etiquetas_execucao(ex) or "—"})
        if linhas_f:
            st.subheader("💪 Evolução nos exercícios de força")
            df_f = pd.DataFrame(linhas_f)
            df_f["data"] = pd.to_datetime(df_f["data"])
            ordem_ex = df_f["exercicio"].value_counts().index.tolist()
            ex_sel = st.selectbox("Exercício:", ordem_ex,
                                  format_func=lambda n: f"{n} ({int((df_f['exercicio'] == n).sum())} registro(s))")
            d_f = df_f[df_f["exercicio"] == ex_sel].sort_values("data")
            un = d_f["un"].iloc[-1]
            colunas_y = ["Melhor série"] + (["Total"] if d_f["Total"].notna().any() else [])
            longo = d_f.melt(id_vars=["data", "detalhe", "execução"], value_vars=colunas_y,
                             var_name="medida", value_name="valor").dropna(subset=["valor"])
            fig_f = px.line(longo, x="data", y="valor", color="medida", markers=True,
                            hover_data={"detalhe": True, "execução": True},
                            labels={"valor": un, "data": "Data", "medida": ""})
            st.plotly_chart(fig_f, width="stretch")
            st.caption("**Melhor série** mostra sua força máxima; **Total** (soma das séries) mostra a resistência. "
                       "Registros antigos só têm a melhor série.")

        # ---- Histórico detalhado, com edição e exclusão ----
        st.subheader("🔍 Histórico detalhado")
        ordem = sorted(range(len(hist)), key=lambda i: str(hist[i].get("data")), reverse=True)
        for i in ordem:
            item = hist[i]
            editando = st.session_state.get("edit_hist") == i
            with st.expander(f"{item.get('data')} — {item.get('treino', '')}", expanded=editando):
                if editando:
                    with st.form(f"form_edit_hist_{i}"):
                        st.markdown("**✏️ Editando registro**")
                        try:
                            data0 = datetime.date.fromisoformat(str(item.get("data")))
                        except ValueError:
                            data0 = datetime.date.today()
                        nova_data = st.date_input("Data", value=data0, format="DD/MM/YYYY", key=f"ed_data_{i}")
                        novo_rpe = item.get("rpe")
                        if item.get("tipo_registro") != "simulado":
                            novo_rpe = st.slider("Esforço percebido geral", 1, 10, int(item.get("rpe") or 6), key=f"ed_rpe_{i}")
                        novos, erros_ed = [], []
                        for j, ex in enumerate(item.get("exercicios_realizados") or []):
                            st.markdown(f"**{ex.get('nome', 'Exercício')}**")
                            resp, err = campos_registro({"nome": ex.get("nome", "Exercício")}, f"ed{i}_{j}", ini=ex)
                            geridos = set(CAMPOS_DE_DADOS) | {"series_realizadas", "status", "sensacao", "variacao",
                                                              "voltas_seg", "pista_m", "tentativas_seg"}
                            # Mantém qualquer outra informação que já existia no registro.
                            novos.append({**{k: v for k, v in ex.items() if k not in geridos}, **resp})
                            if err:
                                erros_ed.append(err)
                        nova_obs = st.text_area("Observações", value=item.get("obs") or "", key=f"ed_obs_{i}")
                        c_s, c_c = st.columns(2)
                        salvar_ed = c_s.form_submit_button("💾 Salvar alterações", type="primary")
                        cancelar_ed = c_c.form_submit_button("↩️ Cancelar")
                    if cancelar_ed:
                        st.session_state.pop("edit_hist", None)
                        st.rerun()
                    if salvar_ed:
                        if erros_ed:
                            st.error("Corrija antes de salvar:\n\n- " + "\n- ".join(erros_ed))
                        else:
                            item.update({"data": str(nova_data), "rpe": novo_rpe, "exercicios_realizados": novos,
                                         "obs": nova_obs, "editado_em": agora_iso()})
                            if salvar():
                                st.session_state.pop("edit_hist", None)
                                st.session_state["toast"] = "✅ Registro atualizado."
                                st.rerun()
                    continue

                if item.get("rpe"):
                    st.caption(f"Esforço: {item['rpe']}/10")
                linhas_ex = []
                for ex in item.get("exercicios_realizados") or []:
                    if ex.get("status") == "nao_fez":
                        resultado = "não feito"
                    elif ex.get("valor") is not None and ex.get("prova_id"):
                        p = next((x for x in provas_ativas if x["id"] == ex["prova_id"]), {"tipo_medida": "repeticoes"})
                        resultado = fmt_valor(p, ex["valor"])
                    elif ex.get("tipo") == "corrida":
                        resultado = f"{ex.get('distancia_m') or '—'} m em {fmt_tempo(ex.get('tempo_seg'))}"
                    elif ex.get("tipo") == "tempo":
                        resultado = f"{ex.get('duracao_min') or '—'} min"
                    elif ex.get("tipo") == "cronometrado":
                        resultado = fmt_tempo(ex.get("tempo_seg"))
                    elif ex.get("tipo") == "distancia":
                        resultado = f"{ex.get('valor_m') or '—'} m"
                    else:
                        resultado = resumo_series(ex)
                    linhas_ex.append({"Exercício": ex.get("nome"), "Resultado": resultado,
                                      "Execução": etiquetas_execucao(ex) or "—"})
                if linhas_ex:
                    df_ex_h = pd.DataFrame(linhas_ex)
                    if (df_ex_h["Execução"] == "—").all():
                        df_ex_h = df_ex_h.drop(columns=["Execução"])
                    st.dataframe(df_ex_h, hide_index=True, width="stretch")
                if item.get("obs"):
                    st.caption(f"📝 {item['obs']}")
                chave = f"conf_del_hist_{i}"
                if not st.session_state.get(chave):
                    c_e, c_d = st.columns(2)
                    if c_e.button("✏️ Editar", key=f"edit_hist_btn_{i}"):
                        st.session_state["edit_hist"] = i
                        st.rerun()
                    if c_d.button("🗑️ Apagar este registro", key=f"del_hist_{i}"):
                        st.session_state[chave] = True
                        st.rerun()
                else:
                    st.warning("Apagar este registro? Não dá para desfazer.")
                    c_s, c_n = st.columns(2)
                    if c_s.button("✅ Sim, apagar", key=f"sim_del_{i}"):
                        del hist[i]
                        st.session_state[chave] = False
                        st.session_state.pop("edit_hist", None)
                        if salvar():
                            st.rerun()
                    if c_n.button("↩️ Cancelar", key=f"nao_del_{i}"):
                        st.session_state[chave] = False
                        st.rerun()

# -----------------------------------------------------------------------
# TAB 5: EDITAIS (BANCO COMPARTILHADO)
# -----------------------------------------------------------------------
with tab5:
    st.header("📄 Editais & Cargos")

    if not editais_globais:
        st.info("Nenhum edital cadastrado ainda.")
    else:
        lista_editais = list(editais_globais.keys())
        padrao = lista_editais.index(dados_usuario["edital_ativo"]) if dados_usuario.get("edital_ativo") in lista_editais else (
            lista_editais.index(NOME_EDITAL_2026) if NOME_EDITAL_2026 in lista_editais else 0)
        edital_sel = st.selectbox("Escolha o Edital/Concurso:", lista_editais, index=padrao)
        entrada_sel = normalizar_edital(editais_globais[edital_sel])
        meta_ed = entrada_sel["_meta"]
        cargos_disponiveis = list(entrada_sel["cargos"].keys())

        if not cargos_disponiveis:
            st.warning("Este edital não tem cargos cadastrados.")
        else:
            idx_cargo = cargos_disponiveis.index(dados_usuario["cargo_ativo"]) if dados_usuario.get("cargo_ativo") in cargos_disponiveis else 0
            cargo_sel = st.selectbox("Escolha o Cargo:", cargos_disponiveis, index=idx_cargo)
            st.markdown(f"### 📌 TAF para **{cargo_sel}** ({edital_sel})")
            st.info(entrada_sel["cargos"][cargo_sel])

            if edital_sel == NOME_EDITAL_2026:
                with st.expander("⚠️ Regras do edital que mais eliminam candidatos"):
                    for r in REGRAS_IMPORTANTES_2026:
                        st.markdown(f"- {r}")

            rodape = f"📥 Cadastrado por **{meta_ed.get('criado_por', 'desconhecido')}**"
            if meta_ed.get("criado_em"):
                rodape += f" em {meta_ed['criado_em']}"
            if meta_ed.get("atualizado_em"):
                rodape += f" · Última atualização por **{meta_ed.get('atualizado_por')}** em {meta_ed['atualizado_em']}"
            if meta_ed.get("arquivo_origem"):
                rodape += f" · Fonte: {meta_ed['arquivo_origem']}"
            st.caption(rodape)

            col_atv, col_del = st.columns([3, 1])
            with col_atv:
                ja_ativo = dados_usuario.get("edital_ativo") == edital_sel and dados_usuario.get("cargo_ativo") == cargo_sel
                if ja_ativo:
                    st.success("✅ Este é o seu cargo ativo.")
                elif st.button("🚀 Definir como Meu Cargo Ativo", type="primary"):
                    dados_usuario["edital_ativo"] = edital_sel
                    dados_usuario["cargo_ativo"] = cargo_sel
                    if salvar():
                        st.success(f"Cargo '{cargo_sel}' ({edital_sel}) ativado!")
                        st.rerun()

            with col_del:
                confirmar_key = f"confirma_exclusao_{edital_sel}"
                if not st.session_state.get(confirmar_key):
                    if st.button(f"🗑️ Excluir '{edital_sel}'"):
                        st.session_state[confirmar_key] = True
                        st.rerun()
                else:
                    st.warning(f"Excluir **{edital_sel}** para TODOS os usuários?")
                    c_sim, c_nao = st.columns(2)
                    if c_sim.button("✅ Sim"):
                        del editais_globais[edital_sel]
                        salvar_editais_globais(editais_globais, st.session_state.get("sha_editais"))
                        st.session_state[confirmar_key] = False
                        st.rerun()
                    if c_nao.button("↩️ Não"):
                        st.session_state[confirmar_key] = False
                        st.rerun()

        # ---- Provas e índices (editável) ----
        st.markdown("---")
        st.subheader(f"📏 Provas e índices — {edital_sel}")
        st.caption("Tempos no formato 12:36 ou 11.40 (segundos); distâncias em metros (1,70). Confira sempre no edital oficial.")
        provas_ed = entrada_sel.get("provas", [])
        df_p = pd.DataFrame([
            {
                "nome": p.get("nome"), "sexo": p.get("sexo", "ambos"), "tipo_medida": p.get("tipo_medida", "repeticoes"),
                "melhor": p.get("melhor", "maior"),
                "meta_masc": "" if p.get("meta_masc") is None else (fmt_tempo(p["meta_masc"]) if p.get("tipo_medida") == "tempo" else str(p["meta_masc"])),
                "meta_fem": "" if p.get("meta_fem") is None else (fmt_tempo(p["meta_fem"]) if p.get("tipo_medida") == "tempo" else str(p["meta_fem"])),
                "natacao": bool(p.get("natacao")), "observacao": p.get("observacao", ""), "id": p.get("id"),
            }
            for p in provas_ed
        ], columns=["nome", "sexo", "tipo_medida", "melhor", "meta_masc", "meta_fem", "natacao", "observacao", "id"])
        editar_provas = st.toggle("✏️ Editar provas/índices deste edital")
        if not editar_provas:
            if df_p.empty:
                st.info("Nenhuma prova cadastrada para este edital. Ative a edição para cadastrar.")
            else:
                st.dataframe(
                    df_p[["nome", "sexo", "meta_masc", "meta_fem", "observacao"]].rename(columns={
                        "nome": "Prova", "sexo": "Sexo", "meta_masc": "Índice masc.", "meta_fem": "Índice fem.", "observacao": "Regras"}),
                    hide_index=True, width="stretch",
                )
        else:
            editado_p = st.data_editor(
                df_p, key=f"editor_provas_{edital_sel}", num_rows="dynamic", hide_index=True, width="stretch",
                column_config={
                    "nome": st.column_config.TextColumn("Prova", required=True),
                    "sexo": st.column_config.SelectboxColumn("Vale para", options=["ambos", "M", "F"], required=True),
                    "tipo_medida": st.column_config.SelectboxColumn("Medida", options=["repeticoes", "tempo", "distancia"], required=True),
                    "melhor": st.column_config.SelectboxColumn("Melhor quando", options=["maior", "menor"], required=True),
                    "meta_masc": st.column_config.TextColumn("Índice masc."),
                    "meta_fem": st.column_config.TextColumn("Índice fem."),
                    "natacao": st.column_config.CheckboxColumn("É natação?"),
                    "observacao": st.column_config.TextColumn("Regras/observações"),
                    "id": None,
                },
            )
            if st.button("💾 Salvar provas deste edital"):
                novas, erros, usados = [], [], set()
                for _, r in editado_p.iterrows():
                    nome = str(r.get("nome") or "").strip()
                    if not nome:
                        continue
                    base_p = {"tipo_medida": r["tipo_medida"]}
                    mm = parse_valor(base_p, r["meta_masc"]) if str(r["meta_masc"] or "").strip() else None
                    mf = parse_valor(base_p, r["meta_fem"]) if str(r["meta_fem"] or "").strip() else None
                    if str(r["meta_masc"] or "").strip() and mm is None:
                        erros.append(f"{nome}: índice masculino inválido")
                    if str(r["meta_fem"] or "").strip() and mf is None:
                        erros.append(f"{nome}: índice feminino inválido")
                    pid = r["id"] if isinstance(r["id"], str) and r["id"] else slug(nome)
                    while pid in usados:
                        pid += "_2"
                    usados.add(pid)
                    antigo = next((p for p in provas_ed if p.get("id") == pid), {})
                    novas.append({
                        **antigo, "id": pid, "nome": nome, "sexo": r["sexo"], "tipo_medida": r["tipo_medida"],
                        "melhor": r["melhor"], "meta_masc": mm, "meta_fem": mf, "natacao": bool(r["natacao"]),
                        "observacao": "" if pd.isna(r["observacao"]) else str(r["observacao"]),
                    })
                if erros:
                    st.error("Corrija antes de salvar: " + "; ".join(erros))
                else:
                    entrada_sel["provas"] = novas
                    entrada_sel["_meta"]["atualizado_por"] = usuario_input
                    entrada_sel["_meta"]["atualizado_em"] = agora_iso()
                    editais_globais[edital_sel] = entrada_sel
                    _, ok = salvar_editais_globais(editais_globais, st.session_state.get("sha_editais"))
                    if ok:
                        st.success("Provas salvas!")
                        st.rerun()

    # ---- Cadastro de novo edital por PDF ----
    st.markdown("---")
    with st.expander("➕ Cadastrar/substituir edital a partir do PDF"):
        nome_edital_input = st.text_input("Nome/Sigla do Concurso (ex: PCPE 2027):", value="").strip().upper()
        uploaded_pdf = st.file_uploader("PDF do edital:", type=["pdf"])
        if nome_edital_input and nome_edital_input in editais_globais:
            st.warning(f"Já existe '{nome_edital_input}'. Processar vai SUBSTITUIR cargos e provas dele.")
        if uploaded_pdf and nome_edital_input and api_key and st.button("🔍 Processar Edital"):
            with st.spinner("Lendo o PDF inteiro e extraindo o TAF..."):
                try:
                    reader = pypdf.PdfReader(uploaded_pdf)
                    texto_completo = "\n".join(p.extract_text() or "" for p in reader.pages)
                    # O PDF inteiro é enviado (antes só ia o começo e a tabela do TAF ficava de fora).
                    prompt_analise = f"""
                    Analise o edital a seguir e extraia o Teste/Exame de Aptidão Física (TAF).
                    Retorne ESTRITAMENTE um JSON válido no formato:
                    {{
                      "cargos": {{"Nome do cargo": "Resumo do TAF para este cargo, citando o item do edital"}},
                      "provas": [
                        {{"nome": "Corrida de 2.400 m", "sexo": "ambos", "tipo_medida": "tempo", "melhor": "menor",
                          "meta_masc": 756, "meta_fem": 889, "natacao": false, "observacao": "regras principais e item"}}
                      ]
                    }}
                    Regras: "sexo" é "ambos", "M" ou "F" (use M/F quando a prova só existir para um sexo);
                    "tipo_medida" é "repeticoes", "tempo" (valores em SEGUNDOS) ou "distancia" (valores em METROS);
                    "melhor" é "maior" ou "menor". Copie os índices EXATAMENTE como estão no edital;
                    se um índice não constar, use null. Não invente nada.

                    Texto do Edital:
                    {texto_completo[:400000]}
                    """
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt_analise)
                    estrutura = _extrair_json(response.text)
                    cargos_mapeados = estrutura.get("cargos") or {}
                    provas_ia = []
                    for p in estrutura.get("provas") or []:
                        if not p.get("nome"):
                            continue
                        provas_ia.append({
                            "id": slug(p["nome"]), "nome": p["nome"], "sexo": p.get("sexo", "ambos") if p.get("sexo") in ("ambos", "M", "F") else "ambos",
                            "tipo_medida": p.get("tipo_medida") if p.get("tipo_medida") in ("repeticoes", "tempo", "distancia") else "repeticoes",
                            "melhor": p.get("melhor") if p.get("melhor") in ("maior", "menor") else "maior",
                            "meta_masc": p.get("meta_masc"), "meta_fem": p.get("meta_fem"),
                            "natacao": bool(p.get("natacao")), "observacao": p.get("observacao", ""),
                        })
                    if not cargos_mapeados:
                        st.error("A IA não encontrou cargos neste edital. Verifique se o PDF tem texto selecionável.")
                    else:
                        agora = agora_iso()
                        existente = editais_globais.get(nome_edital_input)
                        meta_novo = normalizar_edital(existente)["_meta"] if existente else {"criado_por": usuario_input, "criado_em": agora}
                        meta_novo.update({"atualizado_por": usuario_input, "atualizado_em": agora, "arquivo_origem": uploaded_pdf.name})
                        editais_globais[nome_edital_input] = {"_meta": meta_novo, "cargos": cargos_mapeados, "provas": provas_ia}
                        _, ok = salvar_editais_globais(editais_globais, st.session_state.get("sha_editais"))
                        if ok:
                            st.success(f"Edital '{nome_edital_input}' salvo! **Confira os índices** extraídos pela IA na tabela de provas.")
                            st.rerun()
                except json.JSONDecodeError:
                    st.error("A IA não retornou um JSON válido. Tente novamente ou verifique se o PDF tem texto selecionável.")
                except Exception as e:
                    st.error(f"Erro ao processar o edital: {e}")
        elif uploaded_pdf and not api_key:
            st.error("GEMINI_API_KEY não configurada — não é possível ler o PDF.")
