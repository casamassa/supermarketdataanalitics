# app.py
from flask import Flask, render_template, jsonify, abort, url_for, request
from pymongo import MongoClient, DESCENDING, ASCENDING
from bson import json_util
from bson.objectid import ObjectId
import json
import math

app = Flask(__name__)
app.jinja_env.globals.update(min=min) # Adiciona min como global

# --- Configuração ---
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "InvoicesDB"
COLLECTION_NAME = "Invoices"
# ITEMS_PER_PAGE = 10 # Removido - agora é dinâmico
PAGE_WINDOW = 2
ALLOWED_SORT_COLUMNS = {
    "date": "InvoiceDate",
    "quantity": "QuantityTotalItems",
    "total": "TotalInvoice"
}
DEFAULT_SORT_BY = "date"
DEFAULT_SORT_ORDER = "desc"
ALLOWED_LIMITS = [10, 25, 50, 100, 0] # 0 representa "Todos"
DEFAULT_LIMIT = 10

# --- Conexão MongoDB ---
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

# --- Rotas da Aplicação ---
@app.route('/')
def index():
    invoice_list = []
    error_message = None
    pagination = {
        "page": 1,
        "total_pages": 0,
        "has_prev": False,
        "has_next": False,
        "total_items": 0,
        "page_numbers": [],
        "sort_by": DEFAULT_SORT_BY,
        "sort_order": DEFAULT_SORT_ORDER,
        "limit": DEFAULT_LIMIT # Adicionado 'limit'
    }

    if invoices_collection is not None:
        try:
            # --- Paginação ---
            page = request.args.get('page', 1, type=int)
            if page < 1: page = 1
            pagination['page'] = page

            # --- Limite de Itens por Página ---
            limit = request.args.get('limit', DEFAULT_LIMIT, type=int)
            if limit not in ALLOWED_LIMITS:
                limit = DEFAULT_LIMIT
            # Se limit for 0 (Todos), PyMongo entende como sem limite.
            pagination['limit'] = limit
            items_per_page = limit if limit > 0 else float('inf') # Para cálculos, use infinito se for 'Todos'

            # --- Ordenação ---
            sort_by_key = request.args.get('sort_by', DEFAULT_SORT_BY).lower()
            sort_order = request.args.get('sort_order', DEFAULT_SORT_ORDER).lower()
            if sort_by_key not in ALLOWED_SORT_COLUMNS: sort_by_key = DEFAULT_SORT_BY
            pagination['sort_by'] = sort_by_key
            mongo_sort_field = ALLOWED_SORT_COLUMNS[sort_by_key]
            if sort_order not in ['asc', 'desc']: sort_order = DEFAULT_SORT_ORDER
            pagination['sort_order'] = sort_order
            mongo_sort_direction = ASCENDING if sort_order == 'asc' else DESCENDING

            # --- Consulta ao Banco ---
            # A contagem total não depende do limite da página
            total_invoices = invoices_collection.count_documents({})
            pagination['total_items'] = total_invoices

            if total_invoices > 0:
                # Calcular skip apenas se não estivermos mostrando todos ou se houver limite
                skip_count = (page - 1) * limit if limit > 0 else 0

                # Calcular total_pages baseado no limite (se houver)
                if limit > 0:
                    total_pages = math.ceil(total_invoices / limit)
                else: # Se limit é 0 (Todos), só há 1 página
                    total_pages = 1
                pagination['total_pages'] = total_pages

                # Ajustar página se for maior que o total (considerando o limit)
                if page > total_pages:
                    page = total_pages
                    skip_count = (page - 1) * limit if limit > 0 else 0
                    pagination['page'] = page

                # Montar a query
                query = invoices_collection.find().sort([(mongo_sort_field, mongo_sort_direction)])
                
                # Aplicar skip e limit se limit não for 0 ('Todos')
                if limit > 0:
                    query = query.skip(skip_count).limit(limit)
                # Se limit for 0, não aplicamos skip nem limit, pegamos tudo ordenado

                cursor = query
                raw_invoices = list(cursor)
                invoice_list = parse_json(raw_invoices)

                # Definir has_prev e has_next baseado na página atual e total_pages
                pagination['has_prev'] = page > 1
                pagination['has_next'] = page < total_pages

                # Calcular range de páginas apenas se houver mais de uma página
                if total_pages > 1:
                    start_page = max(1, page - PAGE_WINDOW)
                    end_page = min(total_pages, page + PAGE_WINDOW)
                    if page - PAGE_WINDOW < 1: end_page = min(total_pages, end_page + (PAGE_WINDOW - (page - 1)))
                    if page + PAGE_WINDOW > total_pages: start_page = max(1, start_page - (PAGE_WINDOW - (total_pages - page)))
                    pagination['page_numbers'] = list(range(start_page, end_page + 1))
                else:
                    pagination['page_numbers'] = [] # Sem números se só há uma página

            else: # total_invoices == 0
                pagination['total_pages'] = 0

        except Exception as e:
            error_message = f"Erro ao buscar dados do MongoDB: {e}"
            print(error_message)
    else:
        error_message = "Não foi possível conectar ao banco de dados MongoDB."

    return render_template('index.html',
                           invoices=invoice_list,
                           pagination=pagination,
                           error=error_message)

# --- Rota de Detalhes e Error Handlers (sem alterações) ---
@app.route('/invoice/<invoice_id>')
def view_invoice(invoice_id):
    invoice_data = None
    error_message = None
    if invoices_collection is not None:
        try:
            obj_id = ObjectId(invoice_id)
            raw_invoice = invoices_collection.find_one({"_id": obj_id})
            if raw_invoice:
                invoice_data = parse_json(raw_invoice)
            else:
                abort(404, description="Invoice não encontrada")
        except Exception as e:
            error_message = f"Erro ao buscar detalhes da invoice: {e}"
            print(error_message)
            abort(404, description=f"Erro ao buscar ou ID inválido: {invoice_id}")
    else:
        error_message = "Não foi possível conectar ao banco de dados MongoDB."
        abort(503, description="Serviço indisponível (DB Connection Error)")
    return render_template('details.html', invoice=invoice_data, error=error_message)

@app.errorhandler(404)
def page_not_found(e):
    description = e.description if hasattr(e, 'description') else "Página não encontrada."
    return render_template('404.html', error_description=description), 404

@app.errorhandler(503)
def service_unavailable(e):
    description = e.description if hasattr(e, 'description') else "Serviço temporariamente indisponível."
    return render_template('503.html', error_description=description), 503

# --- Execução ---
if __name__ == '__main__':
    app.run(debug=True)