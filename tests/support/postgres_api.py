"""Small PostgREST-shaped adapter for exercising Qt against real local PostgreSQL.

Only used by scripts/verify_postgres.py. Does not simulate SQL functions or RLS.
"""
from types import SimpleNamespace

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class PostgresAPI:
    def __init__(self, connection):
        self.connection = connection

    def table(self, name):
        return Query(self.connection, name)

    def rpc(self, name, args):
        return RPC(self.connection, name, args)


class Query:
    def __init__(self, connection, table):
        self.connection, self.table = connection, table
        self.fields, self.filters, self.values = '*', [], []
        self.sort, self.count = None, None

    def select(self, fields):
        self.fields = fields
        return self

    def eq(self, key, value):
        self.filters.append(sql.SQL('{} = %s').format(sql.Identifier(key)))
        self.values.append(value)
        return self

    def in_(self, key, values):
        self.filters.append(sql.SQL('{}::text = ANY(%s)').format(sql.Identifier(key)))
        self.values.append(list(map(str, values)))
        return self

    def order(self, key, desc=False):
        self.sort = sql.SQL('{} {}').format(sql.Identifier(key), sql.SQL('DESC' if desc else 'ASC'))
        return self

    def limit(self, count):
        self.count = count
        return self

    def execute(self):
        fields = sql.SQL('*') if self.fields == '*' else sql.SQL(',').join(map(sql.Identifier, self.fields.split(',')))
        query = sql.SQL('SELECT {} FROM public.{}').format(fields, sql.Identifier(self.table))
        if self.filters:
            query += sql.SQL(' WHERE ') + sql.SQL(' AND ').join(self.filters)
        if self.sort:
            query += sql.SQL(' ORDER BY ') + self.sort
        if self.count is not None:
            query += sql.SQL(' LIMIT {}').format(sql.Literal(self.count))
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, self.values)
            return SimpleNamespace(data=[{k: str(v) if type(v).__name__ == 'UUID' else v for k,v in row.items()} for row in cursor.fetchall()])


class RPC:
    def __init__(self, connection, name, args):
        self.connection, self.name, self.args = connection, name, args

    def execute(self):
        arguments = sql.SQL(',').join(sql.SQL('{} => %s').format(sql.Identifier(k)) for k in self.args)
        values = [Jsonb(v) if isinstance(v, dict) else v for v in self.args.values()]
        query = sql.SQL('SELECT * FROM public.{}({})').format(sql.Identifier(self.name), arguments)
        with self.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, values)
            rows = [{k: str(v) if type(v).__name__ == 'UUID' else v for k,v in row.items()} for row in cursor.fetchall()]
        if rows and list(rows[0]) == [self.name]:
            return SimpleNamespace(data=rows[0][self.name])
        return SimpleNamespace(data=rows)
