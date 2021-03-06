#!/usr/bin/python3
from network import Network
from typing import Iterable, List, Callable, Optional, Sequence, Tuple, Union
import networkx as nx
import numpy as np
import sys
from random import choice
from fileio import read_network
from analysis import COLORS, calc_prop_common_neighbors
import time
AgentBehavior = Callable[[nx.Graph], Tuple[nx.Graph, bool]]


def make_agent_generated_network(starting_point: Union[int, nx.Graph],
                                 behavior: AgentBehavior,
                                 max_steps: int = 150) -> Optional[Network]:
    """Use the provided behavior to make a network. Return None on timeout."""
    def make_initial_network() -> nx.Graph:
        if isinstance(starting_point, int):
            return nx.empty_graph(starting_point)  # type: ignore
        return starting_point

    G = make_initial_network()
    finished = False
    steps_taken = 0
    while not finished:
        if steps_taken > max_steps:
            return None
        G, finished = behavior(G)
        steps_taken += 1
    return Network(G)


def assign_colors(G: nx.Graph) -> List[str]:
    components = nx.connected_components(G)
    node_to_color = [(node, COLORS[i]) for i, component in enumerate(components)
                     for node in component]
    node_to_color.sort(key=lambda x: x[0])
    return [color for _, color in node_to_color]  # type: ignore


def homogenous_step(G: nx.Graph) -> None:
    """
    All agents behave the same, and that behave doesn't vary with time.
    The agents are trying to reach happy_number connections. If they are not connected
    to any other agents, they choose a random one to connect to. If they are connected
    to less than happy_number, they connect to one of the agents connected to their
    neighbor with the most common neighbors. If they have too many connections, they
    disconnect from the neighbor with the fewest common neighbors.
    """
    happy_number = 10
    for agent in G.nodes:
        neighbors = tuple(nx.neighbors(G, agent))
        # connect to a new neighbor
        if len(neighbors) == 0:
            to_add = choice(tuple(G.nodes))
            connect_agents(G, agent, to_add)
        elif len(neighbors) < happy_number:
            neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                    for neighbor in neighbors}
            closest_neighbor = max(neighbor_to_strength, key=lambda x: x[1])[0]
            new_neighbor_choices = set(nx.neighbors(G, closest_neighbor)) - {agent}
            if len(new_neighbor_choices) > 0:
                to_add = choice(tuple(new_neighbor_choices))
            else:
                to_add = choice(tuple(G.nodes))
            connect_agents(G, agent, to_add)
        # disconnect from a neighbor
        elif len(neighbors) > happy_number:
            neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                    for neighbor in neighbors}
            to_remove = min(neighbor_to_strength, key=lambda x: x[1])[0]
            G.remove_edge(agent, to_remove)


def make_two_type_step(bridge_agents: Iterable[int], normal_agents: Iterable[int])\
        -> Callable[[nx.Graph], None]:
    """
    agent_roles should contain two entries: 'bridge', 'normal'. The iterables
    associated with these keys should union to form the set of all nodes in G.
    normal agents will try to cluster around other agents.
    bridge agents will try to connect themselves to a few different clusters.
    """
    def two_type_step(G: nx.Graph) -> None:
        normal_lb = 2  # lower bound
        normal_ub = 10  # upper bound
        bridge_happy_number = 2

        # how a normal agent behaves
        for agent in normal_agents:
            neighbors = tuple(nx.neighbors(G, agent))
            # connect to a new neighbor
            if len(neighbors) < normal_lb:
                to_add = choice(tuple(G.nodes))
                connect_agents(G, agent, to_add)
            elif len(neighbors) < normal_ub:
                neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                        for neighbor in neighbors}
                closest_neighbor = max(neighbor_to_strength, key=lambda x: x[1])[0]
                new_neighbor_choices = set(nx.neighbors(G, closest_neighbor)) - {agent}
                if len(new_neighbor_choices) > 0:
                    to_add = choice(tuple(new_neighbor_choices))
                else:
                    to_add = choice(tuple(G.nodes))
                connect_agents(G, agent, to_add)
            # disconnect from a neighbor
            elif len(neighbors) > normal_ub:
                neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                        for neighbor in neighbors}
                to_remove = min(neighbor_to_strength, key=lambda x: x[1])[0]
                G.remove_edge(agent, to_remove)

        # how a bridge agent behaves
        for agent in bridge_agents:
            neighbors = tuple(nx.neighbors(G, agent))
            # search for more connections
            if len(neighbors) < bridge_happy_number:
                choices = [a for a in G.nodes if (a not in bridge_agents) and (a not in neighbors)]
                to_add = choice(choices)
                connect_agents(G, agent, to_add)
            # if the agent has enough connections, look for ones to prune
            else:
                # connections are invalid if they are to an agent that shares a common neighbor
                invalid_connections = [a for a in neighbors
                                       if calc_prop_common_neighbors(G, agent, a) > 0]
                if len(invalid_connections) == 0:
                    invalid_connections = neighbors
                to_remove = choice(invalid_connections)
                G.remove_edge(agent, to_remove)

    return two_type_step


class TimeBasedBehavior:
    def __init__(self, N: int,
                 lower_bound: int,
                 upper_bound: int,
                 steps_to_stable: int,
                 rand):
        """
        Agents try to have between [lower_bound, upper_bound] connections. However,
        behavior changes once an agent's connections have not changed for steps_to_stable
        steps. Whether or not they have changed is determined after all agents have taken
        an action, so if A connects to B, but B disconnects from A, A's connections will
        have not changed.

        In the unstable state, agents add neighbors if beneath lower_bound and remove agents
        if above upper_bound. Agents add a random agent adjacent to the agent with the most
        common neighbors. If that agent has no other neighbors, or the original agent has no
        neighbors, an agent is chosen at random to connect to.

        In the stable state, agents only look for more connections if they have less than
        upper_bound-1 connections. This is to minimize the probability that they start
        pruning connections after adding a new one.

        N: number of agents the simulation has.
        rand: an instance of np.random.default_rng
        """
        self._time_stable = np.zeros(N, np.uint64)
        self._lower_bound = lower_bound
        self._upper_bound = upper_bound
        self._steps_to_stable = steps_to_stable
        # agents are ints so, this is probably faster than a dict
        self._agent_to_previous_neighbors = [set() for _ in range(N)]
        self._steps_taken = 0
        self._rand = rand
        self.name = f'TimeBasedBehavior(N={N}, lb={lower_bound}, ub={upper_bound}, '\
                    f'sts={steps_to_stable})'

    def _unstable_behavior(self, G: nx.Graph, agent: int, neighbors: Sequence[int]):
        # add a neighbor if lonely
        if len(neighbors) < self._lower_bound:
            if len(neighbors) == 0:
                connect_agents(G, agent, choice(tuple(G.nodes)))
            else:
                neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                        for neighbor in neighbors}
                closest_neighbor = max(neighbor_to_strength, key=lambda x: x[1])[0]
                # TODO: neighbor_choices will likely include agents already adjacent to agent.
                # These should be filtered out.
                neighbor_choices = tuple(set(G[closest_neighbor]) - {agent})
                to_add = choice(neighbor_choices if len(neighbor_choices) > 0 else tuple(G.nodes))
                connect_agents(G, agent, to_add)
        # remove a neighbor if overwhelmed
        elif len(neighbors) > self._upper_bound:
            neighbor_to_strength = {(neighbor, calc_prop_common_neighbors(G, agent, neighbor))
                                    for neighbor in neighbors}
            farthest_neighbor = min(neighbor_to_strength, key=lambda x: x[1])[0]
            G.remove_edge(agent, farthest_neighbor)

    def _stable_behavior(self, G: nx.Graph, agent: int, neighbors: Sequence[int]):
        if len(neighbors) < self._upper_bound - 1:
            neighbor_choices = [n for n in G.nodes
                                if all((self._time_stable[n] > self._steps_to_stable,
                                        n not in neighbors,
                                        len(G[n]) < self._upper_bound - 1))]
            if len(neighbor_choices) > 0:
                connect_agents(G, agent, choice(neighbor_choices))

    def __call__(self, G: nx.Graph) -> Tuple[nx.Graph, bool]:
        H: nx.Graph = nx.Graph(G)
        agents = np.array(H.nodes)
        self._rand.shuffle(agents)
        for agent in agents:
            neighbors = tuple(H[agent])
            # choose behavior
            if self._time_stable[agent] < self._steps_to_stable:
                self._unstable_behavior(H, agent, neighbors)
            else:
                self._stable_behavior(H, agent, neighbors)

        # Update satisfaction. Agents are satisifed by having consistant neighbors
        for agent in agents:
            neighbors = set(H[agent])
            if self._agent_to_previous_neighbors[agent] == neighbors:
                self._time_stable[agent] += 1
            else:
                self._time_stable[agent] = 0
            self._agent_to_previous_neighbors[agent] = neighbors

        self._steps_taken += 1
        return H, (self._time_stable > 0).all() and nx.is_connected(H)  # type: ignore


def connect_agents(G: nx.Graph, u: int, v: int) -> None:
    """
    Connect agents u and v in the network G.
    """
    G.add_edge(u, v)


def int_or_none(string: str) -> Optional[int]:
    try:
        return int(string)
    except ValueError:
        return None


def agent_based_entry_point():
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <network or number of agents>')
        return

    N = int_or_none(sys.argv[1])
    if N is None:
        net = read_network(sys.argv[1])
        N = net.N
    else:
        net = Network(nx.empty_graph(N))

    rand = np.random.default_rng()
    for i in range(50):
        start_time = time.time()
        H = make_agent_generated_network(nx.Graph(net.G), TimeBasedBehavior(N, 4, 6, 15, rand))
        if H is None:
            print(f'Failure on iteration {i} ({time.time()-start_time:.2f} s).')
        else:
            print(f'Success on iteration {i} ({time.time()-start_time:.2f} s).')


if __name__ == '__main__':
    try:
        agent_based_entry_point()
    except EOFError:
        print('Goodbye.')
    except KeyboardInterrupt:
        print('Goodbye')
