import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Annotated

import requests
from bs4 import BeautifulSoup # Para parsear HTML
from dotenv import load_dotenv # Para carregar variáveis de ambiente (.env)
from fastapi import FastAPI, HTTPException # Framework web
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from pymongo import MongoClient # Driver MongoDB
from pymongo.errors import ConnectionFailure, OperationFailure
from dateutil import parser as date_parser # Para parsear datas de forma mais flexível

from bson.decimal128 import Decimal128
from bson.codec_options import CodecOptions, TypeRegistry, TypeCodec

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# --- Codec para Decimal ---
class DecimalCodec(TypeCodec):
    python_type = Decimal    # O tipo Python que estamos tratando
    bson_type = Decimal128   # O tipo BSON correspondente

    def transform_python(self, value):
        """Converte Python Decimal para BSON Decimal128."""
        if value is None:
            return None
        # O construtor Decimal128 aceita Decimal diretamente
        return Decimal128(value)

    def transform_bson(self, value):
        """Converte BSON Decimal128 para Python Decimal."""
        if value is None:
            return None
        # O método to_decimal() faz a conversão inversa
        return value.to_decimal()

# Cria um registro de tipos e adiciona nosso codec
decimal_codec = DecimalCodec()
type_registry = TypeRegistry([decimal_codec])

# Cria as opções de codec com o registro de tipos
codec_options = CodecOptions(type_registry=type_registry)

# --- Configuração do MongoDB ---
MONGO_CONNECTION_STRING = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "InvoicesDB") # Usando o nome do seu log
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "Invoices") # Nome da coleção default

mongo_client = None
db = None
invoices_collection = None

try:
    print(f"Tentando conectar ao MongoDB em {MONGO_CONNECTION_STRING}...")
    # Conecta sem passar codec_options diretamente aqui
    mongo_client = MongoClient(
        MONGO_CONNECTION_STRING,
        serverSelectionTimeoutMS=5000
        # REMOVIDO: codec_options=codec_options
    )
    mongo_client.admin.command('ping') # Verifica a conexão

    # Obter o banco e a coleção aplicando as codec_options aqui (CORRETO)
    db = mongo_client.get_database(DB_NAME, codec_options=codec_options)
    invoices_collection = db.get_collection(COLLECTION_NAME, codec_options=codec_options)

    # Criar índice único (sem alterações aqui)
    invoices_collection.create_index("access_key", unique=True, sparse=True)
    # Atualiza a mensagem de log para refletir onde as opções são aplicadas
    print(f"Conectado ao MongoDB. DB='{DB_NAME}', Collection='{COLLECTION_NAME}' configuradas com suporte a Decimal128.")
except ConnectionFailure as e:
    print(f"Erro ao conectar ao MongoDB: {e}")
except Exception as e:
    print(f"Ocorreu um erro inesperado na configuração do MongoDB: {e}")


# --- Funções Auxiliares de Limpeza/Conversão ---

def safe_strip(value: Optional[str]) -> Optional[str]:
    """Remove espaços em branco das bordas se a string não for None."""
    return value.strip() if value else None

def parse_decimal_universal(value: Optional[str]) -> Optional[Decimal]:
    """
    Converte string numérica (possivelmente com . ou ,) para Decimal.
    Tenta lidar com milhares e separadores decimais de forma mais robusta.
    """
    if not value:
        return None

    cleaned_value = value.strip()
    # Remover caracteres não numéricos exceto ponto e vírgula
    cleaned_value = re.sub(r'[^\d,\.]', '', cleaned_value)

    try:
        # Verificar se ambos '.' e ',' existem
        has_dot = '.' in cleaned_value
        has_comma = ',' in cleaned_value

        if has_dot and has_comma:
            # Assume '.' como milhar e ',' como decimal (padrão BR mais comum)
            # Remove pontos, troca vírgula por ponto
            cleaned_value = cleaned_value.replace('.', '').replace(',', '.')
        elif has_comma:
            # Apenas vírgula existe, assume como decimal
            cleaned_value = cleaned_value.replace(',', '.')
        elif has_dot:
            # Apenas ponto existe. Verificar se é decimal ou milhar
            # Se houver mais de um ponto, o último é provavelmente decimal (ou erro)
            # Se houver apenas um ponto e mais de 2 dígitos depois, é provável milhar (ex: 1.500)
            # Se houver apenas um ponto e 1 ou 2 dígitos depois, é provável decimal (ex: 215.70)
            dot_count = cleaned_value.count('.')
            if dot_count > 1:
                 # Múltiplos pontos? Tenta remover todos menos o último
                 parts = cleaned_value.split('.')
                 cleaned_value = "".join(parts[:-1]) + "." + parts[-1]
            # Se chegou aqui, cleaned_value tem 0 ou 1 ponto.
            # O construtor Decimal lida bem com "1500" ou "215.70".
            # Nenhuma substituição extra necessária neste caso.

        # Se não tinha nem ponto nem vírgula, já está limpo (ex: "10")

        if not cleaned_value: # Se ficou vazio após limpeza
             return None

        return Decimal(cleaned_value)

    except (InvalidOperation, TypeError, ValueError) as e:
        print(f"Aviso: Falha ao converter '{value}' para Decimal. Limpo: '{cleaned_value}'. Erro: {e}")
        return None
    
def parse_datetime_flexible(value: Optional[str]) -> Optional[datetime]:
    """Converte string de data/hora para datetime usando dateutil."""
    if not value:
        return None
    try:
        # dayfirst=True ajuda a interpretar formatos como DD/MM/YYYY
        return date_parser.parse(value, dayfirst=True)
    except (ValueError, TypeError) as e:
        print(f"Aviso: Falha ao converter '{value}' para datetime. Erro: {e}")
        return None

UniversalDecimalValidator = BeforeValidator(parse_decimal_universal) # Novo nome
CleanStringValidator = BeforeValidator(safe_strip)
FlexibleDateTimeValidator = BeforeValidator(parse_datetime_flexible)

class ItemInvoice(BaseModel):
    code: Optional[Annotated[str, CleanStringValidator]] = Field(default=None, alias='Code')
    description: Optional[Annotated[str, CleanStringValidator]] = Field(default=None, alias='Description')
    quantity: Optional[Annotated[Decimal, UniversalDecimalValidator]] = Field(default=None, alias='Quantity')
    unit: Optional[Annotated[str, CleanStringValidator]] = Field(default=None, alias='Unit')
    value: Optional[Annotated[Decimal, UniversalDecimalValidator]] = Field(default=None, alias='Value')

    model_config = ConfigDict(
        populate_by_name=True,
        extra='ignore'
    )


class Invoice(BaseModel):
    id: Optional[str] = Field(alias='_id', default=None)
    market_name: Optional[Annotated[str, CleanStringValidator]] = Field(default=None, alias='MarketName')
    invoice_date: Optional[Annotated[datetime, FlexibleDateTimeValidator]] = Field(default=None, alias='InvoiceDate')
    total_invoice: Optional[Annotated[Decimal, UniversalDecimalValidator]] = Field(default=None, alias='TotalInvoice')
    quantity_total_items: Optional[int] = Field(default=None, alias='QuantityTotalItems')
    access_key: Optional[Annotated[str, CleanStringValidator]] = Field(default=None, alias='AccessKey')
    items: Optional[List[ItemInvoice]] = Field(default_factory=list, alias='Items')

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={
            Decimal: lambda v: str(v) if v is not None else None,
            datetime: lambda v: v.isoformat() if v is not None else None,
        },
        extra='ignore'
    )

# --- Lógica de Scraping ---

def extract_items_from_html(soup: BeautifulSoup) -> List[ItemInvoice]:
    """Extrai os itens da nota fiscal da tabela no HTML."""
    items = []
    table_body = soup.find('tbody', id='myTable')
    if not table_body:
        print("Aviso: Tabela de itens <tbody id='myTable'> não encontrada.")
        return items

    rows = table_body.find_all('tr')
    print(f"DEBUG: Encontradas {len(rows)} linhas na tabela de itens.") # DEBUG
    for i, row in enumerate(rows): # Adiciona índice para debug
        columns = row.find_all('td')
        print(f"\nDEBUG: Processando linha {i+1}, Colunas: {len(columns)}") # DEBUG
        if len(columns) >= 4:
            try:
                col0_text = columns[0].get_text(separator=' ', strip=True)
                # Regex para Descrição e Código (ajustada ligeiramente para robustez)
                desc_match = re.search(r'(.*?)\s+\(Código:\s*(\d+)\)', col0_text, re.IGNORECASE | re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else col0_text # Fallback se regex falhar
                code = desc_match.group(2).strip() if desc_match else None
                print(f"DEBUG [Linha {i+1}] Descrição: '{description}', Código: '{code}'")

                # Coluna 1: Quantidade - Regex mais robusta
                col1_text = columns[1].get_text(strip=True)
                print(f"DEBUG [Linha {i+1}] Texto Coluna Qtde: '{col1_text}'") # DEBUG
                # Tenta encontrar ': ' seguido por um número (com . ou ,)
                quantity_match = re.search(r':\s*([\d.,]+)', col1_text) # <-- Regex CORRIGIDA
                quantity_str = quantity_match.group(1) if quantity_match else None
                # Se falhar, tenta pegar só o número (caso não tenha ':')
                if quantity_str is None:
                    quantity_match_fallback = re.search(r'([\d.,]+)', col1_text)
                    quantity_str = quantity_match_fallback.group(1) if quantity_match_fallback else None
                    print(f"DEBUG [Linha {i+1}] Fallback Qtde String: '{quantity_str}'") # Debug Fallback
                print(f"DEBUG [Linha {i+1}] String Qtde extraída: '{quantity_str}'") # DEBUG

                # Coluna 2: Unidade
                col2_text = columns[2].get_text(strip=True)
                # Regex para Unidade (parece ok, mas descomentar)
                unit_match = re.search(r'UN\.?:\s*(\w+)', col2_text, re.IGNORECASE)
                unit = unit_match.group(1).strip() if unit_match else None
                print(f"DEBUG [Linha {i+1}] Unidade extraída: '{unit}'")

                # Coluna 3: Valor Total do Item
                col3_text = columns[3].get_text(strip=True)
                print(f"DEBUG [Linha {i+1}] Texto Coluna Valor: '{col3_text}'") # DEBUG
                # Procura por "Valor total R$:" ou "Vl. Total" etc, seguido pelo número
                value_match = re.search(r'(?:Valor|Vl)\.?\s*(?:total)?\s*R?\$?\s*:\s*R?\$?\s*([\d.,]+)', col3_text, re.IGNORECASE) # <-- Regex Corrigida (mais flexível com texto e :)
                value_str = value_match.group(1) if value_match else None
                print(f"DEBUG [Linha {i+1}] String Valor extraída: '{value_str}'") # DEBUG

                # Verifica se conseguimos extrair pelo menos descrição ou código E quantidade E valor
                if (description or code) and quantity_str and value_str:
                     # Certifica que code, description, unit não são usados antes de serem definidos
                    item = ItemInvoice(
                        code=code,             # Garanta que 'code' foi definido acima
                        description=description, # Garanta que 'description' foi definido acima
                        quantity=quantity_str,
                        unit=unit,             # Garanta que 'unit' foi definido acima
                        value=value_str
                    )
                    print(f"DEBUG [Linha {i+1}] Item Pydantic criado: {item.model_dump()}") # DEBUG
                    items.append(item)
                else:
                    print(f"AVISO [Linha {i+1}]: Dados essenciais não extraídos. Item ignorado.")
                    print(f"  -> Desc/Code: {description if 'description' in locals() else 'N/D'}/{code if 'code' in locals() else 'N/D'}, Qtde Str: {quantity_str}, Valor Str: {value_str}, Unit: {unit if 'unit' in locals() else 'N/D'}")


            except (AttributeError, IndexError, Exception) as e:
                # Não usar 'code' aqui pois pode não ter sido definido se o erro ocorreu antes
                print(f"Erro CRÍTICO ao processar linha de item {i+1}: {row.get_text(strip=True)} | Erro: {e}")
                # Considerar logar o traceback completo para depuração mais profunda
                # import traceback
                # print(traceback.format_exc())
                continue # Continua para a próxima linha

    print(f"DEBUG: Final da extração. Total de itens adicionados: {len(items)}") # DEBUG
    return items

# --- Função para Salvar no MongoDB ---
async def save_invoice_to_db(invoice: Invoice):
    """Salva a nota fiscal no MongoDB se não existir pela chave de acesso."""
    if invoices_collection is None:
        print("Aviso: Conexão com MongoDB não está disponível. Não foi possível salvar a nota.")
        return

    # Garante que temos o objeto Pydantic e a chave de acesso (que é o atributo python)
    if not invoice or not invoice.access_key:
        print("AVISO [DB]: Nota fiscal inválida ou sem chave de acesso (atributo python). Não será salva.")
        return

    access_key_value = invoice.access_key # Pega o valor da chave do objeto pydantic
    db_field_name = "AccessKey" # Usa o nome do campo como está no MongoDB (o Alias)

    try:
        # 1. Verifica se a nota já existe usando a chave de acesso
        print(f"DEBUG [DB]: Verificando existência da chave: {invoice.access_key}") # Log adicional
        #existing_invoice = invoices_collection.find_one({"access_key": invoice.access_key})
        existing_invoice = invoices_collection.find_one({db_field_name: access_key_value})

        # 2. Se NÃO existir (find_one retorna None), insere
        if existing_invoice is None:
            print(f"DEBUG [DB]: Chave {invoice.access_key} não encontrada. Preparando para inserir.") # Log adicional
            # Converte o modelo Pydantic para dict ANTES de inserir
            invoice_dict = invoice.model_dump(exclude_unset=True, by_alias=True) # exclude_unset é geralmente melhor que exclude_none
            # Remove o campo 'id' se ele for None (o _id do Pydantic)
            if 'id' in invoice_dict and invoice_dict['id'] is None:
                 del invoice_dict['id'] # MongoDB gerará _id

            print(f"DEBUG [DB]: Inserindo documento: {list(invoice_dict.keys())}") # Log chaves a inserir
            result = invoices_collection.insert_one(invoice_dict)
            print(f"SUCESSO [DB]: Nota fiscal {invoice.access_key} salva com ID: {result.inserted_id}")

        # 3. Se JÁ existir, NÃO faz nada (apenas loga)
        else:
            print(f"INFO [DB]: Nota fiscal com chave {invoice.access_key} já existe no banco de dados. Nenhuma ação realizada.")

    except OperationFailure as e:
        # Pode acontecer se houver violação de índice único (concorrência, SE o índice existe)
        print(f"ERRO [DB]: Erro de operação no MongoDB ao processar {invoice.access_key}: {e}")
        # Se o erro for de chave duplicada (E11000), a lógica funcionou mas houve concorrência
        if "E11000 duplicate key error" in str(e):
             print("INFO [DB]: Erro de chave duplicada indica que a nota foi inserida por outra requisição concorrente.")
    except Exception as e:
        print(f"ERRO [DB]: Erro inesperado ao salvar no MongoDB {invoice.access_key}: {e}")
        import traceback
        print(traceback.format_exc())
    except Exception as e:
        print(f"Erro inesperado ao salvar no MongoDB {invoice.access_key}: {e}")
        # Considerar lançar uma exceção HTTP 500 aqui se o salvamento for crítico
        # raise HTTPException(status_code=500, detail="Erro ao salvar a nota fiscal no banco de dados.")


# --- Inicialização do FastAPI ---
app = FastAPI(
    title="API de Scraping de Nota Fiscal",
    description="Extrai dados de notas fiscais da SEFAZ MG a partir do parâmetro QR Code.",
    version="1.0.0"
)

# --- Endpoint ---
@app.get("/", response_model=Invoice) # Define o modelo de resposta
async def index(qr_code_parameter: str):
    """
    Recebe o parâmetro 'p' do QR Code da NFC-e de MG, busca os dados na SEFAZ,
    extrai as informações e as salva no MongoDB se for uma nota nova.
    Retorna os dados extraídos da nota fiscal.
    """
    if not qr_code_parameter:
        raise HTTPException(status_code=400, detail="Parâmetro 'qr_code_parameter' é obrigatório.")

    # Constrói a URL alvo
    target_url = f"https://portalsped.fazenda.mg.gov.br/portalnfce/sistema/qrcode.xhtml?p={qr_code_parameter}"
    print(f"Buscando dados de: {target_url}")

    # Faz a requisição HTTP
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(target_url, headers=headers, timeout=30)
        response.raise_for_status()
        html_content = response.text
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=408, detail="Tempo limite excedido ao buscar a URL da SEFAZ.")
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar URL: {e}")
        raise HTTPException(status_code=503, detail=f"Erro ao acessar o portal da SEFAZ: {e}")

    # Parseia o HTML com BeautifulSoup
    soup = BeautifulSoup(html_content, 'lxml')
    print("DEBUG: HTML parseado com BeautifulSoup.")

    # --- Extração dos dados principais ---

    # Nome do Mercado
    market_name = None
    try:
        market_name_tag = soup.find('th', class_='text-center text-uppercase')
        if market_name_tag and market_name_tag.find('h4') and market_name_tag.find('h4').find('b'):
            market_name = market_name_tag.find('h4').find('b').get_text(strip=True)
    except Exception as e:
        print(f"DEBUG: Erro ao extrair Nome do Mercado: {e}")
    print(f"DEBUG: Nome do Mercado extraído: '{market_name}'")

    # Data da Nota Fiscal
    invoice_date_str = None
    try:
        date_pattern = re.compile(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}')
        possible_date_parents = soup.find_all(['div', 'td', 'span'], string=re.compile("Data de Emissão", re.IGNORECASE))
        print(f"DEBUG: Encontrados {len(possible_date_parents)} elementos com 'Data de Emissão'.")
        if possible_date_parents:
            for parent in possible_date_parents:
                container = parent.find_parent(['div', 'tr']) or parent # Busca em container maior
                match = date_pattern.search(container.get_text(" ", strip=True))
                if match:
                    invoice_date_str = match.group(0)
                    print(f"DEBUG: Data encontrada via label 'Data de Emissão': '{invoice_date_str}'")
                    break
        # Fallback: busca geral (menos confiável)
        if not invoice_date_str:
            print("DEBUG: Buscando data de emissão via fallback (procurando padrão em Tds)...")
            all_text_nodes = soup.find_all(string=date_pattern) # Procura direto pelo padrão no texto
            if all_text_nodes:
                 invoice_date_str = all_text_nodes[0].strip()
                 print(f"DEBUG: Data encontrada via fallback (texto direto): '{invoice_date_str}'")
            else: # Fallback final em TDs
                 for td in soup.find_all('td'):
                    match = date_pattern.search(td.get_text(strip=True))
                    if match:
                        invoice_date_str = match.group(0)
                        print(f"DEBUG: Data encontrada via fallback (busca em Td): '{invoice_date_str}'")
                        break
    except Exception as e:
        print(f"DEBUG: Erro ao extrair Data da Nota: {e}")
    print(f"DEBUG: String final extraída para invoice_date: '{invoice_date_str}'")

    # Valor Total da Nota
    total_invoice_str = None
    try:
        total_label = soup.find(['strong', 'label', 'span', 'div'], string=re.compile(r'Valor\s+total\s+R?\$\s*:?', re.IGNORECASE))
        print(f"DEBUG: Label 'Valor total R$' encontrada: {total_label is not None}")
        if total_label:
            # Tenta encontrar o valor no próximo elemento relevante ou dentro do container
            possible_containers = [total_label.find_next(['div', 'span', 'td', 'strong']), total_label.find_parent(['div', 'tr'])]
            for container in possible_containers:
                if container:
                    strong_value = container.find('strong')
                    target_text = strong_value.get_text(strip=True) if strong_value else container.get_text(strip=True)
                    print(f"DEBUG: Tentando extrair valor total do texto: '{target_text}'")
                    match = re.search(r'([\d.,]+)', target_text) # Regex simples para o número
                    if match:
                        total_invoice_str = match.group(1)
                        print(f"DEBUG: Valor total encontrado: '{total_invoice_str}'")
                        break # Para no primeiro sucesso
            if not total_invoice_str:
                 print("DEBUG: Não foi possível encontrar valor total próximo à label.")
    except Exception as e:
        print(f"DEBUG: Erro ao extrair Valor Total: {e}")
    print(f"DEBUG: String final extraída para total_invoice: '{total_invoice_str}'")

    # --- Quantidade Total de Itens (Baseado no HTML Fornecido) ---
    quantity_total_items_str = None
    try:
        # 1. Encontra o <div> que contém o VALOR (baseado na classe do HTML)
        #    Usamos uma regex para a classe por segurança contra espaços extras
        value_div = soup.find('div', class_=re.compile(r'\bcol-lg-2\b')) # \b = word boundary

        print(f"DEBUG: Div do valor (class col-lg-2) encontrado: {value_div is not None}")

        if value_div:
            # 2. Tenta encontrar a tag <strong> dentro deste div
            value_strong = value_div.find('strong')
            print(f"DEBUG: Strong tag dentro do div do valor encontrada: {value_strong is not None}")

            if value_strong:
                # 3. Extrai o texto da tag <strong>
                raw_text = value_strong.get_text(strip=True)
                print(f"DEBUG: Texto cru da strong tag do valor: '{raw_text}'")

                # 4. Valida e extrai apenas se for um número inteiro
                match = re.search(r'^(\d+)$', raw_text)
                if match:
                    quantity_total_items_str = match.group(1)
                else:
                    print(f"DEBUG: Texto '{raw_text}' não parece ser um número inteiro.")
            else:
                 # Fallback: Se não houver <strong>, tenta pegar texto direto do div
                 raw_text = value_div.get_text(strip=True)
                 print(f"DEBUG: Texto cru do div do valor (fallback): '{raw_text}'")
                 match = re.search(r'^(\d+)$', raw_text)
                 if match:
                      quantity_total_items_str = match.group(1)
                 else:
                      print(f"DEBUG: Texto '{raw_text}' (fallback div) não parece ser um número inteiro.")
        else:
            print("DEBUG: Não foi encontrado o div com a classe 'col-lg-2' esperada para o valor.")

    except Exception as e:
        print(f"DEBUG: Erro ao extrair Quantidade Total de Itens: {e}")
        import traceback
        print(traceback.format_exc()) # Imprime traceback completo para erros

    print(f"DEBUG: String final extraída para quantity_total_items: '{quantity_total_items_str}'")
    # --- Fim da Extração de Quantidade Total ---

    # --- Chave de Acesso (Prioritizando Formatação do HTML) ---
    access_key = None
    formatted_key_found_in_html = False # Flag para indicar se encontramos no HTML

    try:
        print("DEBUG: Buscando chave de acesso FORMATADA no HTML PRIMEIRO...")

        # Estratégia: Encontrar texto que contenha dígitos E hífens/barras/pontos
        # É difícil ter uma regex perfeita sem ver mais HTML, então buscamos candidatos.
        # Procuramos em tags comuns onde a chave formatada pode estar exibida.
        potential_key_elements = soup.find_all(['span', 'td', 'div', 'strong', 'p'])
        print(f"DEBUG: Verificando {len(potential_key_elements)} elementos candidatos para chave formatada.")

        for element in potential_key_elements:
            # Pega o texto original, respeitando espaços entre tags internas se houver
            original_text = element.get_text(" ", strip=True)

            # Heurística para identificar um candidato a chave formatada:
            # - Contém dígitos?
            # - Contém pelo menos um dos separadores comuns?
            # - Tem um comprimento razoável (pelo menos 44 caracteres)?
            if (re.search(r'\d', original_text) and
                re.search(r'[-/\.]', original_text) and
                len(original_text) >= 44):

                print(f"DEBUG: Candidato a chave formatada encontrado no HTML: '{original_text}'")
                # Validação: Remover não-dígitos e verificar se tem 44 dígitos
                digits_only_html = re.sub(r'\D', '', original_text)
                if len(digits_only_html) == 44:
                    print(f"DEBUG: Candidato '{original_text}' contém 44 dígitos. Tentando extrair padrão formatado...")
                    # Tenta extrair APENAS o padrão formatado (dígitos e separadores)
                    # Regex busca por uma sequência que se pareça com a chave formatada
                    # (Começa com dígito, contém dígitos/pontos/barras/hífens, e tem comprimento substancial)
                    key_match = re.search(r'(\d[\d./-]{40,})', original_text) # Procura padrão começando com dígito, min ~40 chars
                    if key_match:
                        potential_key = key_match.group(1).strip()
                        # Valida se *este* padrão extraído também limpa para 44 dígitos (segurança extra)
                        if len(re.sub(r'\D', '', potential_key)) == 44:
                            access_key = potential_key # Armazena SOMENTE o padrão encontrado
                            formatted_key_found_in_html = True
                            print(f"DEBUG: Chave formatada EXTRAÍDA e validada do HTML: '{access_key}'")
                            break # Encontramos e extraímos, parar busca no HTML
                        else:
                             print(f"DEBUG: Padrão extraído '{potential_key}' não validou 44 dígitos. Tentando próximo elemento.")
                    else:
                        # Se a regex não pegou o padrão, talvez o prefixo seja o problema. Tentativa simples de remover:
                        prefix = "Chave de acesso "
                        if original_text.startswith(prefix):
                            cleaned_key = original_text[len(prefix):].strip()
                            # Revalida se o resto tem 44 dígitos
                            if len(re.sub(r'\D', '', cleaned_key)) == 44:
                                access_key = cleaned_key
                                formatted_key_found_in_html = True
                                print(f"DEBUG: Chave formatada encontrada no HTML (após remover prefixo): '{access_key}'")
                                break
                            else:
                                 print(f"DEBUG: Texto após remover prefixo '{cleaned_key}' não validou 44 digitos.")
                        else:
                             print(f"DEBUG: Não foi possível extrair padrão formatado específico de '{original_text}'.")
                else:
                     print(f"DEBUG: Candidato '{original_text}' não contém 44 dígitos após limpeza ('{digits_only_html}'). Continuando busca...")
        if not formatted_key_found_in_html:
            print("DEBUG: Chave formatada não encontrada/validada no HTML.")

        # ---------------------------------------------------------------------
        # Fallback/Validação usando o parâmetro QR Code
        # ---------------------------------------------------------------------
        print("DEBUG: Verificando parâmetro QR Code para fallback ou validação...")
        key_from_param = None
        digits_only_param = None
        param_is_valid = False

        if '|' in qr_code_parameter:
            key_from_param = qr_code_parameter.split('|')[0]
            digits_only_param = re.sub(r'\D', '', key_from_param)
            if len(digits_only_param) == 44:
                param_is_valid = True
                print(f"DEBUG: Parâmetro QR contém 44 dígitos ('{digits_only_param}'). Valor original: '{key_from_param}'")
            else:
                print(f"AVISO: Parâmetro QR não contém 44 dígitos após limpeza ('{digits_only_param}').")
        else:
            print(f"AVISO: Formato do qr_code_parameter inesperado: '{qr_code_parameter}'.")

        # Decisão final sobre qual chave usar:
        if formatted_key_found_in_html:
            # Já temos a chave formatada do HTML, usamos ela.
            # Opcional: Validar cruzado com o parâmetro se ele for válido
            if param_is_valid:
                digits_from_html_key = re.sub(r'\D', '', access_key)
                if digits_from_html_key != digits_only_param:
                    print(f"ALERTA GRANDE: Dígitos da chave formatada HTML ('{digits_from_html_key}') DIFEREM dos dígitos do parâmetro ('{digits_only_param}')!")
                    # Neste caso, talvez seja mais seguro usar a do parâmetro? Ou logar um erro grave?
                    # Por enquanto, vamos manter a do HTML que encontramos, mas com o alerta.
                    print(f"DEBUG: Mantendo a chave formatada do HTML encontrada: '{access_key}'")
                else:
                    print("DEBUG: Dígitos da chave HTML e parâmetro coincidem. Usando versão formatada do HTML.")
            else:
                print("DEBUG: Usando chave formatada encontrada no HTML (parâmetro inválido ou ausente).")

        elif param_is_valid:
            # Não achamos no HTML, mas o parâmetro é válido. Usamos o valor do parâmetro.
            access_key = key_from_param # Pode ter ou não formatação, dependendo do parâmetro
            print(f"AVISO: Usando chave do parâmetro QR ('{access_key}') pois a formatada não foi encontrada/validada no HTML.")

        else:
            # Falha total: Nem HTML nem parâmetro forneceram uma chave válida.
            access_key = None # Garante que é None
            print("ERRO FATAL: Não foi possível determinar uma chave de acesso válida nem no HTML nem no parâmetro QR.")
            # Considerar lançar HTTPException aqui


    except Exception as e:
        print(f"DEBUG: Erro CRÍTICO durante extração da Chave de Acesso: {e}")
        import traceback
        print(traceback.format_exc())

    # Log Final
    if access_key:
        print(f"DEBUG: Chave de acesso final a ser usada: '{access_key}'")
    else:
        # O erro fatal já foi logado acima.
        pass
    # --- Fim da Extração da Chave de Acesso ---

    # Extração dos Itens da Nota (Chamando a outra função)
    print("\n--- Iniciando Extração de Itens ---")
    invoice_items = extract_items_from_html(soup)
    print("--- Extração de Itens Concluída ---\n")

    # Cria o objeto Invoice usando Pydantic (validará e converterá os tipos)
    print("DEBUG: Criando objeto Invoice Pydantic...")
    try:
        invoice = Invoice(
            market_name=market_name,
            invoice_date=invoice_date_str, # Pydantic/dateutil fará o parse
            total_invoice=total_invoice_str, # Pydantic/parse_decimal fará o parse
            # Tenta converter a string para int, ou None se falhar ou for None
            quantity_total_items=int(quantity_total_items_str) if quantity_total_items_str else None,
            access_key=access_key,
            items=invoice_items # Lista já deve conter objetos ItemInvoice
        )
        print("DEBUG: Objeto Invoice Pydantic criado com sucesso.")
        # print(f"DEBUG: Conteúdo do objeto Invoice: {invoice.model_dump(exclude={'items'})}") # Opcional: Ver sem itens
    except Exception as e:
        print(f"ERRO ao criar o objeto Invoice Pydantic: {e}")
        # Importante lançar erro aqui, pois os dados podem estar inconsistentes
        raise HTTPException(status_code=500, detail=f"Erro ao processar os dados extraídos para criar a nota: {e}")

    # Salva no MongoDB (se a conexão estiver ativa e a nota não existir)
    print("DEBUG: Tentando salvar no MongoDB...")
    if mongo_client is not None and db is not None and invoices_collection is not None:
        await save_invoice_to_db(invoice)
    else:
        print("AVISO: Conexão com MongoDB não está disponível. Nota não será salva.")

    # Retorna o objeto Invoice (FastAPI o serializará para JSON)
    print("DEBUG: Retornando objeto Invoice.")
    return invoice

# --- Ponto de Entrada para rodar com Uvicorn ---
if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor Uvicorn em http://127.0.0.1:8000")
    # host="0.0.0.0" permite acesso externo se necessário
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)