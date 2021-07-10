from typing import Tuple, Dict, Any, Optional
from customtypes import Agent
from sim_dynamic import Disease, FlickerBehavior, make_starting_sir, simulate
import networkgen
import partitioning
import networkx as nx
import numpy as np
from experiment.common import safe_run_trials


def run_social_circles_trial(args: Tuple[Dict[Agent, int],
                                         Tuple[int, int],
                                         Disease,
                                         Any]) -> Optional[Tuple[float, float]]:
    agent_to_quantity, grid_dims, disease, rand = args
    sim_len = 200
    sims_per_trial = 150

    sc_results = networkgen.make_social_circles_network(agent_to_quantity, grid_dims, rand=rand)
    if sc_results is None:
        return None
    G, _, _ = sc_results

    to_flicker = partitioning.fluidc_partition(G, 25)
    proportion_flickering = len(to_flicker) / len(G.edges)
    M = nx.to_numpy_array(G)

    network_behavior = FlickerBehavior(M, to_flicker, (True, False), "Probs don't change this")
    avg_sus = np.mean([np.sum(simulate(M, make_starting_sir(len(M), 1),
                                       disease, network_behavior, sim_len, None, rand)[-1][0] > 0)
                       for _ in range(sims_per_trial)])

    return proportion_flickering, avg_sus


def social_circles_entry_point():
    print('Running social circles experiments.')
    num_trials = 1000
    rand = np.random.default_rng(0xdeadbeef)
    N = 500
    N_purple = int(N * .1)
    N_blue = int(N * .2)
    N_green = N - N_purple - N_blue
    agents = {Agent('green', 30): N_green,
              Agent('blue', 40): N_blue,
              Agent('purple', 50): N_purple}
    # grid_dim = (int(N/.005), int(N/.005))  # the denominator is the desired density
    grid_dim = N, N
    disease = Disease(4, .2)

    safe_run_trials(f'Social Circles -- Elitist {grid_dim} {N}', run_social_circles_trial,
                    (agents, grid_dim, disease, rand), num_trials)
