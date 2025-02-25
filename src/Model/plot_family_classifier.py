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

import os  # provides a portable way of using operating system dependent functionality
import tempfile  # used to create temporary files and directories

import baker  # easy, powerful access to Python functions from the command line
import matplotlib  # comprehensive library for creating static, animated, and interactive visualizations in Python
import mlflow  # open source platform for managing the end-to-end machine learning lifecycle
import numpy as np  # the fundamental package for scientific computing with Python
import pandas as pd  # pandas is a flexible and easy to use open source data analysis and manipulation tool
from matplotlib import pyplot as plt  # state-based interface to matplotlib, provides a MATLAB-like way of plotting
from sklearn.metrics import confusion_matrix  # computes confusion matrix to evaluate the accuracy of a classification
from sklearn.metrics import f1_score  # computes the f1 score
from sklearn.metrics import jaccard_score  # computes the Jaccard similarity coefficient score
from sklearn.metrics import precision_score  # computes the precision score
from sklearn.metrics import recall_score  # computes the recall score
from sklearn.metrics import roc_auc_score  # compute the AUC-ROC score from prediction scores

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


def compute_scores(results_file,  # complete path to results.csv which contains the output of a model run
                   dest_file,  # the filename to save the resulting figure to
                   families,  # list of families of interest
                   zero_division=1.0):  # sets the value to return when there is a zero division
    """ Estimate some micro, macro and weighted averaged Score values (jaccard similarity, recall, precision, f1 score)
    and the macro and weighted averaged OVO (Ove Vs One) and OVR (One Vs Rest) AUC-ROC scores for a
    dataframe/key combination.

    Args:
        results_file: Complete path to a results.csv file that contains the output of a model run
        dest_file: The filename to save the resulting figure to
        families: List of families of interest
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised (default: 1.0)
    """

    # create run ID - filename correspondence dictionary (containing just one result file)
    id_to_resultfile_dict = {'run': results_file}

    # read csv result file and obtain a run ID - result dataframe dictionary
    id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

    # get ground truth labels
    y_true = id_to_dataframe_dict['run']['label']
    # get model predictions
    y_pred = id_to_dataframe_dict['run']['preds']
    # get model probabilities (per family)
    y_proba = np.array([id_to_dataframe_dict['run']['proba_{}'.format(fam)] for fam in families]).T

    # compute scores
    scores_df = pd.DataFrame({'jaccard': [jaccard_score(y_true, y_pred, average='micro', zero_division=zero_division),
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
                                     f1_score(y_true, y_pred, average='weighted', zero_division=zero_division)],
                              'auc-roc-ovo': [np.nan,
                                              roc_auc_score(y_true, y_proba, average='macro', multi_class='ovo'),
                                              roc_auc_score(y_true, y_proba, average='weighted', multi_class='ovo')],
                              'auc-roc-ovr': [np.nan,
                                              roc_auc_score(y_true, y_proba, average='macro', multi_class='ovr'),
                                              roc_auc_score(y_true, y_proba, average='weighted', multi_class='ovr')]},
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


def create_confusion_matrix(results_file,  # complete path to results.csv which contains the output of a model run
                            families):  # list of families of interest
    """ Generate confusion matrix for a dataframe/key combination.

    Args:
        results_file: Complete path to a results.csv file that contains the output of a model run.
        families: List of families of interest
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # create output file path
        output_filename = os.path.join(tempdir, "confusion_matrix.png")

        # create run ID - filename correspondence dictionary (containing just one result file)
        id_to_resultfile_dict = {'run': results_file}

        # read csv result file and obtain a run ID - result dataframe dictionary
        id_to_dataframe_dict = collect_dataframes(id_to_resultfile_dict)

        # get ground truth labels
        y_true = id_to_dataframe_dict['run']['label']
        # get model predictions
        y_pred = id_to_dataframe_dict['run']['preds']

        # create confusion matrix
        conf_mtx = confusion_matrix(y_true, y_pred)
        # plot confusion matrix
        plot_confusion_matrix(conf_mtx, output_filename, families)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "family_classifier_scores")


def compute_run_scores(results_file,  # path to results.csv containing the output of a model run
                       families,  # families (list) to extract results for
                       zero_division=1.0):  # sets the value to return when there is a zero division
    """ Compute multi-class classification scores.

    Args:
        results_file: Path to results.csv containing the output of a model run
        families: Families (list) to extract results for
        zero_division: Sets the value to return when there is a zero division (default: 1.0)
    """

    # crete temporary directory
    with tempfile.TemporaryDirectory() as tempdir:
        # create output file path
        output_filename = os.path.join(tempdir, "classifier_scores.csv")

        # compute multi-class classification scores
        compute_scores(results_file=results_file,
                       dest_file=output_filename,
                       families=families,
                       zero_division=zero_division)

        # log output file as artifact
        mlflow.log_artifact(output_filename, "family_classifier_scores")


@baker.command
def compute_all_family_class_results(results_file,  # path to results.csv containing the output of a model run
                                     fresh_ds_path,  # fresh dataset root directory (where to find .dat files)
                                     zero_division=1.0):  # sets the value to return when there is a zero division
    """ Take a family classifier result file and produce multi-class classification scores and confusion matrix.

    Args:
        results_file: Path to results.csv containing the output of a model run
        fresh_ds_path: Fresh dataset root directory (where to find .dat files)
        zero_division: Sets the value to return when there is a zero division. If set to “warn”, this acts as 0,
                       but warnings are also raised (default: 1.0)
    """

    # start mlflow run
    with mlflow.start_run():
        # get some fresh_dataset related variables
        all_families, n_families = get_fresh_dataset_info(ds_path=fresh_ds_path)

        # compute all run scores
        compute_run_scores(results_file=results_file,
                           families=all_families,
                           zero_division=zero_division)

        # generate confusion matrix
        create_confusion_matrix(results_file=results_file,
                                families=all_families)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
