"""Cliente da API pública do TCE-SP, sem dependências externas."""
import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://transparencia.tce.sp.gov.br/api/json"


def obter_lista(caminho):
    req = Request(f"{BASE}/{caminho}", headers={"Accept": "application/json", "User-Agent": "ConsultaMunicipal/1.0"})
    for tentativa in range(3):
        try:
            with urlopen(req, timeout=60) as resposta:
                dados = json.loads(resposta.read().decode("utf-8-sig"))
            if not isinstance(dados, list) or any(not isinstance(r, dict) for r in dados):
                raise ValueError("A API retornou um formato inesperado, em vez de uma lista de registros.")
            return dados
        except HTTPError as erro:
            if erro.code in (429, 500, 502, 503, 504) and tentativa < 2:
                time.sleep(2 ** (tentativa + 1))
                continue
            raise ValueError(f"API indisponível para a consulta (HTTP {erro.code}).") from erro
        except (URLError, TimeoutError) as erro:
            if tentativa < 2:
                time.sleep(2 ** (tentativa + 1))
                continue
            raise ValueError("Não foi possível conectar ao TCE-SP. Tente novamente mais tarde.") from erro
        except (json.JSONDecodeError, UnicodeDecodeError) as erro:
            raise ValueError("O serviço não retornou JSON válido.") from erro


def municipios():
    dados = obter_lista("municipios")
    if not dados or any(not r.get("municipio") or not r.get("municipio_extenso") for r in dados):
        raise ValueError("A lista de municípios está vazia ou em formato inesperado.")
    return sorted(dados, key=lambda r: r["municipio_extenso"].casefold())


def meses_periodo(inicio, fim):
    """Datas MM/AAAA, meses inclusivos, com passagem de ano."""
    try:
        a = datetime.strptime(inicio.strip(), "%m/%Y")
        b = datetime.strptime(fim.strip(), "%m/%Y")
    except ValueError as erro:
        raise ValueError("Informe o período no formato MM/AAAA, por exemplo 01/2026.") from erro
    if a > b:
        raise ValueError("O início deve ser anterior ou igual ao fim.")
    if a.year < 2014:
        raise ValueError("Informe um ano a partir de 2014.")
    quantidade = (b.year - a.year) * 12 + b.month - a.month + 1
    if quantidade > 60:
        raise ValueError("Consulte no máximo 60 meses por vez.")
    return [((a.year * 12 + a.month - 1 + i) // 12,
             (a.year * 12 + a.month - 1 + i) % 12 + 1) for i in range(quantidade)]


def valor_decimal(valor):
    texto = str(valor).strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
        if not numero.is_finite():
            raise InvalidOperation
        return numero
    except InvalidOperation as erro:
        raise ValueError(f"Valor monetário inválido retornado pela API: {valor!r}") from erro


def consultar_mes(tipo, cidade, ano, mes):
    if tipo not in ("receitas", "despesas"):
        raise ValueError("Tipo de consulta inválido.")
    dados = obter_lista(f"{tipo}/{quote(cidade, safe='')}/{ano}/{mes}")
    campo = "vl_arrecadacao" if tipo == "receitas" else "vl_despesa"
    for registro in dados:
        if campo not in registro:
            raise ValueError(f"A API não retornou o campo {campo}.")
        valor_decimal(registro[campo])
        registro["competencia_consulta"] = f"{ano}-{mes:02d}"
    return dados


def moeda(valor):
    return "R$ " + f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))
