from dataclasses import dataclass
from network import Network
from sim_dynamic import (Disease, PressureBehavior, RandomFlickerBehavior,
                         StaticFlickerBehavior, UpdateConnections, make_starting_sir, simulate)
from typing import (Any, Callable, Collection, List, Optional, Tuple, TypeVar,
                    Sequence, Dict)
from abc import ABC, abstractmethod
from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import wasserstein_distance
import os
import csv
import sys
sys.path.append('')
from customtypes import Array, Number
T = TypeVar('T')


def _create_directory(directory: str):
    if not os.path.exists(directory):
        os.mkdir(directory)


class BasicExperimentResult:
    def __init__(self, name: str,
                 trial_to_perc_sus: Sequence[Number],
                 trial_to_proportion_flickering_edges: Sequence[Number],
                 trial_to_social_good: Sequence[Number]):
        """
        A class for aggregating and recording results of experiments on one type
        of network with a fixed flicker rate.

        network_class: A string describing what type of network the simulations were run on.
        trial_to_perc_sus: The percentage (or probably the average percentage)
                           of agents that ended the experiment susceptible.
        trial_to_proportion_flickering_edges: The trial should line up with the
                                              trial in trial_to_results.
        trial_to_social_good: The trial should line up with the trial in trial_to_results.
        """
        self.name = name
        self.trial_to_perc_sus = trial_to_perc_sus
        self.trial_to_proportion_flickering_edges = trial_to_proportion_flickering_edges
        self.trial_to_social_good = trial_to_social_good

    def save_csv(self, directory: str) -> None:
        """Save a CSV with the stored data."""
        _create_directory(directory)

        with open(os.path.join(directory, self.name+'.csv'), 'w', newline='') as file:
            writer = csv.writer(file, dialect=csv.excel)
            writer.writerow(['Percentage of Susceptible Agents'])
            writer.writerow(self.trial_to_perc_sus)
            writer.writerow(['Proportion Flickering Edges'])
            writer.writerow(self.trial_to_proportion_flickering_edges)
            writer.writerow(['Social Good'])
            writer.writerow(self.trial_to_social_good)

    def save_box_plots(self, directory: str) -> None:
        """Save box plots of all the stored data."""
        _create_directory(directory)

        plt.figure()
        plt.title(f'Percentage Suseptible for\n{self.name}')
        plt.boxplot(self.trial_to_perc_sus, notch=False)
        plt.savefig(os.path.join(directory,
                                 f'Percentage Suseptible for {self.name}.png'),
                    format='png')

        plt.figure()
        plt.title(f'Proportion Flickering Edges in\n{self.name}')
        plt.boxplot(self.trial_to_proportion_flickering_edges, notch=False)
        plt.savefig(os.path.join(directory,
                                 f'Proportion Flickering Edges in {self.name}.png'),
                    format='png')

        plt.figure()
        plt.title(f'Social Good on\n{self.name}')
        plt.boxplot(self.trial_to_social_good, notch=False)
        plt.savefig(os.path.join(directory,
                                 f'Social Good on {self.name}.png'),
                    format='png')

    def save_perc_sus_vs_social_good(self, directory: str,
                                     *, static_x: bool = True, static_y: bool = True) -> None:
        """Save a scatter plot of percentage susctible vs social good"""
        _create_directory(directory)

        plt.figure()
        plt.title(f'Resilience vs Social Good Trade-off Space\n{self.name}')
        plt.xlabel('Percentage Susceptible')
        plt.ylabel('Social Good')
        if static_x:
            plt.xlim(0, 1)
        if static_y:
            plt.ylim(0, 1)
        plt.scatter(self.trial_to_perc_sus, self.trial_to_social_good)
        plt.savefig(os.path.join(directory,
                                 f'R vs SG Trade off Space for {self.name}.png'),
                    format='png')


class FlickerComparisonResult:
    def __init__(self, network_name: str,
                 sims_per_behavior: int,
                 sim_len: int,
                 proportion_flickering_edges: float,
                 behavior_to_survival_rate: Dict[str, Sequence[float]],
                 baseline_behavior: str):
        """
        A class for gathering data on the effectives of different behaviors in comparision
        to each other.

        network_name
        sims_per_behavior
        behavior_to_num_sus: How many agents were still susceptible at the end of
                            each simulation with the specified behavior.
        baseline_behavior: The name of the behavior to computer the
                        Wasserstein distance of the others against.
        """
        self.network_name = network_name
        self.sims_per_behavior = sims_per_behavior
        self.sim_len = sim_len
        self.proportion_flickering_edges = proportion_flickering_edges
        self.behavior_to_survival_rate = behavior_to_survival_rate
        # Fail early if an incorrect name is supplied.
        if baseline_behavior not in behavior_to_survival_rate:
            print(f'{baseline_behavior} is not in {list(behavior_to_survival_rate.keys())}.'
                  'Fix this before continuing.')
            exit(1)
        self.baseline_behavior = baseline_behavior

    def save(self, directory: str, with_histograms: bool = False) -> None:
        """Save a histogram and a text file with analysis information in directory."""
        path = os.path.join(directory, self.network_name)
        _create_directory(path)

        # File Heading
        file_lines = [f'Name: {self.network_name}\n',
                      f'Number of sims per behavior: {self.sims_per_behavior}\n',
                      f'Simulation length: {self.sim_len}\n'
                      f'Proportion of edges flickering: {self.proportion_flickering_edges:.4f}\n\n']
        baseline_distribution = self.behavior_to_survival_rate[self.baseline_behavior]
        for behavior_name, results in self.behavior_to_survival_rate.items():
            # possibly save histograms
            if with_histograms:
                plt.figure()
                title = f'{self.network_name} {behavior_name}\n'\
                    f'sims={self.sims_per_behavior} sim_len={self.sim_len}'
                plt.title(title)
                plt.xlabel('Number of Susceptible Agents')
                plt.ylabel('Frequency')
                plt.hist(results, bins=None)
                plt.savefig(os.path.join(path, title+'.png'), format='png')

            # create a text entry for each behavior
            file_lines += [f'{behavior_name}\n',
                           f'Min:{np.min(results) : >20}\n',
                           f'Max:{np.max(results) : >20}\n',
                           f'Median:{np.median(results) : >20}\n',
                           f'Mean:{np.mean(results) : >20.3f}\n',
                           f'EMD from {self.baseline_behavior}:'
                           f'{wasserstein_distance(results, baseline_distribution) : >20.3f}\n\n']

        # save text entries
        with open(os.path.join(path, f'Report on {self.network_name}.txt'), 'w') as file:
            file.writelines(file_lines)


class PressureComparisonResult:
    def __init__(self, network_name: str,
                 disease: Disease,
                 sims_per_behavior: int,
                 behavior_to_survival_rate: Dict[str, Array],
                 baseline_behavior: str):
        """
        A class for gathering data on the effectives of different behaviors in comparision
        to each other.

        network_name
        sims_per_behavior
        behavior_to_num_sus: How many agents were still susceptible at the end of
                            each simulation with the specified behavior.
        baseline_behavior: The name of the behavior to computer the
                        Wasserstein distance of the others against.
        """
        self.network_name = network_name
        self.sims_per_behavior = sims_per_behavior
        self.behavior_to_survival_rate = behavior_to_survival_rate
        # Fail early if an incorrect name is supplied.
        if baseline_behavior not in behavior_to_survival_rate:
            print(f'{baseline_behavior} is not in {list(behavior_to_survival_rate.keys())}.'
                  'Fix this before continuing.')
            exit(1)
        self.baseline_behavior = baseline_behavior
        self.disease = disease

    def save(self, directory: str, with_histograms: bool = False) -> None:
        """Save a histogram and a text file with analysis information in directory."""
        path = os.path.join(directory, self.network_name)
        _create_directory(path)

        # File Heading
        file_lines = [f'Name: {self.network_name}\n',
                      f'Disease: {self.disease}\n',
                      f'Number of sims per behavior: {self.sims_per_behavior}\n\n']
        baseline_distribution = self.behavior_to_survival_rate[self.baseline_behavior]
        for behavior_name, results in self.behavior_to_survival_rate.items():
            # possibly save histograms
            if with_histograms:
                plt.figure()
                title = f'{self.network_name} {behavior_name}\n'\
                    f'sims={self.sims_per_behavior}'
                plt.title(title)
                plt.xlabel('Number of Susceptible Agents')
                plt.ylabel('Frequency')
                plt.hist(results, bins=None)
                plt.savefig(os.path.join(path, title+'.png'), format='png')

            # create a text entry for each behavior
            file_lines += [f'{behavior_name}\n',
                           f'Min:{np.min(results) : >20}\n',
                           f'Max:{np.max(results) : >20}\n',
                           f'Median:{np.median(results) : >20}\n',
                           f'Mean:{np.mean(results) : >20.3f}\n',
                           f'EMD from {self.baseline_behavior}:'
                           f'{wasserstein_distance(results, baseline_distribution) : >20.3f}\n\n']

        # save text entries
        with open(os.path.join(path, f'Report on {self.network_name}.txt'), 'w') as file:
            file.writelines(file_lines)

    def save_raw(self, directory: str) -> None:
        path = os.path.join(directory, self.network_name)
        _create_directory(path)

        with open(os.path.join(path, 'raw_data.csv'), 'w', newline='') as file:
            writer = csv.writer(file, dialect=csv.excel)
            for behavior, survival_rates in self.behavior_to_survival_rate.items():
                writer.writerow([behavior])
                writer.writerow(survival_rates)


def safe_run_trials(name: str, trial_func: Callable[[T], Optional[Tuple[float, float, float]]],
                    args: T, num_trials: int, max_failures: int = 10) -> None:
    """Run trials until too many failures occur, exit if this happens."""
    results: List[Tuple[float, float, float]] = []
    failures_since_last_success = 0
    pbar = tqdm(total=num_trials, desc=f'Failures: {failures_since_last_success}')
    while len(results) < num_trials:
        if failures_since_last_success >= max_failures:
            print(f'Failure limit has been reached. {name} is not feasible.')
            exit(1)

        result = trial_func(args)
        if result is None:
            failures_since_last_success += 1
            update_amount = 0
        else:
            results.append(result)
            failures_since_last_success = 0
            update_amount = 1
        pbar.set_description(f'Failures: {failures_since_last_success}')
        pbar.update(update_amount)

    trial_to_flickering_edges, trial_to_avg_sus, trial_to_social_good = zip(*results)
    experiment_results = BasicExperimentResult(name, trial_to_avg_sus,
                                               trial_to_flickering_edges, trial_to_social_good)
    experiment_results.save_perc_sus_vs_social_good('results')


def simulate_return_survival_rate(net: Network, disease: Disease,
                                  behavior: UpdateConnections, rng) -> float:
    sir0 = make_starting_sir(net.N, 1, rng)
    return np.sum(simulate(net.M, sir0, disease, behavior, 100, None, rng)[-1][0] > 0) / net.N


class FlickerConfig(ABC):
    @abstractmethod
    def make_behavior(self, M: np.ndarray,
                      edges_to_flicker: Collection[Tuple[int, int]])\
            -> UpdateConnections:
        """Return a some flicker behavior."""
        pass


class StaticFlickerConfig(FlickerConfig):
    def __init__(self, flicker_pattern: Sequence[bool],
                 name: Optional[str] = None) -> None:
        self.flicker_pattern = flicker_pattern
        self.name = name

    def make_behavior(self, M: np.ndarray,
                      edges_to_flicker: Collection[Tuple[int, int]])\
            -> StaticFlickerBehavior:
        return StaticFlickerBehavior(M, edges_to_flicker,
                                     self.flicker_pattern,
                                     self.name)


class RandomFlickerConfig(FlickerConfig):
    def __init__(self, flicker_probability: float,
                 name: Optional[str] = None,
                 rand: Optional[Any] = None):
        self.flicker_probability = flicker_probability
        self.name = name
        self.rand = rand

    def make_behavior(self, M: np.ndarray,
                      edges_to_flicker: Collection[Tuple[int, int]])\
            -> RandomFlickerBehavior:
        if self.rand is None:
            return RandomFlickerBehavior(M, edges_to_flicker,
                                         self.flicker_probability,
                                         self.name)
        return RandomFlickerBehavior(M, edges_to_flicker,
                                     self.flicker_probability,
                                     self.name, self.rand)


@dataclass
class PressureConfig:
    radius: int
    flicker_probability: float
    rng: Any
    name: Optional[str] = None

    def make_behavior(self, net: Network) -> PressureBehavior:
        return PressureBehavior(net, self.radius, self.flicker_probability, self.rng, self.name)
