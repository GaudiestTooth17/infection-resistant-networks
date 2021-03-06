from common import safe_run_trials
from networkgen import TimeBasedBehavior, AgentBehavior, make_agent_generated_network
import numpy as np
from sim_dynamic import Disease, StaticFlickerBehavior, simulate, make_starting_sir
from typing import Optional, Tuple, Any
import partitioning
import networkx as nx
from socialgood import rate_social_good


def agent_generated_entry_point(seed=1337):
    print('Running agent generated experiments')
    num_trials = 100
    rand = np.random.default_rng(seed)
    disease = Disease(4, .2)
    N = 500
    behaviors = [TimeBasedBehavior(N, lb_connection, ub_connection, steps_to_stability, rand)
                 for lb_connection, ub_connection, steps_to_stability
                 in [(4, 6, 5),
                     (4, 6, 10),
                     (4, 6, 20)]]
    for agent_behavior in behaviors:
        safe_run_trials(agent_behavior.name, run_agent_generated_trial,
                        (disease, agent_behavior, N, rand), num_trials)


def run_agent_generated_trial(args: Tuple[Disease, AgentBehavior, int, Any])\
        -> Optional[Tuple[float, float, float]]:
    """
    args: (disease to use in the simulation,
           the behavior agents have when generating the network,
           the number of agents in the network,
           an instance of np.random.default_rng)
    """
    disease, agent_behavior, N, rand = args
    sim_len = 200
    sims_per_trial = 150
    net = make_agent_generated_network(N, agent_behavior)
    if net is None:
        return None

    to_flicker = partitioning.fluidc_partition(net.G, 50)
    proportion_flickering = len(to_flicker) / net.E
    social_good = rate_social_good(net)

    network_behavior = StaticFlickerBehavior(net.M, to_flicker, (True, False),
                                             "Probs don't change this")
    avg_sus = np.mean([np.sum(simulate(net.M, make_starting_sir(net.N, 1),
                                       disease, network_behavior, sim_len, None, rand)[-1][0] > 0)
                       for _ in range(sims_per_trial)]) / net.N

    return proportion_flickering, avg_sus, social_good


if __name__ == '__main__':
    agent_generated_entry_point(2)
