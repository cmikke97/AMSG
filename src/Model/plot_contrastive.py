# Copyright 2021, Crepaldi Michele.
#
# Developed as a thesis project at the TORSEC research group of the Polytechnic of Turin (Italy) under the supervision
# of professor Antonio Lioy and engineer Andrea Atzeni and with the support of engineer Andrea Marcelli.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

import json  # json encoder and decoder
import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting
from sklearn.metrics import jaccard_score  # computes the Jaccard similarity coefficient score
from sklearn.metrics import recall_score  # computes the recall score
from sklearn.metrics import precision_score  # computes the precision score
from sklearn.metrics import f1_score  # computes the f1 score
from sklearn.metrics import confusion_matrix  # computes confusion matrix to evaluate the accuracy of a classification
from sklearn.metrics import accuracy_score  # computes the Accuracy classification score

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


def plot_score_trend(values_dict,  # dict containing the values of the score to plot
                     filename,  # path where to save the plot
                     key,  # name of the score
                     style,  # style to use in the plot
                     std_alpha=.2):  # standard deviation alpha value
    """ Plot score trend given a dict of values as input.

    Args:
        values_dict: Dict containing the values of the score to plot
        filename: Path where to save the plot
        key: Name of the score
        style: Style to use in the plot
        std_alpha: Standard deviation alpha value
    """

    # if the style was not defined (it is None)
    if style is None:
        raise ValueError('No default style information is available for contrastive learning model {} score;'
                         ' please provide (linestyle, color)'.format(key))
    else:  # otherwise (the style was defined)
        color, linestyle = style  # get linestyle and color from style

    # get x values from dict
    x = np.array([k for k in values_dict.keys()])
    # get mean and standard deviation y values from dict
    y_mean = np.array([v['mean'] for v in values_dict.values()])
    y_std = np.array([v['std'] for v in values_dict.values()])

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # plot mean score trend
    plt.plot(x, y_mean, color + linestyle, linewidth=2.0)

    # fill uncertainty (standard deviation) area around curve
    plt.fill_between(x,
                     y_mean - y_std,
                     y_mean + y_std,
                     color=color,
                     alpha=std_alpha)

    plt.ylabel(key)  # set the label for the y-axis
    plt.xlabel('k')  # set the label for the x-axis
    plt.title("Contrastive model {} results".format(key))  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def get_fresh_dataset_info(ds_path):  # fresh dataset root directory (where to find .dat files)
    """ Get some fresh_dataset specific variables.

    Args:
        ds_path: Fresh dataset root directory (where to find .dat files)
    Returns:
        all_families (list containing all the families of interst), n_families (the number of families of interest)
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
                   k,  # number of nearest neighbours used with the k-NN algorithm
                   zero_division=1.0):  # sets the value to return when there is a zero division
    """ Estimate some micro, macro and weighted averaged Score values (jaccard similarity, recall, precision, f1 score)
    and the macro for a dataframe/key combination.

    Args:
        id_to_dataframe_dict: Run ID - result dataframe dictionary
        dest_file: The filename to save the resulting scores to
        k: Number of nearest neighbours used with the k-NN algorithm
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised
    """

    # get ground truth labels
    y_true = id_to_dataframe_dict['run']['label']
    # get model predictions
    y_pred = id_to_dataframe_dict['run']['{}-NN_pred'.format(k)]

    # compute scores
    scores_df = pd.DataFrame({'accuracy': [accuracy_score(y_true, y_pred), '-', '-'],
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


def plot_confusion_matrix(conf_mtx,  # ndarray containing the confusion matrix to plot
                          filename,  # path where to save the generated confusion matrix plot
                          families):  # list of families of interest
    """ Plot and save to file a figure containing the confusion matrix passed as input.

    Args:
        conf_mtx: Ndarray containing the confusion matrix to plot
        filename: Path where to save the generated confusion matrix plot
        families: List of families of interest
    """

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # plot confusion matrix
    im = plt.imshow(conf_mtx)

    # get text color thresholds
    threshold = im.norm(conf_mtx.max()) / 2
    # set text colors
    textcolors = ("white", "black")

    # plot ticks on x and y axes
    plt.xticks(np.arange(len(families)), families, rotation=45, ha="right", rotation_mode="anchor")
    plt.yticks(np.arange(len(families)), families)

    # plot labels for x and y axes
    plt.xlabel('predicted')
    plt.ylabel('ground truth')

    # loop over data dimensions and create text annotations
    for i in range(len(families)):
        for j in range(len(families)):
            # plot text annotation
            plt.text(j, i, conf_mtx[i, j], ha="center", va="center",
                     color=textcolors[int(im.norm(conf_mtx[i, j]) > threshold)])

    plt.title("Confusion matrix")  # plot figure title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def create_confusion_matrixes(results_file,  # complete path to results.csv which contains the output of a model run
                              families,  # list of families of interest
                              knn_k_min=1,  # min number of nearest neighbours to use with k-NN algorithm
                              knn_k_max=11):  # max number of nearest neighbours to use with k-NN algorithm
    """ Create confusion matrixes for the contrastive learning model using odd numbers of nearest neighbors (k) between
        knn_k_min and knn_k_max.

    Args:
        results_file: Complete path to a results.csv file that contains the output of a model run.
        families: List of families of interest
        knn_k_min: Min number of nearest neighbours to use when applying the k-NN algorithm
        knn_k_max: Max number of nearest neighbours to use when applying the k-NN algorithm
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for all odd values of k from knn_k_min to knn_k_max (included)
        for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):
            # create output file path
            output_filename = os.path.join(tempdir, "contrastive_learning_{}-nn_confusion_matrix.png".format(k))

            # create run ID - filename correspondence dictionary (containing just one result file)
            id_to_resultfile_dict = {'run': results_file}

            # read csv result file and obtain a run ID - result dataframe dictionary
            id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

            # get ground truth labels
            y_true = id_to_dataframe_dict['run']['label']
            # get model predictions
            y_pred = id_to_dataframe_dict['run']['{}-NN_pred'.format(k)]

            # create confusion matrix
            conf_mtx = confusion_matrix(y_true, y_pred)
            # plot confusion matrix
            plot_confusion_matrix(conf_mtx, output_filename, families)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "contrastive_learning_scores")


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       knn_k_min=1,  # min number of nearest neighbours to use with k-NN algorithm
                       knn_k_max=11,  # max number of nearest neighbours to use with k-NN algorithm
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute multi-class classification scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        knn_k_min: Min number of nearest neighbours to use when applying the k-NN algorithm
        knn_k_max: Max number of nearest neighbours to use when applying the k-NN algorithm
        zero_division: Sets the value to return when there is a zero division
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # for all odd values of k from knn_k_min to knn_k_max (included)
        for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):
            # create output file path
            output_filename = os.path.join(tempdir, "contrastive_learning_{}-nn_scores.csv".format(k))

            # create run ID - filename correspondence dictionary (containing just one result file)
            id_to_resultfile_dict = {'run': results_file}

            # read csv result file and obtain a run ID - result dataframe dictionary
            id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

            # compute multi-class classification scores
            compute_scores(id_to_dataframe_dict=id_to_dataframe_dict,
                           dest_file=output_filename,
                           k=k,
                           zero_division=zero_division)

            # log output file as artifact
            mlflow.log_artifact(output_filename, "contrastive_learning_scores")


@baker.command
def compute_contrastive_learning_results(results_file,  # path to results.csv containing the output of a model run
                                         fresh_ds_path,  # fresh dataset root directory (where to find .dat files)
                                         knn_k_min=1,  # min number of nearest neighbours to use with k-NN algorithm
                                         knn_k_max=11,  # max number of nearest neighbours to use with k-NN algorithm
                                         zero_division=1.0):  # sets the value to return when there is a zero division
    """ Take a contrastive model result file and produce multi-class classification scores and confusion matrix.

    Args:
        results_file: Path to results.csv containing the output of a model run
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
        knn_k_min: Min number of nearest neighbours to use when applying the k-NN algorithm
        knn_k_max: Max number of nearest neighbours to use when applying the k-NN algorithm
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

        # create confusion matrix
        create_confusion_matrixes(results_file=results_file,
                                  families=all_families,
                                  knn_k_min=knn_k_min,
                                  knn_k_max=knn_k_max)


@baker.command
def plot_all_scores_trends(run_to_filename_json,  # run - filename json file path
                           knn_k_min=1,  # min number of nearest neighbours to use when applying the k-NN algorithm
                           knn_k_max=11):  # max number of nearest neighbours to use when applying the k-NN algorithm
    """ Plot contrastive model classification scores trends.

    Args:
        run_to_filename_json: A json file that contains a key-value map that links run IDs to the full path to a
                              results file (including the file name)
        knn_k_min: Min number of nearest neighbours to use when applying the k-NN algorithm
        knn_k_max: Max number of nearest neighbours to use when applying the k-NN algorithm
    """

    # start mlflow run
    with mlflow.start_run():
        # open json containing run ID - dir correspondences and decode it as json object
        id_to_resultfile_dict = json.load(open(run_to_filename_json, 'r'))

        # initialize some variables
        accuracies = {}
        scores = {
            'jaccard': {'micro': {}, 'macro': {}, 'weighted': {}},
            'recall': {'micro': {}, 'macro': {}, 'weighted': {}},
            'precision': {'micro': {}, 'macro': {}, 'weighted': {}},
            'f1': {'micro': {}, 'macro': {}, 'weighted': {}}
        }

        # create temporary directory
        with tempfile.TemporaryDirectory() as tempdir:

            # for each element in the run ID - filename dictionary
            for key, val in id_to_resultfile_dict.items():
                # for the odd values of 'k' from 'knn_k_min' to 'knn_k_min'
                for k in range(knn_k_min if knn_k_min % 2 else knn_k_min + 1, knn_k_max + 1, 2):
                    # create input model results path
                    curr_scores_filepath = os.path.join(val, "contrastive_learning_{}-nn_scores.csv".format(k))

                    # read as python object the csv results file
                    curr_dataframe = pd.read_csv(curr_scores_filepath, index_col=0)

                    # if it is the first cycle for the current value of k -> initialize accuracy[k]
                    if str(k) not in accuracies.keys():
                        accuracies[str(k)] = []

                    # append to accuracies[k] the value of accuracy found in the file
                    accuracies[str(k)].append(float(curr_dataframe.loc['accuracy', 'micro']))

                    # for each score in the 'scores' dict
                    for score_name in scores.keys():
                        # if it is the first cycle for the current value of k for the current score
                        # -> initialize 'scores' dict subelements
                        if str(k) not in scores[score_name]['micro'].keys():
                            scores[score_name]['micro'][str(k)] = []
                        if str(k) not in scores[score_name]['macro'].keys():
                            scores[score_name]['macro'][str(k)] = []
                        if str(k) not in scores[score_name]['weighted'].keys():
                            scores[score_name]['weighted'][str(k)] = []

                        # append to the 'scores' dict sub elements the values got from the results file
                        scores[score_name]['micro'][str(k)].append(float(curr_dataframe.loc[score_name, 'micro']))
                        scores[score_name]['macro'][str(k)].append(float(curr_dataframe.loc[score_name, 'macro']))
                        scores[score_name]['weighted'][str(k)].append(float(curr_dataframe.loc[score_name, 'weighted']))

            # compute mean and standard deviation of the accuracy score (per value of k)
            accuracies = {
                k: {
                    'mean': float(np.mean(v, dtype=np.float32)),
                    'std': float(np.std(v, dtype=np.float32))
                } for k, v in accuracies.items()
            }

            # compute the mean and standard deviation of all multi-class classification scores (per value of k)
            scores = {
                score_key: {
                    avg_key: {
                        k: {
                            'mean': float(np.mean(v, dtype=np.float32)),
                            'std': float(np.std(v, dtype=np.float32))
                        } for k, v in avg_value.items()
                    } for avg_key, avg_value in score_value.items()
                } for score_key, score_value in scores.items()
            }

            # create output file name
            acc_filename = os.path.join(tempdir, 'accuracy.png')
            # plot accuracy score trend
            plot_score_trend(accuracies, filename=acc_filename, key='accuracy', style=('k', '-'))
            # log file as artifact
            mlflow.log_artifact(acc_filename, "contrastive_model_mean_results")

            # for each score type in 'scores'
            for key, val in scores.items():
                # create output file names
                filename_micro = os.path.join(tempdir, '{}_micro.png'.format(key))
                filename_macro = os.path.join(tempdir, '{}_macro.png'.format(key))
                filename_weighted = os.path.join(tempdir, '{}_weighted.png'.format(key))

                # plot score trends
                plot_score_trend(val['micro'], filename=filename_micro, key=key, style=('k', '-'))
                plot_score_trend(val['macro'], filename=filename_macro, key=key, style=('k', '-'))
                plot_score_trend(val['weighted'], filename=filename_weighted, key=key, style=('k', '-'))

                # log files as artifacts
                mlflow.log_artifact(filename_micro, 'contrastive_model_mean_results')
                mlflow.log_artifact(filename_macro, 'contrastive_model_mean_results')
                mlflow.log_artifact(filename_weighted, 'contrastive_model_mean_results')


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
