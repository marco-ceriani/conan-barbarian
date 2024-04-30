"""
Graph structures and algorithms.
"""

import io
import logging


class DepGraphNode:
    __slots__ = ("name", "in_refs", "out_refs", "data")
    in_refs: set['DepGraphNode']
    out_refs: set['DepGraphNode']
    data: dict[str, object]

    def __init__(self, name: str):
        self.name = name
        self.in_refs = set()
        self.out_refs = set()
        self.data = {}

    @property
    def is_root(self):
        return len(self.in_refs) == 0
    
    @property
    def in_degree(self):
        return len(self.in_refs)

    def __repr__(self):
        return f"Node({self.name}, depends_on:{[n.name for n in self.out_refs]})"

    def __str__(self):
        return self.name


class DepGraph:
    __slots__ = ("_nodes")
    _nodes: dict[str, DepGraphNode]

    def __init__(self):
        self._nodes = {}

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._nodes.keys())
    
    @property
    def nodes(self) -> list[DepGraphNode]:
        return list(self._nodes.values())
    
    def get_node(self, lib: str):
        node = self._nodes.get(lib, None)
        if not node:
            node = DepGraphNode(lib)
            self._nodes[lib] = node
        return node
    
    def add_dependency(self, src: str, tgt: str):
        src_node = self.get_node(src)
        tgt_node = self.get_node(tgt)
        src_node.out_refs.add(tgt_node)
        tgt_node.in_refs.add(src_node)

    def remove_dependency(self, src: str, tgt: str):
        src_node = self.get_node(src)
        tgt_node = self.get_node(tgt)
        src_node.out_refs.remove(tgt_node)
        tgt_node.in_refs.remove(src_node)

    def __repr__(self):
        return f"DepGraph[{str(list(self.nodes.values()))}]"
    
    def to_dot(self):
        """
        Creates a DOT description of the graph
        """
        text = io.StringIO()
        text.write('digraph {\n')
        for node in self.nodes:
            if node.data.get('component', False):
                text.write(f'  {node.name} [shape=box];\n')
        for node in self.nodes:
            for child in node.out_refs:
                text.write(f'  "{node.name}" -> "{child.name}";\n')
        text.write('}\n')
        return text.getvalue()


def sort_graph(graph: DepGraph):
    logger = logging.getLogger('graph')
    roots = [n for n in graph.nodes if n.is_root]
    sorted_names = []

    while len(roots) > 0:
        roots.sort(key=lambda n : n.name)
        sorted_names.extend([r.name for r in roots])
        next_roots = []
        for node in roots:
            logger.debug('processing node %s', node)
            node_children: set[DepGraphNode] = node.out_refs.copy()
            for target in node_children:
                num_visits = target.data.get('visited', 0) + 1
                target.data['visited'] = num_visits
                if num_visits == target.in_degree:
                    next_roots.append(target)
        roots = next_roots

    for node in graph.nodes:
        try:
            del node.data['visited']
        except KeyError:
            pass
    return sorted_names

