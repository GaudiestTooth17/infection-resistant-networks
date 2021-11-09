import sys
sys.path.append('')
from collections import defaultdict
from typing import Tuple
from sympy.core.function import diff
from sympy.core.symbol import Symbol
import numpy as np
from network import Network
import networkx as nx
import itertools as it
from sympy import Expr


def make_affiliation_network(f_coeffs: np.ndarray, g_coeffs: np.ndarray,
                             N: int, M: int, rng: np.random.Generator) -> Network:
    # get initial counts for how many stubs each agent and group has
    agent_stubs: np.ndarray = rng.choice(len(f_coeffs), N, p=f_coeffs)
    group_stubs: np.ndarray = rng.choice(len(g_coeffs), M, p=g_coeffs)
    # balance the counts so that the groups can combine nicely
    # This doesn't seem to be super necessary because it isn't feasible
    # to balance all the time and the results look fine visually without it
    # TODO: check that the actual results from the function match the results
    #       predicted by the math
    timeout = 1_000
    pre_calculed_indices = rng.choice(N+M, size=timeout)
    while np.sum(agent_stubs) != np.sum(group_stubs) and timeout > 0:
        stub_count_to_replace = pre_calculed_indices[timeout-1]
        if stub_count_to_replace < N:
            agent_stubs[stub_count_to_replace] = rng.choice(len(f_coeffs), 1, p=f_coeffs)
        else:
            group_stubs[stub_count_to_replace-N] = rng.choice(len(g_coeffs), 1, p=g_coeffs)
        timeout -= 1

    group_membership = defaultdict(lambda: set())
    # Assign agents to groups
    # This assumes that agents can be assigned to the same group multiple times, but only
    # one edge will appear
    agents_with_stubs = np.nonzero(agent_stubs)[0]
    groups_with_stubs = np.nonzero(group_stubs)[0]
    while len(agents_with_stubs) > 0 and len(groups_with_stubs) > 0:
        agent = rng.choice(agents_with_stubs)
        group = rng.choice(groups_with_stubs)
        group_membership[group].add(agent)
        agent_stubs[agent] -= 1
        group_stubs[group] -= 1
        agents_with_stubs = np.nonzero(agent_stubs)[0]
        groups_with_stubs = np.nonzero(group_stubs)[0]

    # for agent_id, n_stubs in enumerate(agent_stubs):
    #     if len(np.nonzero(group_stubs)[0]) == 0:
    #         break
    #     for _ in range(n_stubs):
    #         possible_groups = np.nonzero(group_stubs)[0]
    #         if len(possible_groups) == 0:
    #             break
    #         group = rng.choice(possible_groups)
    #         group_membership[group].add(agent_id)
    #         group_stubs[group] -= 1

    edges = it.chain.from_iterable(it.combinations(agents, 2)
                                   for agents in group_membership.values())
    G: nx.Graph = nx.empty_graph(N)
    G.add_edges_from(edges)
    return Network(G)


def coeffs_to_expr(coeffs: np.ndarray, var: Symbol) -> Expr:
    e: Expr = 0  # type: ignore
    for ex, c in enumerate(coeffs):
        e += c*(var**ex)
    return e


def calc_clustering_and_edge_density(f_coeffs: np.ndarray, g_coeffs: np.ndarray,
                                     N: int, M: int) -> Tuple[float, float]:
    x = Symbol('x')
    f = coeffs_to_expr(f_coeffs, x)
    g = coeffs_to_expr(g_coeffs, x)
    g_p = diff(g, x)
    G = f.subs({x: (g_p/g_p.subs({x: 1}))})
    G_p = diff(G, x)
    G_pp = diff(G_p, x)
    g_ppp = diff(g_p, x, 2)

    clustering = (M*g_ppp.subs({x: 1})) / (N*G_pp.subs({x: 1}))
    z = G_p.subs({x: 1})
    edge_density = z/(N-1)
    return clustering, edge_density


def display_results_for(f_coeffs, g_coeffs, seed):
    rng = np.random.default_rng(seed)
    N = 1000
    M = 100
    net = make_affiliation_network(f, g, N, M, rng)
    actual_c = nx.average_clustering(net.G)
    actual_ed = net.edge_density
    expected_c, expected_ed = calc_clustering_and_edge_density(f, g, N, M)
    print(f'Actual clustering: {actual_c}\nExpected clustering: {expected_c}\n')
    print(f'Actual edge density: {actual_ed}\nExpected edge density: {expected_ed}\n')


if __name__ == '__main__':
    seed = 666
    rng = np.random.default_rng(seed)
    # these arrays are troublesome
    # f = np.array([0, .1, .2, .3, .4])
    # g = np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .1, .2, .2, .5])
    for _ in range(10):
        f = rng.random(20)
        f /= np.sum(f)
        g = rng.random(100)
        g /= np.sum(g)
        display_results_for(f, g, seed)
