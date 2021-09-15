import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting
from sklearn.metrics import jaccard_score, recall_score, precision_score, f1_score, roc_auc_score, confusion_matrix, accuracy_score

from nets.generators.fresh_generators import get_generator
from utils.plot_utils import collect_dataframes

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

    return all_families, n_families


def compute_scores(id_to_dataframe_dict,  # run ID - result dataframe dictionary
                   dest_file,  # the filename to save the resulting figure to
                   k,
                   zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute some Score values (accuracy, jaccard, recall, precision, f1 score) for a dataframe/key combination.
    Args:
        id_to_dataframe_dict: Run ID - result dataframe dictionary
        dest_file: The filename to save the resulting scores to
        k:
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    y_true = id_to_dataframe_dict['run']['label']
    y_pred = id_to_dataframe_dict['run']['{}-NN_pred'.format(k)]

    # compute scores
    scores_df = pd.DataFrame({'accuracy': [accuracy_score(y_true, y_pred)],
                              'jaccard': [jaccard_score(y_true, y_pred, average='micro', zero_division=zero_division),
                                          jaccard_score(y_true, y_pred, average='macro', zero_division=zero_division),
                                          jaccard_score(y_true, y_pred, average='weighted',
                                                        zero_division=zero_division)],
                              'recall': [recall_score(y_true, y_pred, average='micro', zero_division=zero_division),
                                         recall_score(y_true, y_pred, average='macro', zero_division=zero_division),
                                         recall_score(y_true, y_pred, average='weighted', zero_division=zero_division)],
                              'precision': [
                                  precision_score(y_true, y_pred, average='micro', zero_division=zero_division),
                                  precision_score(y_true, y_pred, average='macro', zero_division=zero_division),
                                  precision_score(y_true, y_pred, average='weighted', zero_division=zero_division)],
                              'f1': [f1_score(y_true, y_pred, average='micro', zero_division=zero_division),
                                     f1_score(y_true, y_pred, average='macro', zero_division=zero_division),
                                     f1_score(y_true, y_pred, average='weighted', zero_division=zero_division)]},
                             index=['micro', 'macro', 'weighted']).T

    # open destination file
    with open(dest_file, "w") as output_file:
        # serialize scores_df dataframe as a csv file and save it
        scores_df.to_csv(output_file)


def plot_confusion_matrix(conf_mtx,
                          filename,
                          families):
    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))
    # fig, ax = plt.subplots()
    im = plt.imshow(conf_mtx)

    threshold = im.norm(conf_mtx.max()) / 2
    textcolors = ("white", "black")

    plt.xticks(np.arange(len(families)), families, rotation=45, ha="right", rotation_mode="anchor")
    plt.yticks(np.arange(len(families)), families)

    plt.xlabel('predicted')
    plt.ylabel('ground truth')

    # Loop over data dimensions and create text annotations.
    for i in range(len(families)):
        for j in range(len(families)):
            plt.text(j, i, conf_mtx[i, j], ha="center", va="center",
                     color=textcolors[int(im.norm(conf_mtx[i, j]) > threshold)])

    plt.title("Confusion matrix")
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def create_confusion_matrixes(results_file,  # complete path to results.csv which contains the output of a model run
                              families,
                              knn_k_min=1,
                              knn_k_max=11):
    """ Create confusion matrixes for the contrastive learning model using odd numbers of nearest neighbors (k) between
        knn_k_min and knn_k_max.

    Args:
        results_file: Complete path to a results.csv file that contains the output of
                      a model run.
        families:
        knn_k_min:
        knn_k_max:
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for all odd values of k from knn_k_min to knn_k_max (included)
        for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):

            output_filename = os.path.join(tempdir, "contrastive_learning_{}-nn_confusion_matrix.png".format(k))

            # create run ID - filename correspondence dictionary (containing just one result file)
            id_to_resultfile_dict = {'run': results_file}

            # read csv result file and obtain a run ID - result dataframe dictionary
            id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

            y_true = id_to_dataframe_dict['run']['label']
            y_pred = id_to_dataframe_dict['run']['{}-NN_pred'.format(k)]

            conf_mtx = confusion_matrix(y_true, y_pred)
            plot_confusion_matrix(conf_mtx, output_filename, families)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "contrastive_learning_scores")


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       knn_k_min=1,
                       knn_k_max=11,
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute all scores for all families.

    Args:
        results_file: Path to results.csv containing the output of a model run
        knn_k_min:
        knn_k_max:
        zero_division: Sets the value to return when there is a zero division
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:

        # for all odd values of k from knn_k_min to knn_k_max (included)
        for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):
            output_filename = os.path.join(tempdir, "contrastive_learning_{}-nn_scores.csv".format(k))

            # create run ID - filename correspondence dictionary (containing just one result file)
            id_to_resultfile_dict = {'run': results_file}

            # read csv result file and obtain a run ID - result dataframe dictionary
            id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

            compute_scores(id_to_dataframe_dict=id_to_dataframe_dict,
                           dest_file=output_filename,
                           k=k,
                           zero_division=zero_division)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "contrastive_learning_scores")


@baker.command
def compute_contrastive_learning_results(results_file,  # path to results.csv containing the output of a model run
                                         fresh_ds_path,  # fresh dataset root directory (where to find .dat files)
                                         knn_k_min=1,
                                         knn_k_max=11,
                                         zero_division=1.0):  # sets the value to return when there is a zero division
    """ Takes a result file from a feedforward neural network model and produces results plots, computes per-family
        scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
        knn_k_min:
        knn_k_max:
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # start mlflow run
    with mlflow.start_run():
        # get some fresh_dataset related variables
        all_families, n_families = get_fresh_dataset_info(ds_path=fresh_ds_path)

        # compute all run scores
        compute_run_scores(results_file=results_file,
                           knn_k_min=knn_k_min,
                           knn_k_max=knn_k_max,
                           zero_division=zero_division)

        create_confusion_matrix(results_file=results_file,
                                families=all_families)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
