# app.py
from flask import (Flask, render_template, jsonify, abort, url_for,
                   request, redirect, session, flash) # Adicionado redirect, session, flash
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson import json_util
from bson.objectid import ObjectId
import json
import math
from functools import wraps # Necessário para o decorador

app = Flask(__name__)
app.jinja_env.globals.update(min=min) # Adiciona min como global

# !!! IMPORTANTE: Defina uma chave secreta forte e única !!!
# Para produção, use algo realmente aleatório e guarde fora do código.
# Exemplo: import os; app.secret_key = os.urandom(24)
app.secret_key = 'teste' # TROQUE ISSO!

# --- Configuração MongoDB e Constantes ---
# ... (código existente: MONGO_URI, DB_NAME, etc.) ...
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "InvoicesDB"
COLLECTION_NAME = "Invoices"
PAGE_WINDOW = 2
ALLOWED_SORT_COLUMNS = {
    "date": "InvoiceDate",
    "quantity": "QuantityTotalItems",
    "total": "TotalInvoice"
}
DEFAULT_SORT_BY = "date"
DEFAULT_SORT_ORDER = "desc"
ALLOWED_LIMITS = [10, 25, 50, 100, 0]
DEFAULT_LIMIT = 10
# Credenciais Hardcoded (APENAS PARA DEMONSTRAÇÃO)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"


# --- Conexão MongoDB ---
# ... (código de conexão existente) ...
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.server_info()
    db = client[DB_NAME]
    invoices_collection = db[COLLECTION_NAME]
    print("Conexão com MongoDB estabelecida com sucesso!")
except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")
    invoices_collection = None
    db = None
    client = None

# --- Funções Auxiliares ---
def parse_json(data):
    return json.loads(json_util.dumps(data))

# --- Decorador de Login Obrigatório ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Por favor, faça login para acessar esta página.', 'warning')
            # Guarda a URL que o usuário tentou acessar para redirecionar após o login
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Rotas da Aplicação ---

# Rota de Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Se já estiver logado, redireciona para o index
    if 'logged_in' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username # Guarda o username na sessão (opcional)
            flash('Login realizado com sucesso!', 'success')
            # Verifica se há um parâmetro 'next' para redirecionar
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
            # Permanece na página de login para tentar novamente
            return render_template('login.html')

    # Se for GET, apenas mostra o formulário de login
    return render_template('login.html')

# Rota de Logout
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# Rota Principal (Protegida)
@app.route('/')
@login_required # Aplica o decorador
def index():
    # ... (código da rota index existente, sem alterações na lógica interna) ...
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
    return render_template('index.html', invoices=invoice_list, pagination=pagination, error=error_message)


# Rota de Detalhes (Protegida)
@app.route('/invoice/<invoice_id>')
@login_required # Aplica o decorador
def view_invoice(invoice_id):
    # ... (código da rota view_invoice existente, sem alterações na lógica interna) ...
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
    return render_template('details.html', invoice=invoice_data, error=error_message)

# --- Error Handlers (sem alterações) ---
@app.errorhandler(404)
def page_not_found(e):
    description = e.description if hasattr(e, 'description') else "Página não encontrada."
    # Adiciona verificação de login para mostrar link de logout ou login
    return render_template('404.html', error_description=description), 404

@app.errorhandler(503)
def service_unavailable(e):
    description = e.description if hasattr(e, 'description') else "Serviço temporariamente indisponível."
    return render_template('503.html', error_description=description), 503

# --- Execução ---
if __name__ == '__main__':
    app.run(debug=True) # Mantenha debug=True por enquanto