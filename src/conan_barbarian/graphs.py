"""
Graph structures and algorithms.
"""

from typing import Optional, Callable
import io
import logging


logger = logging.getLogger(__name__)


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
    
    @property
    def out_degree(self):
        return len(self.out_refs)
    
    @property
    def out_ids(self):
        return [n.name for n in self.out_refs]
    
    def remove_in_ref(self, other: 'DepGraphNode'):
        self.in_refs.discard(other)
        other.out_refs.discard(self)

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

    def traverse(self, node_visitor: Callable[[DepGraphNode], None],
                 arc_visitor: Optional[Callable[[DepGraphNode, DepGraphNode], None]] = None):
        logger.debug('traversing graph')
        roots = [n for n in self.nodes if n.is_root]
        visit_count: dict[str, int] = {}

        while len(roots) > 0:
            roots.sort(key=lambda n : n.name)
            next_roots = []
            for node in roots:
                node_visitor(node)
                logger.debug('processing node %s', node)
                node_children: set[DepGraphNode] = node.out_refs.copy()
                for target in node_children:
                    num_visits = visit_count.get(target.name, 0) + 1
                    visit_count[target.name] = num_visits
                    if arc_visitor:
                        arc_visitor(node, target)
                    if num_visits == target.in_degree:
                        next_roots.append(target)
            roots = next_roots

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
    sorted_names = []
    graph.traverse(lambda node: sorted_names.append(node.name))
    return sorted_names


def prune_arcs(graph: DepGraph):
    logger.debug('pruning graph')
    pruned = DepGraph()

    nodes_with_multiple_dependants: list[DepGraphNode] = []
    
    def node_visitor(node: DepGraphNode):
        new_node = pruned.get_node(node.name)
        if node.in_degree > 1:
            nodes_with_multiple_dependants.append(new_node)

    def arc_visitor(src: DepGraphNode, tgt: DepGraphNode):
        pruned.add_dependency(src.name, tgt.name)

    graph.traverse(node_visitor, arc_visitor)

    def recursive_check(node: DepGraphNode, alternatives: set[DepGraphNode]):
        to_be_removed: set[DepGraphNode] = set()
        for parent in node.in_refs:
            if parent in alternatives:
                alternatives.discard(parent)
                to_be_removed.add(parent)
            recursive_check(parent, alternatives)
        return to_be_removed
    
    for node in nodes_with_multiple_dependants:
        logger.debug(f'checking incoming arcs of node {node.name}')
        to_be_pruned: set[DepGraphNode] = set()
        for parent in node.in_refs:
            res = recursive_check(parent, set(node.in_refs))
            to_be_pruned.update(res)
        logger.debug(f'removing parents {[n.name for n in to_be_pruned]}')
        for parent in to_be_pruned:
            node.remove_in_ref(parent)

    return pruned

