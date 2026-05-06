
import tkinter as tk
from tkinter import ttk, messagebox
from SQLProcessor import SQLProcessor,SCHEMA
import networkx as nx


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
            w, h = 130, 130
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
