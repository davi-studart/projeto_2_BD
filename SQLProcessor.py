from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict
import copy
import re
import networkx as nx

SCHEMA = {
    "Categoria": ["idCategoria", "Descricao"],
    "Produto": ["idProduto", "Nome", "Descricao", "Preco", "QuantEstoque", "Categoria_idCategoria"],
    "TipoCliente": ["idTipoCliente", "Descricao"],
    "Cliente": ["idCliente", "Nome", "Email", "Nascimento", "Senha", "TipoCliente_idTipoCliente", "DataRegistro"],
    "TipoEndereco": ["idTipoEndereco", "Descricao"],
    "Endereco": ["idEndereco", "EnderecoPadrao", "Logradouro", "Numero", "Complemento", "Bairro", "Cidade", "UF", "CEP", "TipoEndereco_idTipoEndereco", "Cliente_idCliente"],
    "Telefone": ["Numero", "Cliente_idCliente"],
    "Status": ["idStatus", "Descricao"],
    "Pedido": ["idPedido", "Status_idStatus", "DataPedido", "ValorTotalPedido", "Cliente_idCliente"],
    "Pedido_has_Produto": ["idPedidoProduto", "Pedido_idPedido", "Produto_idProduto", "Quantidade", "PrecoUnitario"],
}

@dataclass
class Condition:
    left: str
    op: str
    right: str
    connector: str = "AND"

@dataclass
class JoinClause:
    table: str
    left: str
    op: str
    right: str

@dataclass
class QueryData:
    select_fields: List[str]
    from_table: str
    joins: List[JoinClause] = field(default_factory=list)
    where_conditions: List[Condition] = field(default_factory=list)

class SQLProcessor:
    def __init__(self):
        self.schema = SCHEMA

    def parse(self, sql: str) -> QueryData:
        sql = re.sub(r"\s+", " ", sql.strip()).rstrip(";")
        pattern = re.compile(
            r"^SELECT\s+(?P<select>.+?)\s+FROM\s+(?P<from>[A-Za-z_][A-Za-z0-9_]*)"
            r"(?P<joins>(?:\s+INNER\s+JOIN\s+[A-Za-z_][A-Za-z0-9_]*\s+ON\s+.+?)*)"
            r"(?:\s+WHERE\s+(?P<where>.+))?$",
            re.IGNORECASE,
        )
        match = pattern.match(sql)
        if not match:
            raise ValueError("Consulta SQL fora do padrão suportado: SELECT ... FROM ... [INNER JOIN ... ON ...] [WHERE ...]")

        query = QueryData(
            select_fields=[item.strip() for item in match.group("select").split(",")],
            from_table=match.group("from"),
            joins=self._parse_joins(match.group("joins") or ""),
            where_conditions=self._parse_where(match.group("where") or ""),
        )
        self._validate(query)
        return query

    def _parse_joins(self, joins_text: str) -> List[JoinClause]:
        joins = []
        if not joins_text:
            return joins
        join_pattern = re.compile(
            r"INNER\s+JOIN\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+([A-Za-z_][A-Za-z0-9_\.]*?)\s*(=|<>|<=|>=|<|>)\s*([A-Za-z_][A-Za-z0-9_\.]*)",
            re.IGNORECASE,
        )
        for table, left, op, right in join_pattern.findall(joins_text):
            joins.append(JoinClause(table=table, left=left, op=op, right=right))
        if not joins:
            raise ValueError("INNER JOIN encontrado, mas não foi possível analisar as cláusulas ON.")
        return joins

    def _parse_where(self, where_text: str) -> List[Condition]:
        conditions = []
        if not where_text:
            return conditions
        tokens = re.split(r"\s+(AND)\s+", where_text, flags=re.IGNORECASE)
        connector = "AND"
        for token in tokens:
            if not token:
                continue
            if token.upper() == "AND":
                connector = "AND"
                continue
            cleaned = token.strip().replace("(", "").replace(")", "")
            m = re.match(r"(.+?)\s*(=|<>|<=|>=|<|>)\s*(.+)", cleaned)
            if not m:
                raise ValueError(f"Condição WHERE inválida: {token}")
            left, op, right = [x.strip() for x in m.groups()]
            conditions.append(Condition(left=left, op=op, right=right, connector=connector))
        return conditions

    def _validate(self, query: QueryData):
        tables = [query.from_table] + [j.table for j in query.joins]
        for table in tables:
            if table not in self.schema:
                raise ValueError(f"Tabela inválida: {table}")
        for field in query.select_fields:
            if field != "*":
                self._validate_field_ref(field, tables)
        for join in query.joins:
            self._validate_field_ref(join.left, tables)
            self._validate_field_ref(join.right, tables)
        for cond in query.where_conditions:
            self._validate_operand(cond.left, tables)
            self._validate_operand(cond.right, tables, allow_literal=True)

    def _validate_operand(self, operand: str, tables: List[str], allow_literal: bool = False):
        if allow_literal and self._is_literal(operand):
            return
        self._validate_field_ref(operand, tables)

    def _validate_field_ref(self, ref: str, tables: List[str]):
        if "." in ref:
            table, field = ref.split(".", 1)
            if table not in self.schema:
                raise ValueError(f"Tabela no campo não existe: {table}")
            if field not in self.schema[table]:
                raise ValueError(f"Campo inválido: {ref}")
        else:
            matches = [t for t in tables if ref in self.schema.get(t, [])]
            if len(matches) == 0:
                raise ValueError(f"Campo inválido: {ref}")
            if len(matches) > 1:
                raise ValueError(f"Campo ambíguo: {ref}. Use tabela.campo")

    def _is_literal(self, value: str) -> bool:
        return bool(re.fullmatch(r"'[^']*'|\d+(?:\.\d+)?", value))

    def _table_from_operand(self, operand: str) -> str | None:
        if "." in operand:
            return operand.split(".", 1)[0]
        return None

    def _conditions_for_table(self, query: QueryData, table: str) -> List[Condition]:
        result = []
        for cond in query.where_conditions:
            left_table = self._table_from_operand(cond.left)
            right_table = self._table_from_operand(cond.right)
            tables = {t for t in [left_table, right_table] if t}
            if not tables or tables == {table}:
                result.append(cond)
        return result

    def _fields_for_table(self, query: QueryData, table: str) -> List[str]:
        needed: Set[str] = set()
        if query.select_fields == ["*"]:
            return self.schema[table][:]
        for field in query.select_fields:
            if "." in field:
                t, c = field.split(".", 1)
                if t == table:
                    needed.add(c)
            elif field in self.schema.get(table, []):
                needed.add(field)
        for cond in query.where_conditions:
            for operand in [cond.left, cond.right]:
                if "." in operand:
                    t, c = operand.split(".", 1)
                    if t == table and c in self.schema[table]:
                        needed.add(c)
        for join in query.joins:
            for operand in [join.left, join.right]:
                if "." in operand:
                    t, c = operand.split(".", 1)
                    if t == table and c in self.schema[table]:
                        needed.add(c)
        if not needed:
            needed.update(self.schema[table])
        return sorted(needed)

    def relational_algebra(self, query: QueryData) -> str:
        expr = query.from_table
        for join in query.joins:
            expr = f"({expr} ⋈[{join.left} {join.op} {join.right}] {join.table})"
        if query.where_conditions:
            conds = " AND ".join(f"{c.left} {c.op} {c.right}" for c in query.where_conditions)
            expr = f"σ[{conds}]({expr})"
        if query.select_fields != ["*"]:
            expr = f"π[{', '.join(query.select_fields)}]({expr})"
        return expr

    def optimized_relational_algebra(self, query: QueryData) -> str:
        branch_exprs: Dict[str, str] = {}
        tables = [query.from_table] + [j.table for j in query.joins]
        for table in tables:
            expr = table
            if query.select_fields != ["*"]:
                expr = f"π[{', '.join(self._fields_for_table(query, table))}]({expr})"
            table_conds = self._conditions_for_table(query, table)
            if table_conds:
                cond_text = " AND ".join(f"{c.left} {c.op} {c.right}" for c in table_conds)
                expr = f"σ[{cond_text}]({expr})"
            branch_exprs[table] = expr

        expr = branch_exprs[query.from_table]
        for join in query.joins:
            expr = f"({expr} ⋈[{join.left} {join.op} {join.right}] {branch_exprs[join.table]})"
        if query.select_fields != ["*"]:
            expr = f"π[{', '.join(query.select_fields)}]({expr})"
        return expr

    def optimize(self, query: QueryData) -> Tuple[List[str], QueryData, str]:
        optimized = copy.deepcopy(query)
        steps = []
        if optimized.select_fields != ["*"]:
            steps.append("1. Aplicar projeções antecipadas nas tabelas para reduzir atributos intermediários.")
        if optimized.where_conditions:
            optimized.where_conditions.sort(key=self._condition_weight, reverse=True)
            steps.append("2. Aplicar seleções (WHERE) em cada ramo antes das junções para reduzir tuplas.")
        if optimized.joins:
            optimized.joins.sort(key=self._join_weight, reverse=True)
            steps.append("3. Executar junções após projeções e seleções, priorizando as mais restritivas.")
        return steps, optimized, self.optimized_relational_algebra(optimized)

    def _condition_weight(self, cond: Condition) -> int:
        return 3 if cond.op == "=" else 2

    def _join_weight(self, join: JoinClause) -> int:
        return 3 if join.op == "=" else 1

    def build_plan(self, query: QueryData, optimized: bool = False) -> List[str]:
        plan = []
        if optimized and query.select_fields != ["*"]:
            plan.append(f"Aplicar projeção inicial em {query.from_table}: {', '.join(self._fields_for_table(query, query.from_table))}.")
            for join in query.joins:
                plan.append(f"Aplicar projeção inicial em {join.table}: {', '.join(self._fields_for_table(query, join.table))}.")
        else:
            plan.append(f"Ler tabela base {query.from_table}.")

        if not optimized:
            current_source = query.from_table
            for join in query.joins:
                plan.append(f"Executar INNER JOIN entre {current_source} e {join.table} usando {join.left} {join.op} {join.right}.")
                current_source = f"resultado parcial + {join.table}"
            for cond in query.where_conditions:
                plan.append(f"Aplicar seleção após as junções: {cond.left} {cond.op} {cond.right}.")
        else:
            processed_tables = [query.from_table] + [j.table for j in query.joins]
            for table in processed_tables:
                for cond in self._conditions_for_table(query, table):
                    plan.append(f"Aplicar seleção no ramo {table}: {cond.left} {cond.op} {cond.right}.")
            for join in query.joins:
                plan.append(f"Executar INNER JOIN com {join.table} usando {join.left} {join.op} {join.right}.")

        if query.select_fields != ["*"]:
            plan.append(f"Aplicar projeção final: {', '.join(query.select_fields)}.")
        plan.append("Exibir resultado final na interface.")
        return plan

    def _short_projection_label(self, fields: List[str], title: str) -> str:
        preview = ", ".join(fields[:3])
        if len(fields) > 3:
            preview += ", ..."
        return f"{title}\n{preview}"

    def _where_label(self, conds: List[Condition]) -> str:
        if not conds:
            return "where"
        first = conds[0]
        if len(conds) == 1:
            return f"where\n{first.left} {first.op} {first.right}"
        return f"where\n{first.left} {first.op} {first.right}\n+{len(conds)-1} condição(ões)"

    def build_operator_graph(self, query: QueryData, optimized: bool = False):
        graph = nx.DiGraph()
        node_counter = 0

        def add_node(label, kind, display=None):
            nonlocal node_counter
            node_id = f"n{node_counter}"
            node_counter += 1
            graph.add_node(node_id, label=label, kind=kind, display=display or label)
            return node_id

        if not optimized:
            current = add_node("Table", "table", query.from_table)
            for join in query.joins:
                join_table = add_node("Table", "table", join.table)
                join_node = add_node("Join", "join", "Join")
                graph.add_edge(current, join_node)
                graph.add_edge(join_table, join_node)
                current = join_node
            if query.where_conditions:
                where_label = self._where_label(query.where_conditions)
                where_node = add_node("where", "selection", where_label)
                graph.add_edge(current, where_node)
                current = where_node
            if query.select_fields != ["*"]:
                final_proj = add_node("projection", "projection", self._short_projection_label(query.select_fields, "projection"))
                graph.add_edge(current, final_proj)
                current = final_proj
            result = add_node("Result", "result", "Result")
            graph.add_edge(current, result)
            return graph

        branch_outputs: Dict[str, str] = {}
        ordered_tables = [query.from_table] + [j.table for j in query.joins]

        for table in ordered_tables:
            table_node = add_node("Table", "table", table)
            current = table_node

            if query.select_fields != ["*"]:
                proj_fields = self._fields_for_table(query, table)
                proj_node = add_node("projection", "projection", self._short_projection_label(proj_fields, "projection"))
                graph.add_edge(current, proj_node)
                current = proj_node

            table_conds = self._conditions_for_table(query, table)
            if table_conds:
                where_node = add_node("where", "selection", self._where_label(table_conds))
                graph.add_edge(current, where_node)
                current = where_node

            branch_outputs[table] = current

        current = branch_outputs[query.from_table]
        for join in query.joins:
            join_node = add_node("Join", "join", "Join")
            graph.add_edge(current, join_node)
            graph.add_edge(branch_outputs[join.table], join_node)
            current = join_node

        if query.select_fields != ["*"]:
            final_proj = add_node("projection", "projection", self._short_projection_label(query.select_fields, "projection"))
            graph.add_edge(current, final_proj)
            current = final_proj

        result = add_node("Result", "result", "Result")
        graph.add_edge(current, result)
        return graph