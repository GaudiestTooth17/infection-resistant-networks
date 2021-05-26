import networkx as nx
import numpy as np
from typing import Optional, Union, Callable, Tuple, Dict, Any
from customtypes import Layout


def output_network(G: nx.Graph, network_name: str, layout_algorithm: Optional[Union[Callable, Layout]] = None):
    """
    Saves the network to a file using the typical representation
    """
    with open(network_name+'.txt', 'w') as f:
        f.write(f'{len(G.nodes)}\n')

        # sometimes the nodes are identified by tuples instead of just integers
        # This doesn't work with other programs in the project, so we must give each tuple
        # a unique integer ID.
        node_to_id: Dict[Any, int] = {}
        current_id = 0

        def get_id_of_node(node) -> int:
            nonlocal current_id
            if node not in node_to_id:
                node_to_id[node] = current_id
                current_id += 1
            return node_to_id[node]

        edge_lines = [f'{get_id_of_node(n0)} {get_id_of_node(n1)}' for n0, n1 in G.edges]
        f.writelines(edge_lines)
        # this code is just for the visualization program I made ("graph-visualizer")
        # It writes out where each of the nodes should be drawn.
        f.write('\n')
        if layout_algorithm is None:
            layout_algorithm = nx.kamada_kawai_layout
        if callable(layout_algorithm):
            layout = layout_algorithm(G)
        else:
            layout = layout_algorithm
        for node, coordinate in sorted(layout.items(), key=lambda x: x[0]):
            f.write(f'{node_to_id[node]} {coordinate[0]} {coordinate[1]}\n')
        f.write('\n')


def read_network_file(file_name: str) -> Tuple[np.ndarray, Optional[Layout]]:
    with open(file_name, 'r') as f:
        line = f.readline()
        shape = (int(line[:-1]), int(line[:-1]))
        matrix = np.zeros(shape, dtype='uint8')

        line = f.readline()[:-1]
        i = 1
        while len(line) > 0:
            coord = line.split(' ')
            matrix[int(coord[0]), int(coord[1])] = 1
            matrix[int(coord[1]), int(coord[0])] = 1
            line = f.readline()[:-1]
            i += 1

        rest_of_lines = tuple(map(lambda s: s.split(),
                              filter(lambda s: len(s) > 1, f.readlines())))
        layout = {int(line[0]): (float(line[1]), float(line[2]))
                  for line in rest_of_lines} if len(rest_of_lines) > 0 else None
    return matrix, layout