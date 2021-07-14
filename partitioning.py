from customtypes import Communities
from itertools import takewhile
from typing import Dict, Iterable, Sequence, Union, Tuple
import networkx as nx
import numpy as np
import sys
from networkx.algorithms.community import girvan_newman, asyn_fluidc
from fileio import get_network_name, read_network, write_network
from analyzer import (calc_prop_common_neighbors,
                      make_meta_community_layout,
                      make_meta_community_network,
                      visualize_network)
from collections import Counter
import time
import itertools as it


def main():
    """
    Initial testing indicates that this is a REALLY good community detection algorithm!!
    It didn't do great on the elitist network, but perhaps with more time it could
    get better results.

    It was really crappy on Watts-Strogatz.
    """
    if len(sys.argv) < 3:
        print(f'Usage: {sys.argv[0]} <network> <num labels/partitions>')
        return

    M, layout, _ = read_network(sys.argv[1])
    if layout is None:
        raise Exception('Layout cannot be None.')
    name = get_network_name(sys.argv[1])
    n_communities = int(sys.argv[2])

    G = nx.Graph(M)
    start_time = time.time()


def fluidc_test():
    N = 500
    networks = (nx.erdos_renyi_graph(N, .01) for _ in range(100))
    n_comms = N // 20
    for G in networks:
        starting_ncc = nx.number_connected_components(G)
        print(f'Network has {starting_ncc} components.')
        if starting_ncc >= n_comms:
            continue
        to_remove = fluidc_partition(G, n_comms)
        G.remove_edges_from(to_remove)
        ncc = nx.number_connected_components(G)
        if ncc != n_comms:
            name = input(f'Network has {ncc} communities. Name? ')
            write_network(G, name, nx.kamada_kawai_layout(G),
                          intercommunity_edges_to_communities(G, to_remove))


def run_experiment(args) -> Tuple[int, int]:
    M, n_labels = args
    G = nx.Graph(M)
    edges_to_remove = label_partition(G, n_labels)
    G.remove_edges_from(edges_to_remove)
    modules = tuple(nx.connected_components(G))
    return len(modules), len(tuple(filter(lambda module: len(module) < 6, modules)))


def girvan_newman_partition(G: nx.Graph, num_communities: int) -> Tuple[Tuple[int, int], ...]:
    """Return the edges to remove in order to break G into communities."""
    communities_generator: Iterable[Tuple[int, ...]] = girvan_newman(G)
    communities = tuple(takewhile(lambda comm: len(comm) <= num_communities,
                                  communities_generator))[-1]
    id_to_community = dict(enumerate(communities))
    node_to_community = {node: comm_id
                         for comm_id, community in id_to_community.items()
                         for node in community}
    edges_to_remove = tuple(set((u, v)
                                for u, v in G.edges
                                if node_to_community[u] != node_to_community[v]))
    return edges_to_remove


def common_neighbor_partition(G: nx.Graph, num_communities: int) -> Tuple[Tuple[int, int], ...]:
    """Return the edges to remove in order to break G into communities."""
    def weakest_edge(G: nx.Graph) -> Tuple[int, int]:
        return min(G.edges, key=lambda edge: calc_prop_common_neighbors(G, edge[0], edge[1]))

    communities_generator = girvan_newman(G, most_valuable_edge=weakest_edge)
    communities = tuple(takewhile(lambda comm: len(comm) <= num_communities,
                                  communities_generator))[-1]
    id_to_community = dict(enumerate(communities))
    node_to_community = {node: comm_id
                         for comm_id, community in id_to_community.items()
                         for node in community}
    edges_to_remove = tuple(set((u, v)
                                for u, v in G.edges
                                if node_to_community[u] != node_to_community[v]))
    return edges_to_remove


def fluidc_partition(G: nx.Graph, num_communities: int) -> Tuple[Tuple[int, int], ...]:
    """
    Return the edges to remove in order to break G into communities.

    If the network is disconnected, the smaller components will all be
    deterministically attached by 1 edge to the largest component for the sake
    of the algorithm. The original network will not be mutated.
    """
    # list of all the components sorted by length with the largest coming first
    components = sorted((tuple(comp) for comp in nx.connected_components(G)),
                        key=len, reverse=True)
    # It's possible that the network is already divided up
    if len(components) >= num_communities:
        return ()
    # handle the case where the network is unconnected
    if len(components) > 1:
        comp_to_num_communities = _calc_num_communities_per_component(components, num_communities)
        unflattened_edges_to_remove = (fluidc_partition(G.subgraph(comp), num_comms)
                                       for comp, num_comms in comp_to_num_communities.items())
        return tuple(it.chain(*unflattened_edges_to_remove))

    # handle the case where the network is connected
    communities = tuple(asyn_fluidc(G, num_communities, seed=0))
    id_to_community = dict(enumerate(communities))
    node_to_community = {node: comm_id
                         for comm_id, community in id_to_community.items()
                         for node in community}
    edges_to_remove = tuple(set((u, v)
                                for u, v in G.edges
                                if node_to_community[u] != node_to_community[v]))
    H = G.copy()
    H.remove_edges_from(edges_to_remove)
    # This gets triggered, so the error has to be nearish by
    # In one inspection, it looked like all the components but one were in tact, except one that had
    # gotten split
    ncc = nx.number_connected_components(H)
    if ncc != num_communities:
           print(f'G divided incorrectly! Expected {num_communities} Got {ncc}')
           import pdb; pdb.set_trace()
    return edges_to_remove


def _calc_num_communities_per_component(components: Sequence[Sequence[int]],
                                        num_communities: int) -> Dict[Sequence[int], int]:
    """
    Assign each component to be divided into some number of communities with the
    goal of make the communities as equally sized as possible across the entire
    network.
    """
    component_sizes = np.array(tuple(len(comp) for comp in components))
    relative_sizes = component_sizes / np.sum(component_sizes)
    comp_to_num_communities: np.ndarray = num_communities * relative_sizes
    comp_to_num_communities = np.where(comp_to_num_communities < 1, 1, comp_to_num_communities)
    comp_to_num_communities = np.round(comp_to_num_communities)

    error = num_communities - np.sum(comp_to_num_communities)
    error_sign = np.sign(error)
    while error != 0:
        possible_comp_to_num_communities = comp_to_num_communities - error_sign
        possible_comp_to_num_communities = np.where(comp_to_num_communities < 1,
                                                    1, possible_comp_to_num_communities)
        possible_new_comm_sizes = component_sizes / possible_comp_to_num_communities
        index_to_change = np.argmax(possible_new_comm_sizes)
        comp_to_num_communities[index_to_change] += error_sign

        error -= error_sign

    component_to_n_comms = {comp: int(n_comms) for comp, n_comms in zip(components, comp_to_num_communities)}
    print(f'Got {sum(component_to_n_comms.values())} communities.')
    # print(np.array(tuple(component_to_n_comms.values())))
    return component_to_n_comms


def label_partition(G: nx.Graph, labels: Union[int, np.ndarray]) -> Tuple[Tuple[int, int], ...]:
    """
    Return the edges to remove in order to break G into communities.

    G: Network to partition.
    labels: Either the number of classes of labels to randomly assign to vertices,
            or a premade array of labels to assign to the vertices.
    """
    if isinstance(labels, int):
        available_labels = tuple(range(labels))
        rand = np.random.default_rng()
        node_to_label = rand.choice(available_labels, size=len(G))
    else:
        node_to_label = labels

    max_steps = 1000
    for step in range(max_steps):
        # do label propagation
        new_labels = np.zeros(len(G), dtype=np.int64)
        for node in G:
            label_counts = Counter([node_to_label[neighbor] for neighbor in G[node]]
                                   + [node_to_label[node]])
            most_popular = max(label_counts.items(), key=lambda x: x[1])[0]
            new_labels[node] = most_popular

        # early exit condition
        if (node_to_label == new_labels).all():
            break
        node_to_label = new_labels

    edges_to_remove = filter(lambda edge: node_to_label[edge[0]] != node_to_label[edge[1]], G.edges)
    return tuple(edges_to_remove)


def intercommunity_edges_to_communities(G: nx.Graph,
                                        interedges: Tuple[Tuple[int, int], ...]) -> Communities:
    """
    Return a dictionary of node to the ID of the community it belongs to.

    interedges: The edges to remove in order to break up G along community lines.
    """
    H = nx.Graph(G)
    H.remove_edges_from(interedges)
    id_to_community: Dict[int, Tuple[int, ...]] = dict(enumerate(nx.connected_components(H)))
    node_to_community = {node: comm_id
                         for comm_id, comm in id_to_community.items()
                         for node in comm}
    return node_to_community


if __name__ == '__main__':
    try:
        # main()
        fluidc_test()
    except KeyboardInterrupt:
        print('\nGood bye.')
    except EOFError:
        print('\nGood bye.')
