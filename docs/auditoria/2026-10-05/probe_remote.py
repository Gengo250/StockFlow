"""Leitura anônima: sem login e sem executar funções de escrita."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'src'))
from stockflow.infrastructure.database.supabase_client import get_client

ZERO = '00000000-0000-0000-0000-000000000000'
client = get_client()
checks = []
tables = {
    'products': 'id,supplier_id,stock',
    'categories': 'id',
    'product_stock': 'product_id,min_quantity',
    'company': 'id',
    'stock_movements': 'id,supplier_id,status',
    'clients': 'id',
    'sales': 'id',
    'suppliers': 'id',
    'vw_stock_alerts': 'product_code,current_balance,min_quantity,state',
    'vw_stock_situation': 'product_id',
}
for table, columns in tables.items():
    try:
        client.table(table).select(columns).limit(0).execute()
        state = 'consulta anonima permitida; RLS/conteudo nao comprovados'
        code = 'HTTP sucesso'
    except Exception as error:
        code = str(getattr(error, 'code', type(error).__name__))
        state = ('bloqueado para anonimo' if code == '42501' else
                 'ausente no schema cache' if code in ('PGRST205', 'PGRST202') else
                 'erro de contrato' if code == '42703' else 'inconclusivo')
    checks.append({'object': table, 'kind': 'table/view', 'result': state, 'code': code})

for function, args in (
    ('fn_current_user_id', {}),
    ('fn_my_companies', {}),
    ('fn_list_company_users', {'p_company_id': ZERO}),
    ('fn_list_company_clients', {'p_company_id': ZERO, 'p_search': None}),
    ('fn_list_company_suppliers', {'p_company_id': ZERO, 'p_search': None}),
):
    try:
        client.rpc(function, args).execute()
        state, code = 'executavel por anonimo', 'HTTP sucesso'
    except Exception as error:
        code = str(getattr(error, 'code', type(error).__name__))
        state = ('bloqueado para anonimo' if code == '42501' else
                 'ausente no schema cache' if code == 'PGRST202' else 'inconclusivo')
    checks.append({'object': function, 'kind': 'read_rpc', 'result': state, 'code': code})

out = Path('/tmp/stockflow-audit-20261005/remote-anonymous.json')
out.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
for c in checks:
    print(f"{c['object']}: {c['result']} ({c['code']})")
