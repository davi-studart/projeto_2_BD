import copy
import re
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict

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

class GraphCanvas(ttk.LabelFrame):
    def __init__(self, parent, title):
        super().__init__(parent, text=title, padding=8)
        self.canvas = tk.Canvas(self, bg="#ffffff", height=520, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.legend = ttk.Label(self, text="Table | projection | where | Join | Result")
        self.legend.pack(anchor="w", pady=(6, 0))

    def clear(self):
        self.canvas.delete("all")

    def draw_graph(self, graph: nx.DiGraph):
        self.clear()
        if not graph.nodes:
            return
        self.update_idletasks()
        width = max(self.canvas.winfo_width(), 1100)
        height = max(self.canvas.winfo_height(), 520)
        pos = self._example_style_positions(graph, width, height)

        for u, v in graph.edges():
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            self.canvas.create_line(x1 + 70, y1, x2 - 70, y2, fill="#222222", width=1.4)

        styles = {
            "table": {"fill": "#ffffff", "outline": "#000000", "text": "#000000"},
            "projection": {"fill": "#7a6492", "outline": "#5e4d71", "text": "#ffffff"},
            "selection": {"fill": "#f1d400", "outline": "#bca700", "text": "#000000"},
            "join": {"fill": "#2e9bd3", "outline": "#247eab", "text": "#ffffff"},
            "result": {"fill": "#70839a", "outline": "#5c6c80", "text": "#ffffff"},
        }

        for node, attrs in graph.nodes(data=True):
            x, y = pos[node]
            label = attrs.get("display", attrs.get("label", node))
            kind = attrs.get("kind", "table")
            style = styles[kind]
            w, h = 130, 58
            self.canvas.create_rectangle(x - w/2, y - h/2, x + w/2, y + h/2, fill=style["fill"], outline=style["outline"], width=1)
            self.canvas.create_text(x, y, text=label, width=w - 18, font=("Arial", 10, "bold"), fill=style["text"], justify="center")

    def _example_style_positions(self, graph: nx.DiGraph, width: int, height: int):
        indegrees = dict(graph.in_degree())
        roots = [n for n, deg in indegrees.items() if deg == 0]
        depths = {}

        def dfs(node, depth):
            depths[node] = max(depths.get(node, 0), depth)
            for nxt in graph.successors(node):
                dfs(nxt, depth + 1)

        for root in roots:
            dfs(root, 0)

        layers = {}
        for node, depth in depths.items():
            layers.setdefault(depth, []).append(node)

        max_depth = max(layers) if layers else 0
        left_margin = 90
        right_margin = 90
        top_margin = 70
        bottom_margin = 70
        usable_w = max(1, width - left_margin - right_margin)
        usable_h = max(1, height - top_margin - bottom_margin)
        x_gap = usable_w / max(1, max_depth)
        pos = {}

        for depth in range(max_depth + 1):
            nodes = layers.get(depth, [])
            if not nodes:
                continue
            x = left_margin + depth * x_gap
            if len(nodes) == 1:
                ys = [top_margin + usable_h / 2]
            elif len(nodes) == 2:
                ys = [top_margin + usable_h * 0.28, top_margin + usable_h * 0.72]
            elif len(nodes) == 3:
                ys = [top_margin + usable_h * 0.18, top_margin + usable_h * 0.50, top_margin + usable_h * 0.82]
            else:
                step = usable_h / (len(nodes) + 1)
                ys = [top_margin + step * i for i in range(1, len(nodes) + 1)]
            for node, y in zip(nodes, ys):
                pos[node] = (x, y)
        return pos

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Processador de Consultas SQL - Dois Grafos")
        self.root.geometry("1400x920")
        self.processor = SQLProcessor()
        self._build_ui()
        self._load_example()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Consulta SQL", font=("Arial", 12, "bold")).pack(anchor="w")
        self.sql_text = tk.Text(main, height=6, wrap="word")
        self.sql_text.pack(fill="x", pady=(5, 10))

        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(0, 10))
        ttk.Button(btns, text="Processar consulta", command=self.process_query).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Carregar exemplo", command=self._load_example).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Limpar", command=self._clear_all).pack(side="left")

        notebook = ttk.Notebook(main)
        notebook.pack(fill="both", expand=True)

        text_frame = ttk.Frame(notebook, padding=10)
        notebook.add(text_frame, text="Análise textual")

        self.tabs = {}
        for name in ["Parse", "Validação", "Álgebra Relacional", "Plano de Execução"]:
            section = ttk.LabelFrame(text_frame, text=name, padding=8)
            section.pack(fill="both", expand=True, pady=4)
            text = tk.Text(section, wrap="word", height=8)
            text.pack(fill="both", expand=True)
            self.tabs[name] = text

        original_graph_tab = ttk.Frame(notebook, padding=10)
        notebook.add(original_graph_tab, text="Grafo Não Otimizado")
        self.original_graph_canvas = GraphCanvas(original_graph_tab, "Grafo Não Otimizado")
        self.original_graph_canvas.pack(fill="both", expand=True)

        optimized_graph_tab = ttk.Frame(notebook, padding=10)
        notebook.add(optimized_graph_tab, text="Grafo Otimizado")
        self.optimized_graph_canvas = GraphCanvas(optimized_graph_tab, "Grafo Otimizado")
        self.optimized_graph_canvas.pack(fill="both", expand=True)

        schema_frame = ttk.LabelFrame(main, text="Esquema BD_Vendas usado na validação", padding=10)
        schema_frame.pack(fill="x", pady=(10, 0))
        self.schema_text = tk.Text(schema_frame, height=8, wrap="word")
        self.schema_text.pack(fill="x")
        self.schema_text.insert("1.0", self._schema_description())
        self.schema_text.configure(state="disabled")

    def _schema_description(self):
        return "\n".join(f"{table}: {', '.join(fields)}" for table, fields in SCHEMA.items())

    def _load_example(self):
        example = (
            "SELECT Cliente.Nome, Pedido.ValorTotalPedido, Status.Descricao\n"
            "FROM Cliente\n"
            "INNER JOIN Pedido ON Pedido.Cliente_idCliente = Cliente.idCliente\n"
            "INNER JOIN Status ON Pedido.Status_idStatus = Status.idStatus\n"
            "WHERE Pedido.ValorTotalPedido > 100 AND Cliente.idCliente >= 1;"
        )
        self.sql_text.delete("1.0", "end")
        self.sql_text.insert("1.0", example)

    def _clear_all(self):
        self.sql_text.delete("1.0", "end")
        for widget in self.tabs.values():
            widget.delete("1.0", "end")
        self.original_graph_canvas.clear()
        self.optimized_graph_canvas.clear()

    def _set_tab(self, tab_name, content):
        widget = self.tabs[tab_name]
        widget.delete("1.0", "end")
        widget.insert("1.0", content)

    def process_query(self):
        sql = self.sql_text.get("1.0", "end").strip()
        if not sql:
            messagebox.showwarning("Aviso", "Digite uma consulta SQL.")
            return

        try:
            query = self.processor.parse(sql)
            heuristics, optimized_query, algebra_optimized = self.processor.optimize(query)
            algebra_original = self.processor.relational_algebra(query)

            parse_lines = [
                f"SELECT: {', '.join(query.select_fields)}",
                f"FROM: {query.from_table}",
                "JOINS:"
            ]
            parse_lines.extend([f"- {j.table} ON {j.left} {j.op} {j.right}" for j in query.joins] or ["- Nenhum"])
            parse_lines.append("WHERE:")
            parse_lines.extend([f"- {c.left} {c.op} {c.right}" for c in query.where_conditions] or ["- Nenhum"])
            self._set_tab("Parse", "\n".join(parse_lines))

            self._set_tab("Validação", "Consulta validada com sucesso.\nTabelas, campos e operadores estão dentro do subconjunto exigido no projeto.")

            algebra_text = (
                "Álgebra relacional não otimizada:\n" + algebra_original +
                "\n\nHeurísticas aplicadas:\n- " + "\n- ".join(heuristics) +
                "\n\nÁlgebra relacional otimizada:\n" + algebra_optimized
            )
            self._set_tab("Álgebra Relacional", algebra_text)

            plan_original = self.processor.build_plan(query, optimized=False)
            plan_optimized = self.processor.build_plan(optimized_query, optimized=True)
            plan_text = (
                "Plano original:\n" + "\n".join(f"{i + 1}. {step}" for i, step in enumerate(plan_original)) +
                "\n\nPlano otimizado:\n" + "\n".join(f"{i + 1}. {step}" for i, step in enumerate(plan_optimized))
            )
            self._set_tab("Plano de Execução", plan_text)

            self.original_graph_canvas.draw_graph(self.processor.build_operator_graph(query, optimized=False))
            self.optimized_graph_canvas.draw_graph(self.processor.build_operator_graph(optimized_query, optimized=True))

        except Exception as e:
            for widget in self.tabs.values():
                widget.delete("1.0", "end")
            self.original_graph_canvas.clear()
            self.optimized_graph_canvas.clear()
            self._set_tab("Validação", f"Erro: {e}")
            messagebox.showerror("Erro na consulta", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()
