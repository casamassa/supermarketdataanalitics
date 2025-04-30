# app.py
from flask import Flask, render_template, jsonify, abort, url_for, request, redirect, flash, make_response
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson import json_util
from bson.objectid import ObjectId
import json
import math
from datetime import timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    JWTManager, get_jwt_identity, unset_jwt_cookies, set_access_cookies, set_refresh_cookies,
    get_current_user # Importado se for usar get_current_user
)
# Importar erros específicos se for tratar separadamente (opcional)
# from flask_jwt_extended.exceptions import NoAuthorizationError

from dotenv import load_dotenv
import os

load_dotenv() # Carrega variáveis do arquivo .env para o ambiente

# --- Obter configurações do ambiente ---
FLASK_SECRET = os.getenv('FLASK_SECRET_KEY')
JWT_SECRET = os.getenv('JWT_SECRET_KEY')
# Usar um valor padrão para MONGO_URI se não estiver no .env (útil para dev local)
MONGO_URI_ENV = os.getenv('MONGO_URI', 'mongodb://localhost:27017')

# Validar se as chaves secretas foram carregadas
if not FLASK_SECRET:
    raise ValueError("Erro: FLASK_SECRET_KEY não definida no arquivo .env")
if not JWT_SECRET:
    raise ValueError("Erro: JWT_SECRET_KEY não definida no arquivo .env")
if MONGO_URI_ENV == 'mongodb://localhost:27017' and not os.getenv('MONGO_URI'):
    print("Aviso: MONGO_URI não encontrada no .env, usando valor padrão 'mongodb://localhost:27017'")

app = Flask(__name__)

# --- Configuração Flask Session (NECESSÁRIO PARA FLASH) ---
# !!! IMPORTANTE: Use uma chave secreta forte e única !!!
# Para produção, use algo realmente aleatório e guarde fora do código.
# Exemplo no console Python: import os; os.urandom(24).hex()
app.secret_key = FLASK_SECRET

# --- Configuração JWT ---
# Pode ser a mesma chave do Flask ou uma diferente
app.config["JWT_SECRET_KEY"] = JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(minutes=30)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_CSRF_PROTECT"] = True
# Verifique se FLASK_ENV é production para habilitar cookie seguro
if os.getenv('FLASK_ENV') == 'production':
     app.config["JWT_COOKIE_SECURE"] = True # Descomente em produção (HTTPS)
     app.config["JWT_COOKIE_SAMESITE"] = "Lax" # Ou "Strict"

jwt = JWTManager(app)

# --- Configuração MongoDB e Constantes ---
MONGO_URI = MONGO_URI_ENV
DB_NAME = "InvoicesDB"
COLLECTION_NAME = "Invoices"
USERS_COLLECTION_NAME = "Users" # Nova collection para usuários
PAGE_WINDOW = 2
ALLOWED_SORT_COLUMNS = { "date": "InvoiceDate", "quantity": "QuantityTotalItems", "total": "TotalInvoice" }
DEFAULT_SORT_BY = "date"
DEFAULT_SORT_ORDER = "desc"
ALLOWED_LIMITS = [10, 25, 50, 100, 0]
DEFAULT_LIMIT = 10

# --- Conexão MongoDB ---
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client[DB_NAME]
    invoices_collection = db[COLLECTION_NAME]
    users_collection = db[USERS_COLLECTION_NAME] # Acessa a collection de usuários
    print("Conexão com MongoDB estabelecida com sucesso!")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")
    invoices_collection = None
    users_collection = None
    db = None
    client = None

# --- Funções Auxiliares ---
def parse_json(data):
    return json.loads(json_util.dumps(data))

# --- Funções de Carregamento de Usuário para JWT ---
# Define qual informação do seu objeto usuário será usada como 'identity' no token
@jwt.user_identity_loader
def user_identity_lookup(user):
    return str(user["_id"]) # Usando o _id do MongoDB como identidade

# Define como carregar o objeto usuário completo a partir da 'identity' do token
# Isso é útil se você precisar dos dados do usuário em rotas protegidas
@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    if users_collection is not None: # <-- CORREÇÃO: Verifica explicitamente contra None
         # Retorna o objeto usuário (ou None se não encontrado)
        return users_collection.find_one({"_id": ObjectId(identity)})
    # Se users_collection for None (erro de conexão inicial), retorna None
    return None

# --- Rotas de Autenticação ---

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Renderiza a página de login (GET)"""
    # Se estiver usando cookies, a verificação de 'já logado' é feita pelo @jwt_required nas rotas protegidas
    # Podemos redirecionar se um cookie de acesso válido existir, mas é opcional
    # try:
    #     verify_jwt_in_request(locations=['cookies'])
    #     return redirect(url_for('index')) # Já logado, vai pro index
    # except NoAuthorizationError:
    #     pass # Não logado, continua para mostrar o form
    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    """Processa o login e retorna tokens (via cookies)"""
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    if not username or not password:
        return jsonify({"msg": "Usuário e senha são obrigatórios"}), 400

    if users_collection is None: # Verifica explicitamente se é None
         return jsonify({"msg": "Erro interno: não foi possível conectar ao banco de usuários"}), 500

    user = users_collection.find_one({"username": username})

    # Verifica se usuário existe e se a senha está correta
    if user and check_password_hash(user["password_hash"], password):
        # Cria os tokens usando o objeto usuário encontrado
        access_token = create_access_token(identity=user)
        refresh_token = create_refresh_token(identity=user)

        # Cria uma resposta JSON (pode ser só de sucesso)
        response = jsonify({"msg": "Login bem-sucedido"})
        # Define os cookies JWT na resposta
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)
        return response, 200
    else:
        return jsonify({"msg": "Credenciais inválidas"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """Desloga o usuário limpando os cookies JWT"""
    response = jsonify({"msg": "Logout bem-sucedido"})
    unset_jwt_cookies(response) # Remove os cookies
    return response, 200

# Flask-JWT-Extended pode lidar com refresh automaticamente se configurado
# Opcional: endpoint explícito para refresh, se necessário
@app.route("/api/refresh", methods=["POST"])
@jwt_required(refresh=True) # Requer um refresh token válido
def api_refresh():
    current_user_identity = get_jwt_identity() # Pega a identidade do refresh token
    # Cria um *novo* access token. A identidade pode ser str ou objeto dependendo do loader
    # Se user_identity_loader retorna str(id), buscamos o user para passar ao create_access_token
    user_object = users_collection.find_one({"_id": ObjectId(current_user_identity)})
    if not user_object:
         return jsonify({"msg": "Usuário não encontrado para refresh"}), 404
         
    new_access_token = create_access_token(identity=user_object)
    response = jsonify({"msg":"Token de acesso atualizado"})
    set_access_cookies(response, new_access_token) # Define apenas o novo cookie de acesso
    return response, 200

# --- Rotas Principais (Protegidas) ---

@app.route('/')
@jwt_required() # Protege a rota, requer um Access Token válido (via cookie)
def index():
    # --- Obter o usuário atual ---
    current_user = get_current_user() # Pega o objeto do usuário carregado pelo user_lookup_loader
    # Extrai o username (com segurança, caso current_user seja None ou não tenha 'username')
    username = current_user.get('username') if current_user else None
    # --- Fim da obtenção do usuário ---
    invoice_list = []
    error_message = None
    pagination = {
        "page": 1, "total_pages": 0, "has_prev": False, "has_next": False,
        "total_items": 0, "page_numbers": [], "sort_by": DEFAULT_SORT_BY,
        "sort_order": DEFAULT_SORT_ORDER, "limit": DEFAULT_LIMIT
    }
    if invoices_collection is not None:
        try:
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            pagination['page'] = page
            limit = request.args.get('limit', DEFAULT_LIMIT, type=int)
            if limit not in ALLOWED_LIMITS: limit = DEFAULT_LIMIT
            pagination['limit'] = limit
            items_per_page = limit if limit > 0 else float('inf')
            sort_by_key = request.args.get('sort_by', DEFAULT_SORT_BY).lower()
            sort_order = request.args.get('sort_order', DEFAULT_SORT_ORDER).lower()
            if sort_by_key not in ALLOWED_SORT_COLUMNS: sort_by_key = DEFAULT_SORT_BY
            pagination['sort_by'] = sort_by_key
            mongo_sort_field = ALLOWED_SORT_COLUMNS[sort_by_key]
            if sort_order not in ['asc', 'desc']: sort_order = DEFAULT_SORT_ORDER
            pagination['sort_order'] = sort_order
            mongo_sort_direction = ASCENDING if sort_order == 'asc' else DESCENDING
            total_invoices = invoices_collection.count_documents({})
            pagination['total_items'] = total_invoices
            if total_invoices > 0:
                skip_count = (page - 1) * limit if limit > 0 else 0
                if limit > 0: total_pages = math.ceil(total_invoices / limit)
                else: total_pages = 1
                pagination['total_pages'] = total_pages
                if page > total_pages:
                    page = total_pages
                    skip_count = (page - 1) * limit if limit > 0 else 0
                    pagination['page'] = page
                query = invoices_collection.find().sort([(mongo_sort_field, mongo_sort_direction)])
                if limit > 0: query = query.skip(skip_count).limit(limit)
                cursor = query
                raw_invoices = list(cursor)
                invoice_list = parse_json(raw_invoices)
                pagination['has_prev'] = page > 1
                pagination['has_next'] = page < total_pages
                if total_pages > 1:
                    start_page = max(1, page - PAGE_WINDOW)
                    end_page = min(total_pages, page + PAGE_WINDOW)
                    if page - PAGE_WINDOW < 1: end_page = min(total_pages, end_page + (PAGE_WINDOW - (page - 1)))
                    if page + PAGE_WINDOW > total_pages: start_page = max(1, start_page - (PAGE_WINDOW - (total_pages - page)))
                    pagination['page_numbers'] = list(range(start_page, end_page + 1))
                else: pagination['page_numbers'] = []
            else: pagination['total_pages'] = 0
        except Exception as e:
            error_message = f"Erro ao buscar dados do MongoDB: {e}"
            print(error_message)
    else: error_message = "Não foi possível conectar ao banco de dados MongoDB."
    # Passa a informação se o usuário está logado (verificado pelo @jwt_required)
    # Ou obtem dados do usuário se necessário: current_user = get_current_user()
    return render_template('index.html', invoices=invoice_list, pagination=pagination, error=error_message, username=username)


@app.route('/invoice/<invoice_id>')
@jwt_required() # Protege a rota
def view_invoice(invoice_id):
    # ... (código da rota view_invoice existente) ...
    # --- Obter o usuário atual ---
    current_user = get_current_user()
    username = current_user.get('username') if current_user else None
    # --- Fim da obtenção do usuário ---
    invoice_data = None
    error_message = None
    if invoices_collection is not None:
        try:
            obj_id = ObjectId(invoice_id)
            raw_invoice = invoices_collection.find_one({"_id": obj_id})
            if raw_invoice: invoice_data = parse_json(raw_invoice)
            else: abort(404, description="Invoice não encontrada")
        except Exception as e:
            error_message = f"Erro ao buscar detalhes da invoice: {e}"
            print(error_message)
            abort(404, description=f"Erro ao buscar ou ID inválido: {invoice_id}")
    else:
        error_message = "Não foi possível conectar ao banco de dados MongoDB."
        abort(503, description="Serviço indisponível (DB Connection Error)")
    return render_template('details.html', invoice=invoice_data, error=error_message, username=username)

# --- Error Handlers ---
# Custom error handler para redirecionar para login em caso de 401 (não autorizado)
# Flask-JWT-Extended faz isso automaticamente se `login_url` for configurado,
# ou podemos customizar
@jwt.unauthorized_loader
def unauthorized_callback(reason):
    flash('Acesso não autorizado. Por favor, faça login.', 'warning')
    return redirect(url_for('login_page', next=request.url))

@jwt.invalid_token_loader
def invalid_token_callback(reason):
    flash('Token inválido ou expirado. Por favor, faça login novamente.', 'warning')
    response = make_response(redirect(url_for('login_page')))
    unset_jwt_cookies(response) # Limpa cookies inválidos
    return response

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
     # Se o token expirado for um access token, podemos tentar usar o refresh token
     # Mas para simplificar a UI, vamos apenas redirecionar para login
    flash('Sua sessão expirou. Por favor, faça login novamente.', 'warning')
    response = make_response(redirect(url_for('login_page', next=request.url)))
    unset_jwt_cookies(response) # Limpa cookies expirados
    return response

@app.errorhandler(404)
def page_not_found(e):
    description = e.description if hasattr(e, 'description') else "Página não encontrada."
    return render_template('404.html', error_description=description), 404

@app.errorhandler(503)
def service_unavailable(e):
    description = e.description if hasattr(e, 'description') else "Serviço temporariamente indisponível."
    return render_template('503.html', error_description=description), 503

# --- Função para Criar Usuário (Executar uma vez ou via um script separado) ---
def create_admin_user():
    if users_collection is None:
        print("Não foi possível conectar à collection de usuários.")
        return

    # Verifica se o admin já existe
    if users_collection.find_one({"username": "admin"}):
        print("Usuário 'admin' já existe.")
        return

    # Cria o hash da senha
    password = os.getenv('INITALPWDADMIN') # Senha inicial (usuário deve trocar!)
    hashed_password = generate_password_hash(password)

    # Insere o usuário
    try:
        user_id = users_collection.insert_one({
            "username": "admin",
            "password_hash": hashed_password,
            "roles": ["admin"] # Exemplo de campo de roles
        }).inserted_id
        print(f"Usuário 'admin' criado com ID: {user_id}")
    except Exception as e:
        print(f"Erro ao criar usuário 'admin': {e}")

# --- Execução ---
if __name__ == '__main__':
    # Descomente a linha abaixo APENAS UMA VEZ para criar o usuário admin
    # create_admin_user()
    app.run(debug=True)