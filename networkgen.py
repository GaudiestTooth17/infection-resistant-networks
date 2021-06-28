#!/usr/bin/python3

from analyzer import visualize_graph
from typing import List, Tuple, Dict
import sys
import math
from itertools import product

import networkx as nx
import numpy as np
import matplotlib.pyplot as plt

from customtypes import Layout, NodeColors, Agent
from fileio import output_network


# make a component-gate graph
def main(argv):
    # cgg_entry_point(argv)
    social_circles_entry_point(argv)


def cgg_entry_point(argv):
    if len(argv) < 4:
        print(f'Usage: {argv[0]} <num-big-components> <big-component-size> <gate-size>')
        return

    num_big_components = int(argv[1])
    big_component_size = int(argv[2])
    gate_size = int(argv[3])
    name = argv[4]

    graph = make_complete_clique_gate_graph(num_big_components, big_component_size, gate_size)

    output_network(graph, name)
    nx.draw(graph, node_size=100)
    plt.show()


def social_circles_entry_point(argv):
    if len(argv) < 2:
        print(f'Usage: {argv[0]} <output name>')
        return

    agents = {Agent('green', 30): 70, Agent('blue', 40): 20, Agent('purple', 50): 10}
    G, layout, _ = make_social_circles_network(agents, (200, 200))
    plt.clf()
    visualize_graph(G, layout, 'elitist-100-100-100', block=False)
    keep = input('Keep? ')
    if keep.lower() == 'n':
        return social_circles_entry_point(argv)
    output_network(G, argv[1], layout)


def union_components(components: List[nx.Graph]) -> nx.Graph:
    """
    :param components: If the node id's are not unique, some nodes will get overwritten
    :return: the union of components
    """
    master_graph = nx.Graph()
    for comp in components:
        master_graph.add_nodes_from(comp.nodes())
        master_graph.add_edges_from(comp.edges())
    return master_graph


def make_complete_clique_gate_graph(num_big_components, big_component_size, gate_size):
    """
    A clique-gate graph is made up of several cliques that are psuedo nodes. The pseudo edges
    that connect them are smaller cliques (gates). Half the nodes in the gate have an edge into
    one clique and the other half are connected to the other clique.
    """
    # this splits up the list of valid ids into sublists the same size as gate_size
    gate_node_ids = [range(start, start+gate_size)
                     for start in range(0, sum(range(num_big_components))*gate_size, gate_size)]
    gates = [nx.complete_graph(node_ids) for node_ids in gate_node_ids]
    # start numbering the nodes in the big componenets at the first int not used by the gates
    component_node_ids = (range(start, start+big_component_size)
                          for start in range(len(gate_node_ids)*gate_size,
                                             len(gate_node_ids)*gate_size+num_big_components*big_component_size,
                                             big_component_size))
    big_comps = [nx.complete_graph(node_ids) for node_ids in component_node_ids]

    # union the disparate components
    master_graph = union_components(gates + big_comps)

    # insert gates in between components
    current_gate_ind = 0
    for comp_ind, src_comp in enumerate(big_comps[:-1]):
        for dest_comp in big_comps[comp_ind+1:]:
            gate_nodes = list(gates[current_gate_ind].nodes())
            current_gate_ind += 1
            # Add edges to src_comp.
            # The loop assumes that there are fewer or equal nodes in half the gate than in each component
            src_nodes = list(src_comp.nodes())
            for i, node in enumerate(gate_nodes[:len(gate_nodes)//2]):
                master_graph.add_edge(node, src_nodes[i])
            # add edges to dest_comp
            dest_nodes = list(dest_comp.nodes())
            for i, node in enumerate(gate_nodes[len(gate_nodes)//2:]):
                master_graph.add_edge(node, dest_nodes[i])

    return master_graph


def make_social_circles_network(agent_type_to_quantity: Dict[Agent, int],
                                grid_size: Tuple[int, int],
                                force_connected=True) -> Tuple[nx.Graph, Layout, NodeColors]:
    # repeat the algorithm up to some maximum attempting to generate a connected network.
    max_tries = 100
    for attempt in range(max_tries):
        agents = sorted(agent_type_to_quantity.items(),
                        key=lambda x: x[0][1], reverse=True)
        grid = np.zeros(grid_size, dtype='uint8')
        num_nodes = sum(agent_type_to_quantity.values())
        M = np.zeros((num_nodes, num_nodes), dtype='uint8')
        # place the agents with the largest reach first
        loc_to_id = {}
        current_id = 0
        for agent, quantity in agents:
            new_agents = []
            for _ in range(quantity):
                x, y = choose_empty_spot(grid)
                grid[x, y] = agent.reach
                new_agents.append((x, y))
                loc_to_id[(x, y)] = current_id
                current_id += 1
            for x, y in new_agents:
                neighbors = search_for_neighbors(grid, x, y)
                for i, j in neighbors:
                    M[loc_to_id[(x, y)], loc_to_id[(i, j)]] = 1
                    M[loc_to_id[(i, j)], loc_to_id[(x, y)]] = 1

        colors = []
        for agent, quantity in agent_type_to_quantity.items():
            colors += [agent.color]*quantity
        layout = {id_: (2*x/grid_size[0]-1, 2*y/grid_size[1]-1)
                  for (x, y), id_ in loc_to_id.items()}
        G = nx.Graph(M)
        # return the generated network if it is connected or if we don't care
        if (not force_connected) or nx.is_connected(G):
            print(f'Success after {attempt+1} tries.')
            return G, layout, colors
        else:
            print(f'Finished {attempt+1} tries.')

    # Abort execution on failure
    exit(f'Failed to generate a connected network after {max_tries} tries.')


def choose_empty_spot(grid):
    x, y = np.random.randint(grid.shape[0]), np.random.randint(grid.shape[1])
    while grid[x, y] > 0:
        x, y = np.random.randint(grid.shape[0]), np.random.randint(grid.shape[1])
    return x, y


def search_for_neighbors(grid, x, y):
    reach = grid[x, y]
    min_x = max(0, x-reach)
    max_x = min(grid.shape[0]-1, x+reach)
    min_y = max(0, y-reach)
    max_y = min(grid.shape[1]-1, y+reach)
    neighbors = {(i, j)
                 for (i, j) in product(range(min_x, max_x),
                                       range(min_y, max_y))
                 if all((grid[i, j] > 0,
                         distance(x, y, i, j) <= reach,
                         (x, y) != (i, j)))}
    return neighbors


def distance(x0, y0, x1, y1) -> float:
    return math.sqrt((x0-x1)**2 + (y0-y1)**2)


def make_configuration_network(degree_distribution: np.ndarray) -> np.ndarray:
    """Create a random network with the provided degree distribution."""
    degree_distribution = np.copy(degree_distribution)

    N = degree_distribution.shape[0]
    M = np.zeros((N, N), dtype=np.uint8)

    while np.sum(degree_distribution > 0):
        a = np.random.choice(np.where(degree_distribution > 0)[0])
        degree_distribution[a] -= 1
        b = np.random.choice(np.where(degree_distribution > 0)[0])
        degree_distribution[b] -= 1

        M[a, b] += 1
        M[b, a] += 1

    return M


def make_connected_community_network(inner_degrees: np.ndarray,
                                     outer_degrees: np.ndarray) -> nx.Graph:
    """
    Create a random network divided into randomly generated communities connected to each other.

    The number of vertices in each community is determined by the length of inner_degrees.
    Similarly, the number of communities is determined by the length of outer_degrees.

    inner_degrees: the inner degree of each of the vertices in the communities.
    outer_degrees: How many outgoing edges each of the communities has.
    """
    num_communities = len(outer_degrees)
    community_size = len(inner_degrees)
    N = community_size * num_communities
    M = np.zeros((N, N), dtype=np.uint8)

    for c in range(num_communities):
        c_offset = c * community_size
        cm = make_configuration_network(inner_degrees)
        for n1 in range(community_size):
            for n2 in range(community_size):
                M[n1 + c_offset, n2 + c_offset] = cm[n1, n2]
    
    outer_m = make_configuration_network(outer_degrees)
    for c1 in range(num_communities):
        for c2 in range(c1, num_communities):
            if outer_m[c1, c2] > 0:
                for _ in range(int(outer_m[c1, c2])):
                    n1 = c1 * community_size + np.random.randint(community_size)
                    n2 = c2 * community_size + np.random.randint(community_size)
                    M[n1, n2] = 1
                    M[n2, n1] = 1

    return nx.Graph(M)


if __name__ == '__main__':
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print('\nGood bye.')
    except EOFError:
        print('\nGood bye.')
