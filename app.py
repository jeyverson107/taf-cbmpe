import streamlit as st
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
    page_icon="🏋️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded",
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

TIPOS_EXERCICIO = ["forca", "corrida", "tempo", "cronometrado", "distancia"]
TIPOS_EXERCICIO_DESC = {
    "forca": "séries x repetições",
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
        "observacao": "Joelhos a ~45º, braços cruzados no peito com mãos nos ombros; cotovelos tocam a coxa e "
                      "escápulas voltam ao solo. Pausas são permitidas dentro do 1 minuto (item 14.11).",
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
    tiver o perfil, mas o público tiver, COPIA automaticamente (migração)."""
    dados, sha, erro = _github_get(f"dados_{usuario}.json", DATA_REPO)
    if erro:
        st.sidebar.error(f"❌ {erro}")
        return {}, None
    if not dados and DATA_REPO != CODE_REPO:
        antigos, _, erro_pub = _github_get(f"dados_{usuario}.json", CODE_REPO)
        if not erro_pub and antigos:
            novo_sha, msg = _github_put(
                f"dados_{usuario}.json", antigos, None, f"Migra dados de {usuario} para o repositório privado", DATA_REPO
            )
            if novo_sha:
                st.session_state["aviso_migracao"] = True
                return antigos, novo_sha
            st.sidebar.error(f"❌ Não consegui copiar seus dados para o repositório privado: {msg}")
            return antigos, None
    return (dados or {}), sha


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
            if ex.get("tipo") == "forca" and ex.get("reps_realizadas"):
                partes.append(f"{ex['nome']}: {ex.get('series_realizadas')} séries, melhor série {ex['reps_realizadas']} reps")
            elif ex.get("tipo") == "corrida" and ex.get("distancia_m"):
                partes.append(f"{ex['nome']}: {ex['distancia_m']}m em {fmt_tempo(ex.get('tempo_seg'))}")
            elif ex.get("tipo") in ("cronometrado",) and ex.get("tempo_seg"):
                partes.append(f"{ex['nome']}: {fmt_tempo(ex['tempo_seg'])}")
            elif ex.get("tipo") == "distancia" and ex.get("valor_m"):
                partes.append(f"{ex['nome']}: {ex['valor_m']} m")
            elif ex.get("valor") is not None:
                partes.append(f"{ex['nome']}: {ex['valor']}")
        obs = f" | obs: {h['obs']}" if h.get("obs") else ""
        linhas.append(f"- {h.get('data')} ({h.get('treino')}), esforço {h.get('rpe')}/10: " + "; ".join(partes) + obs)
    return "\n".join(linhas) if linhas else "Sem registros ainda."


def gerar_treino_personalizado(edital, cargo, descricao_taf, provas, perfil_fisico, config, historico, ciclo_id):
    """Chama a IA para montar o plano do ciclo (semana) `ciclo_id`. Retorna (plano, erro)."""
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
    Observações do aluno: {config.get('observacoes') or 'nenhuma'}
    {natacao}

    Resultados registrados recentemente (use para calibrar a progressão):
    {resumo_ciclo_para_ia(historico, ciclo_id - 1)}

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

    Retorne ESTRITAMENTE um JSON válido (nada fora do JSON), no formato:
    {{"treinos": [{{"dia_nome": "Dia 1 - ...", "exercicios": [
        {{"nome": "...", "series": 3, "reps": "...", "detalhes": "...", "tipo": "forca", "prova_id": null}}
    ]}}]}}
    "tipo" deve ser um de: "forca" (séries/repetições), "corrida" (distância + tempo),
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
            edital, cargo, descricao, provas, perfil, cfg, dados.get("historico_evolucoes", []), proximo_id
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


# =============================================================================
# MIGRAÇÕES DE DADOS ANTIGOS
# =============================================================================
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
# LOGIN & PERFIL (SIDEBAR)
# =============================================================================
st.sidebar.title("🏋️‍♂️ TAF Pro - Perfil")
usuario_padrao = st.query_params.get("u", "")
usuario_raw = st.sidebar.text_input("Seu Nome / Login:", value=usuario_padrao)
usuario_input = normalizar_usuario(usuario_raw)
st.sidebar.caption("Dica: salve nos favoritos o link do app com `?u=seunome` no final para já abrir com o seu login.")

if not usuario_input:
    st.title("🛡️ Central TAF Militar & Treinos")
    st.info("👈 Digite seu nome/login na barra lateral para começar.")
    st.stop()

if usuario_raw.strip().lower().replace(" ", "_") != usuario_input:
    st.sidebar.caption(f"Login normalizado para: `{usuario_input}`")

# Toda vez que o login muda, os dados são recarregados (evita misturar perfis).
if st.session_state.get("usuario_carregado") != usuario_input:
    dados_remotos, sha_remoto = carregar_dados_github(usuario_input)
    st.session_state["dados"] = migrar_dados_antigos(dados_remotos or {})
    st.session_state["sha"] = sha_remoto
    st.session_state["usuario_carregado"] = usuario_input
    st.session_state["pin_ok"] = False

if st.sidebar.button("🔄 Recarregar Meus Dados Agora"):
    dados_remotos, sha_remoto = carregar_dados_github(usuario_input)
    st.session_state["dados"] = migrar_dados_antigos(dados_remotos or {})
    st.session_state["sha"] = sha_remoto
    st.session_state["pin_ok"] = False
    st.rerun()

dados_usuario = st.session_state["dados"]


def salvar():
    """Atalho: salva o perfil atual e atualiza o sha. Retorna True/False."""
    novo_sha, ok = salvar_dados_github(usuario_input, dados_usuario, st.session_state.get("sha"))
    if ok:
        st.session_state["sha"] = novo_sha
    return ok


if st.session_state.pop("aviso_migracao", False):
    st.sidebar.success("🔐 Seus dados foram copiados para o repositório privado.")

# -----------------------------------------------------------------------
# PROTEÇÃO POR PIN
# -----------------------------------------------------------------------
# Não é um login robusto, mas impede o acesso/edição por engano de outro perfil.
# A proteção real dos dados é o repositório PRIVADO (secret DATA_REPO).
if tem_pin(dados_usuario):
    if not st.session_state.get("pin_ok"):
        st.sidebar.info("🔒 Perfil protegido por PIN.")
        pin_tentativa = st.sidebar.text_input("Digite o PIN para continuar:", type="password", key=f"pin_{usuario_input}")
        if pin_tentativa:
            if conferir_pin(pin_tentativa, dados_usuario):
                st.session_state["pin_ok"] = True
                if dados_usuario.get("pin_hash"):
                    # Atualiza o PIN antigo para o formato seguro, sem pedir nada ao usuário.
                    dados_usuario["pin"] = gerar_registro_pin(pin_tentativa)
                    dados_usuario.pop("pin_hash", None)
                    salvar()
                st.rerun()
            else:
                st.sidebar.error("PIN incorreto.")
        st.title("🛡️ Central TAF Militar & Treinos")
        st.info("🔒 Digite o PIN na barra lateral para abrir seu perfil.")
        st.stop()
else:
    st.sidebar.warning("⚠️ Este perfil ainda não tem PIN de proteção.")
    with st.sidebar.form("form_criar_pin"):
        novo_pin = st.text_input("Criar um PIN (mín. 6 dígitos):", type="password")
        if st.form_submit_button("Definir PIN"):
            if len(novo_pin) >= 6:
                dados_usuario["pin"] = gerar_registro_pin(novo_pin)
                if salvar():
                    st.session_state["pin_ok"] = True
                    st.sidebar.success("PIN definido e salvo!")
                    st.rerun()
            else:
                st.sidebar.error("Use pelo menos 6 dígitos.")
    st.session_state["pin_ok"] = True

# Estrutura padrão (perfis antigos que só tenham parte dos campos não quebram)
dados_usuario.setdefault("perfil_fisico", {})
dados_usuario.setdefault("edital_ativo", None)
dados_usuario.setdefault("cargo_ativo", None)
dados_usuario.setdefault("plano_semanal", plano_padrao())
dados_usuario.setdefault("historico_evolucoes", [])
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

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🎯 Treino de Hoje", "📅 Cronograma", "🤖 IA Assistente", "📊 Minha Evolução", "📄 Editais & Cargos"]
)

# -----------------------------------------------------------------------
# TAB 1: TREINO DE HOJE
# -----------------------------------------------------------------------
with tab1:
    st.header("🎯 Treino de Hoje")
    if st.session_state.get("msg_ciclo"):
        st.success(st.session_state.pop("msg_ciclo"))

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

        for ex in treino_pendente["exercicios"]:
            etiqueta = f" · 🏁 prova: {nomes_provas.get(ex.get('prova_id'), '')}" if ex.get("prova_id") in nomes_provas else ""
            st.markdown(f"**{ex['nome']}** — `{ex.get('series', 1)}x {ex.get('reps', '')}`{etiqueta}")
            if ex.get("detalhes"):
                st.caption(f"ℹ️ {ex['detalhes']}")

        st.markdown("---")
        with st.form("form_treino_hoje"):
            st.markdown("### 📝 Registrar Desempenho")
            st.caption("Deixe em branco o que você não fez — campos vazios não entram nos gráficos.")
            data_execucao = st.date_input("Data em que realizou este treino:", value=datetime.date.today(), format="DD/MM/YYYY")
            rpe = st.slider("Esforço percebido geral (1 = muito leve, 10 = máximo):", 1, 10, 6)

            respostas = []
            for i, ex in enumerate(treino_pendente["exercicios"]):
                tipo = ex.get("tipo", "forca")
                st.markdown(f"**{ex['nome']}** — alvo: `{ex.get('series', 1)}x {ex.get('reps', '')}`")
                base = {"nome": ex["nome"], "tipo": tipo, "prova_id": ex.get("prova_id")}
                if tipo == "corrida":
                    c1, c2, c3 = st.columns(3)
                    dist = c1.number_input("Distância (m)", min_value=0, value=None, step=50, key=f"dist_{i}")
                    mi = c2.number_input("Minutos", min_value=0, value=None, step=1, key=f"min_{i}")
                    se = c3.number_input("Segundos", min_value=0, max_value=59, value=None, step=1, key=f"seg_{i}")
                    tempo = (mi or 0) * 60 + (se or 0)
                    respostas.append({**base, "distancia_m": dist, "tempo_seg": tempo or None})
                elif tipo == "tempo":
                    dur = st.number_input("Duração realizada (min)", min_value=0, value=None, step=1, key=f"dur_{i}")
                    respostas.append({**base, "duracao_min": dur})
                elif tipo == "cronometrado":
                    txt = st.text_input("Tempo (ex.: 12.35 ou 1:05)", key=f"crono_{i}")
                    respostas.append({**base, "tempo_seg": parse_tempo(txt)})
                elif tipo == "distancia":
                    v = st.number_input("Marca (m)", min_value=0.0, value=None, step=0.01, format="%.2f", key=f"distm_{i}")
                    respostas.append({**base, "valor_m": v})
                else:
                    c1, c2 = st.columns(2)
                    series_feitas = c1.number_input("Séries completas", min_value=0, value=None, step=1, key=f"ser_{i}")
                    reps_feitas = c2.number_input("Reps na melhor série", min_value=0, value=None, step=1, key=f"reps_{i}")
                    respostas.append({**base, "series_realizadas": series_feitas, "reps_realizadas": reps_feitas})

            obs = st.text_area("Observações (dores, sensações, condições do dia):")
            marcar_concluido = st.checkbox("✅ Marcar este treino como REALIZADO", value=False)
            if st.form_submit_button("💾 Salvar Registro"):
                if not marcar_concluido:
                    st.warning("Marque a caixinha de verificação para concluir o treino.")
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
                        "Não invente índices de edital: use apenas os informados.\n\n"
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
        if corridas:
            df_c = pd.DataFrame(corridas)
            df_c["data"] = pd.to_datetime(df_c["data"])
            df_c["ritmo"] = (df_c["tempo_seg"] / 60) / (df_c["distancia_m"] / 1000)
            st.subheader("⏱️ Ritmo das corridas (min/km) — quanto menor, melhor")
            fig_r = px.line(df_c.sort_values("data"), x="data", y="ritmo", markers=True, hover_data=["distancia_m"],
                            labels={"ritmo": "min/km", "data": "Data"})
            alvo_2400 = next((meta_para(p, sexo_usuario) for p in provas_ativas if p["id"] == "corrida_2400m"), None)
            if alvo_2400:
                ritmo_alvo = (alvo_2400 / 60) / 2.4
                fig_r.add_hline(y=ritmo_alvo, line_dash="dash", line_color="green",
                                annotation_text=f"Ritmo da meta dos 2.400 m ({ritmo_alvo:.2f} min/km)")
            st.plotly_chart(fig_r, width="stretch")

        # ---- Esforço percebido ----
        df_rpe = pd.DataFrame([{"data": h["data"], "rpe": h.get("rpe")} for h in hist if h.get("rpe")])
        if not df_rpe.empty:
            df_rpe["data"] = pd.to_datetime(df_rpe["data"])
            st.subheader("😮‍💨 Esforço percebido por treino")
            st.caption("Esforço sempre em 9–10 é sinal de que a carga está alta demais para esta fase.")
            st.plotly_chart(px.bar(df_rpe.sort_values("data"), x="data", y="rpe", labels={"rpe": "Esforço (1-10)", "data": "Data"}), width="stretch")

        # ---- Histórico detalhado, com exclusão ----
        st.subheader("🔍 Histórico detalhado")
        ordem = sorted(range(len(hist)), key=lambda i: str(hist[i].get("data")), reverse=True)
        for i in ordem:
            item = hist[i]
            with st.expander(f"{item.get('data')} — {item.get('treino', '')}"):
                if item.get("rpe"):
                    st.caption(f"Esforço: {item['rpe']}/10")
                linhas_ex = []
                for ex in item.get("exercicios_realizados") or []:
                    if ex.get("valor") is not None and ex.get("prova_id"):
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
                        resultado = f"{ex.get('series_realizadas') or '—'} séries · melhor série {ex.get('reps_realizadas') or '—'} reps"
                    linhas_ex.append({"Exercício": ex.get("nome"), "Resultado": resultado})
                if linhas_ex:
                    st.dataframe(pd.DataFrame(linhas_ex), hide_index=True, width="stretch")
                if item.get("obs"):
                    st.caption(f"📝 {item['obs']}")
                chave = f"conf_del_hist_{i}"
                if not st.session_state.get(chave):
                    if st.button("🗑️ Apagar este registro", key=f"del_hist_{i}"):
                        st.session_state[chave] = True
                        st.rerun()
                else:
                    st.warning("Apagar este registro? Não dá para desfazer.")
                    c_s, c_n = st.columns(2)
                    if c_s.button("✅ Sim, apagar", key=f"sim_del_{i}"):
                        del hist[i]
                        st.session_state[chave] = False
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
