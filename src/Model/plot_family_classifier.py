import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle

from nets.generators.fresh_generators import get_generator
from utils.plot_utils import *

SMALL_SIZE = 18
MEDIUM_SIZE = 20
BIGGER_SIZE = 22

plt.rc('font', size=MEDIUM_SIZE)  # controls default text sizes
plt.rc('axes', titlesize=MEDIUM_SIZE)  # fontsize of the axes title
plt.rc('axes', labelsize=MEDIUM_SIZE)  # fontsize of the x and y labels
plt.rc('xtick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('ytick', labelsize=MEDIUM_SIZE)  # fontsize of the tick labels
plt.rc('legend', fontsize=MEDIUM_SIZE)  # legend fontsize
plt.rc('figure', titlesize=BIGGER_SIZE)  # fontsize of the figure title

matplotlib.use('Agg')  # Select 'Agg' as the backend used for rendering and GUI integration

# define default family colors to be used in the graph
default_family_colors = ['r', 'r', 'r',
                         'g', 'g', 'b',
                         'b', 'm', 'm',
                         'c']

# define default family linestyles to be used in the graph
default_family_linestyles = [':', '--', '-.',
                             ':', '--', ':',
                             '--', ':', '--',
                             ':']


def get_fresh_dataset_info(ds_path):  # fresh dataset root directory (where to find .dat files)
    """ Get some fresh_dataset specific variables.

    Args:
        ds_path: Fresh dataset root directory (where to find .dat files)
    Returns:
        all_families, n_families, style_dict
    """

    # load fresh dataset generator
    generator = get_generator(ds_root=ds_path,
                              batch_size=1000,
                              return_shas=False,
                              shuffle=False)

    # get label to signature function from the dataset (used to convert numerical labels to family names)
    label_to_sig = generator.dataset.label_to_sig

    # get total number of families in fresh dataset
    n_families = generator.dataset.n_families

    # compute all families list
    all_families = [label_to_sig(i) for i in range(n_families)]

    # combine the previously defined information into a "style" dictionary (e.g. {'loki': ('r', ':'), ..})
    style_dict = {fam: (color, linestyle) for fam, color, linestyle in zip(all_families,
                                                                           default_family_colors,
                                                                           default_family_linestyles)}

    return all_families, n_families, style_dict


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       families,  # families (list) to extract results for
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute all scores for all families.

    Args:
        results_file: Path to results.csv containing the output of a model run
        families: Families (list) to extract results for
        zero_division: Sets the value to return when there is a zero division
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for each family in all_families list, compute scores
        for fam in families:
            output_filename = os.path.join(tempdir, fam + "_scores.csv")

            compute_scores(results_file=results_file,
                           key=fam,
                           dest_file=output_filename,
                           zero_division=zero_division)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "family_class_fresh_scores")


def plot_run_results(results_file,  # path to results.csv containing the output of a model run
                     families,  # families (list) to extract results for
                     style_dict):  # style dictionary (e.g. {'loki': ('r', ':'), ..})
    """ Takes a result file from a feedforward neural network model that includes all families, and produces multiple
    overlaid ROC plots for each family individually.

    Args:
        results_file: Path to results.csv containing the output of a model run
        families: Families (list) to extract results for
        style_dict: Style dictionary (e.g. {'loki': ('r', ':'), ..})
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # create temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        output_filename = os.path.join(tempdir, "model_results.png")

        # produce multiple overlaid ROC plots (one for each family individually) and save the overall figure to file
        plot_family_results(dataframe=id_to_dataframe_dict['run'],
                            filename=output_filename,
                            families=families,
                            style_dict=style_dict)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "family_class_fresh_results")


@baker.command
def compute_all_family_class_results(results_file,  # path to results.csv containing the output of a model run
                                     fresh_ds_path,  # fresh dataset root directory (where to find .dat files)
                                     zero_division=1.0):  # sets the value to return when there is a zero division
    """ Takes a result file from a feedforward neural network model and produces results plots, computes per-family
        scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # start mlflow run
    with mlflow.start_run():
        # get some fresh_dataset related variables
        all_families, n_families, style_dict = get_fresh_dataset_info(ds_path=fresh_ds_path)

        # compute all run scores
        compute_run_scores(results_file=results_file,
                           families=all_families,
                           zero_division=zero_division)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
