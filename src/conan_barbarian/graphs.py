"""
Graph structures and algorithms.
"""

class DepGraphNode:
    __slots__ = ("name", "in_refs", "out_refs", "data")

    def __init__(self, name: str):
        self.name = name
        self.in_refs = set()
        self.out_refs = set()
        self.data = {}

    @property
    def is_root(self):
        return len(self.in_refs) == 0

    def __repr__(self):
        return f"Node({self.name}, depends_on:{[n.name for n in self.out_refs]})"

    def __str__(self):
        return self.name


class DepGraph:
    __slots__ = ("nodes")

    def __init__(self):
        self.nodes: dict[str, DepGraphNode] = {}

    def get_keys(self) -> list[str]:
        return self.nodes.keys()
    
    def get_nodes(self) -> list[DepGraphNode]:
        return list(self.nodes.values())
    
    def get_node(self, lib: str):
        node = self.nodes.get(lib, None)
        if not node:
            node = DepGraphNode(lib)
            self.nodes[lib] = node
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
