#!/usr/bin/python3
import itertools as it
from customtypes import Number
from typing import Callable, List, Sequence, Tuple
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import hcmioptim as ho
from analyzer import visualize_graph, betw_centrality


def main():
    n_steps = 1000
    N = 100
    rand = np.random.default_rng()
    # node_to_degree = np.clip(rand.normal(5, 3, N), 1, None).astype('int')
    # # All of the degrees must sum to an even number. This if block ensures that happens.
    # if np.sum(node_to_degree) % 2 == 1:
    #     node_to_degree[np.argmin(node_to_degree)] += 1
    # edge_list = np.array([node
    #                       for node, degree in enumerate(node_to_degree)
    #                       for _ in range(degree)])
    # rand.shuffle(edge_list)
    # optimizer = ho.sa.SAOptimizer(component_objective, ho.sa.make_fast_schedule(100),
    #                               make_edge_list_neighbor(), edge_list, True)
    optimizer = ho.ga.GAOptimizer(ClusteringObjective(edge_list_to_network, .01),
                                  NextNetworkGenEdgeList(N, rand),
                                  new_edge_list_pop(20, N, rand),
                                  True, 6)
    pbar = tqdm(range(n_steps))
    costs = np.zeros(n_steps)
    global_best = None
    for step in pbar:
        cost_to_encoding = optimizer.step()
        local_best = min(cost_to_encoding, key=lambda x: x[0])
        if global_best is None or local_best[0] < global_best[0]:
            global_best = local_best
        costs[step] = local_best[0]
        pbar.set_description('Cost: {:.3f}'.format(local_best[0]))

    G = edge_list_to_network(global_best[1])
    print('Number of nodes:', len(G.nodes))
    print('Number of edges:', len(G.edges))
    print('Number of components:', len(tuple(nx.connected_components(G))))

    plt.plot(costs)
    plt.show(block=False)
    plt.figure()
    plt.hist(tuple(x[1] for x in G.degree), bins=None)
    plt.show(block=False)
    plt.figure()
    visualize_graph(nx.adjacency_matrix(G), None, f'From Edge List\nCost: {global_best[0]}',  # type: ignore
                    True, betw_centrality, False)

    input('Press <enter> to exit.')


class ClusteringObjective:
    def __init__(self, encoding_to_network: Callable[[np.ndarray], nx.Graph], diameter_weight: float):
        self._rand = np.random.default_rng()
        self._encoding_to_network = encoding_to_network
        self._diameter_weight = diameter_weight

    def __call__(self, encoding) -> float:
        G = self._encoding_to_network(encoding)
        biggest_comp = G.subgraph(max(nx.connected_components(G), key=len))
        return -nx.average_clustering(G) - self._diameter_weight * nx.diameter(biggest_comp)  # type: ignore


def component_objective(edge_list: np.ndarray) -> int:
    G = edge_list_to_network(edge_list)
    conn_comps = tuple(nx.connected_components(G))
    largest_component = max(conn_comps, key=len)
    bad = len(largest_component)*2 + len(conn_comps)
    good = nx.diameter(G.subgraph(largest_component)) + len(G) + len(G.edges)  # type: ignore
    energy = bad - good
    return energy


class HighBetweenessObjective:
    def __init__(self, encoding_to_network: Callable[[np.ndarray], nx.Graph],
                 num_important_edges: int,
                 diameter_weight: float) -> None:
        self._encoding_to_network = encoding_to_network
        self._num_important_edges = num_important_edges
        self._diameter_weight = diameter_weight

    def __call__(self, encoding: np.ndarray) -> float:
        G = self._encoding_to_network(encoding)

        if not nx.is_connected(G):
            return len(G) + self._num_important_edges*2

        edge_betwenesses = sorted(nx.edge_betweenness_centrality(G).values(), reverse=True)
        return -sum(edge_betwenesses[:self._num_important_edges])\
            - nx.diameter(G)*self._diameter_weight  # type: ignore


def configuration_neighbor(degrees: Sequence[int], rand) -> Sequence[int]:
    neighbor = np.copy(degrees)
    nonzero_entries = np.where(neighbor > 0)[0]
    i, j = rand.choice(nonzero_entries, 2, replace=False)
    neighbor[i] += rand.choice((-1, 1))
    neighbor[j] += rand.choice((-1, 1))
    return neighbor


def make_edge_list_neighbor() -> Callable[[np.ndarray], np.ndarray]:
    rand = np.random.default_rng()

    def edge_list_neighbor(edge_list: np.ndarray) -> np.ndarray:
        index0 = rand.integers(0, edge_list.shape[0])
        index1 = rand.integers(0, edge_list.shape[0])

        # to eliminate self-loops check the value adjacent to index0 to make sure edge_list[index1] != that_value
        offset = 1 if index0 % 2 == 0 else -1
        while edge_list[index0+offset] == edge_list[index1]:
            index1 = rand.integers(0, edge_list.shape[0])

        new_edge_list = np.copy(edge_list)
        new_edge_list[index0], new_edge_list[index1] = new_edge_list[index1], new_edge_list[index0]
        return new_edge_list

    return edge_list_neighbor


def network_from_degree_sequence(degrees: Sequence[int], vis_func, force_good_behavior: bool, rand) -> nx.Graph:
    if sum(degrees) % 2 != 0:
        raise Exception('The sum of degrees must be even.')

    node_to_remaining_stubs = dict(enumerate(degrees))
    G = nx.empty_graph(len(degrees))
    while sum(node_to_remaining_stubs.values()) > 0:
        available_nodes = tuple(filter(lambda u: node_to_remaining_stubs[u],
                                       node_to_remaining_stubs.keys()))
        u = rand.choice(available_nodes)
        node_to_remaining_stubs[u] -= 1
        available_nodes = tuple(filter(lambda v: all((node_to_remaining_stubs[v],
                                                      any((not force_good_behavior,
                                                           v != u and not G.has_edge(u, v))))),
                                       node_to_remaining_stubs.keys()))
        if len(available_nodes) == 0:
            print('Network generation failed. Restarting.')
            return network_from_degree_sequence(degrees, vis_func, force_good_behavior, rand)

        v = rand.choice(available_nodes)
        node_to_remaining_stubs[v] -= 1
        G.add_edge(u, v)
        vis_func(G, u, v)

    return G


def edge_set_to_network(edge_set: np.ndarray) -> nx.Graph:
    E = edge_set.shape[0]
    N = int(np.sqrt(2*E+.25)+.5)
    current_edge = 0
    M = np.zeros((N, N), dtype=np.int64)

    for i in range(M.shape[0]):
        for j in range(i+1, M.shape[1]):
            M[i, j] = edge_set[current_edge]
            M[j, i] = edge_set[current_edge]
            current_edge += 1

    return nx.Graph(M)


class NextNetworkGenEdgeList:
    def __init__(self, N: int, rand):
        self._vertex_choices = tuple(range(N))
        self._N = N
        self._rand = rand

    def __call__(self, rated_pop: Sequence[Tuple[Number, np.ndarray]]) -> Tuple[np.ndarray, ...]:
        couples = ho.ga.roulette_wheel_cost_selection(rated_pop)
        offspring = (ho.ga.single_point_crossover(*couple) for couple in couples)
        children = tuple(child for pair in offspring for child in pair)

        for i, j in it.product(range(len(children)), range(len(children[0]))):
            if self._rand.random() < .001:
                children[i][j] = self._rand.choice(self._vertex_choices)

        return children


class NextNetworkGenEdgeSet:
    def __init__(self, rand) -> None:
        self._rand = rand

    def __call__(self, rated_pop: Sequence[Tuple[Number, np.ndarray]]) -> Tuple[np.ndarray, ...]:
        couples = ho.ga.roulette_wheel_cost_selection(rated_pop)
        offspring = (ho.ga.single_point_crossover(*couple) for couple in couples)
        children = tuple(child for pair in offspring for child in pair)

        for i, j in it.product(range(len(children)), range(len(children[0]))):
            if self._rand.random() < .0001:
                children[i][j] = 1 - children[i][j]

        return children


def new_edge_list_pop(population_size: int, N: int, rand) -> Tuple[np.ndarray, ...]:
    # decide on a degree for each of the nodes
    node_to_degree = np.clip(rand.normal(5, 3, N), 1, None).astype('int')
    # ensure that the sum of the degrees is even
    if np.sum(node_to_degree) % 2 != 0:
        node_to_degree[np.argmin(node_to_degree)] += 1

    # put each node's id in an array (edge list) the same amount as its degree
    base_list = np.array(tuple(node
                               for node, degree in enumerate(node_to_degree)
                               for _ in range(degree)))
    population = tuple(np.copy(base_list) for _ in range(population_size))
    # shuffle each edge list
    for edge_list in population:
        rand.shuffle(edge_list)

    return population


def new_edge_set_pop(size: int, N: int, rand) -> List[np.ndarray]:
    edge_density = .01
    E = (N**2 - N) // 2
    population = [np.array([1 if i < int(E*edge_density) else 0 for i in range(E)])
                  for _ in range(size)]
    for edge_set in population:
        rand.shuffle(edge_set)
    return population


def edge_list_to_network(edge_list: np.ndarray) -> nx.Graph:
    """
    edge_list is the concrete implementation of the thing created by a degree configuration.
    If a node has degree n, that node's integer ID will appear n times in edge_list. Edges are
    created by putting the values in groups of two starting at index 0 and proceeding to the end.
    In this way, edge_list can be viewed as a List[Tuple[int, int]].
    """
    N = np.max(edge_list)
    G = nx.empty_graph(N)
    G.add_edges_from(((edge_list[i], edge_list[i+1])
                      for i in range(0, len(edge_list), 2)))
    return G


def make_vis_func(visualize: bool) -> Callable[[nx.Graph, int, int], None]:
    layout = None

    def do_vis(G: nx.Graph, u: int, v: int) -> None:
        nonlocal layout
        if layout is None:
            layout = nx.kamada_kawai_layout(G)
        nx.draw_networkx(G, with_labels=False, pos=layout,
                         node_color=tuple('green' if n in (u, v) else 'blue' for n in G.nodes))
        plt.pause(.5)  # type: ignore
        plt.clf()

    def dont_vis(G: nx.Graph, u: int, v: int) -> None:
        return None

    return do_vis if visualize else dont_vis


if __name__ == '__main__':
    try:
        main()
    except EOFError:
        print('\nGoodbye.')
    except KeyboardInterrupt:
        print('\nGoodbye.')
