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
import torch  # tensor library like NumPy, with strong GPU support
from numpy import interp  # one-dimensional linear interpolation for monotonically increasing sample points
from sklearn.metrics import auc  # computes the Area Under the Curve (AUC) using the trapezoidal rule
from sklearn.metrics import confusion_matrix  # computes confusion matrix to evaluate the accuracy of a classification
from sklearn.preprocessing import label_binarize  # applies the boolean thresholding to an array-like matrix

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

score_functions = {
    'accuracy': accuracy_score,
    'precision': precision_score,
    'recall': recall_score,
    'f1_score': f1_score,
    'confusion_matrix': confusion_matrix
}


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
        std_alpha: Standard deviation alpha value (default: .2)
    """

    # if the style was not defined (it is None)
    if style is None:
        raise ValueError('No default style information is available for f-way {} score;'
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
    plt.xlabel('number of anchors')  # set the label for the x-axis
    plt.title("f-way {} results".format(key))  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def plot_confusion_matrix(cm,  # ndarray containing the confusion matrix to plot
                          filename,  # path where to save the generated confusion matrix plot
                          n_anchors,  # number of anchors used
                          families):  # list of families of interest
    """ Plot and save to file a figure containing the confusion matrix passed as input.

    Args:
        cm: Ndarray containing the confusion matrix to plot
        filename: Path where to save the generated confusion matrix plot
        n_anchors: Number of anchors used
        families: List of families of interest
    """

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    # plot confusion matrix
    im = plt.imshow(cm)

    # get text color thresholds
    threshold = im.norm(cm.max()) / 2
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
            plt.text(j, i, cm[i, j], ha="center", va="center", color=textcolors[int(im.norm(cm[i, j]) > threshold)])

    plt.title("Confusion matrix with {} anchors".format(n_anchors))  # plot figure title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure
    plt.close()


def compute_fresh_scores(predictions_json_path):  # path where to find the json file containing the model predictions
    """ Compute scores for the model when evaluated using the Fresh Dataset on the Family Prediction task.

    Args:
        predictions_json_path: Path where to find the json file containing the model predictions
    """

    # open json file containing the model predictions in read mode
    with open(predictions_json_path, 'r') as infile:
        # load predictions as json object
        predictions = json.load(infile)

    # initialize some variables
    families = None
    scores = {
        'precision': {'macro': {}, 'micro': {}},
        'recall': {'macro': {}, 'micro': {}},
        'f1_score': {'macro': {}, 'micro': {}},
    }
    accuracies = {}
    confusion_matrixes = {}

    # get minimum number of anchors used
    min_n_anchors = np.min([int(n) for n in predictions.keys()])

    # for all predictions
    for n_anchors in predictions.keys():
        # if it is the first cycle
        if families is None:
            # get families of interest from the 'predictions' json object
            families = predictions[n_anchors][0]['families']

        # initialize current scores dictionaries
        curr_accuracy = []
        curr_scores = {
            'precision': {'macro': [], 'micro': []},
            'recall': {'macro': [], 'micro': []},
            'f1_score': {'macro': [], 'micro': []},
        }
        curr_confusion_matrix = []

        # for all predictions with the current number of anchors
        for curr_preds in predictions[n_anchors]:
            # compute the model accuracy and append it to 'curr_accuracy'
            curr_accuracy.append(score_functions['accuracy'](curr_preds['labels'], curr_preds['predictions']))
            # generate model confusion matrix and append it to 'curr_confusion_matrix'
            curr_confusion_matrix.append(score_functions['confusion_matrix'](curr_preds['labels'],
                                                                             curr_preds['predictions']))

            # for each score type in 'curr_scores'
            for key, val in curr_scores.items():
                # compute the model 'macro' averaged score and append it to the respective 'curr_scores' element
                curr_scores[key]['macro'].append(score_functions[key](curr_preds['labels'],
                                                                      curr_preds['predictions'],
                                                                      average='macro',
                                                                      zero_division=0))
                # compute the model 'micro' averaged score and append it to the respective 'curr_scores' element
                curr_scores[key]['micro'].append(score_functions[key](curr_preds['labels'],
                                                                      curr_preds['predictions'],
                                                                      average='micro',
                                                                      zero_division=0))

        # compute the mean and standard deviation accuracy for the current number of anchors
        accuracies[n_anchors] = {
            'mean': float(np.mean(curr_accuracy, dtype=np.float32)),
            'std': float(np.std(curr_accuracy, dtype=np.float32))
        }
        # log accuracy as metric
        mlflow.log_metric('mean_accuracy',
                          float(np.mean(curr_accuracy, dtype=np.float32)),
                          int(n_anchors))

        # save confusion matrixes corresponding to the best and worst evaluations
        confusion_matrixes[n_anchors] = {
            'max': curr_confusion_matrix[torch.argmax(torch.tensor(curr_accuracy))],
            'min': curr_confusion_matrix[torch.argmin(torch.tensor(curr_accuracy))]
        }
        # for all score types in 'curr_scores'
        for key, val in curr_scores.items():
            # compute the mean and standard deviation 'macro' averaged score for the current number of anchors
            scores[key]['macro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['macro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['macro'], dtype=np.float32))
            }
            # log score as metric
            mlflow.log_metric('mean_{}'.format(key),
                              float(np.mean(curr_scores[key]['macro'], dtype=np.float32)),
                              int(n_anchors))

            # compute the mean and standard deviation 'micro' averaged score for the current number of anchors
            scores[key]['micro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['micro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['micro'], dtype=np.float32))
            }
            # log score as metric
            mlflow.log_metric('mean_{}'.format(key),
                              float(np.mean(curr_scores[key]['micro'], dtype=np.float32)),
                              int(n_anchors))

    # create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # create result file path
        acc_filename = os.path.join(tmpdir, 'accuracy.png')
        # plot accuracy score trend to file
        plot_score_trend(accuracies, filename=acc_filename, key='accuracy', style=('k', '-'))
        # log file as artifact
        mlflow.log_artifact(acc_filename, 'fresh_scores_plots')

        # for all score types in 'scores'
        for key, val in scores.items():
            # create result files paths
            filename_macro = os.path.join(tmpdir, '{}_macro.png'.format(key))
            filename_micro = os.path.join(tmpdir, '{}_micro.png'.format(key))

            # plot 'macro' and 'micro' averaged score trends
            plot_score_trend(val['macro'], filename=filename_macro, key=key, style=('k', '-'))
            plot_score_trend(val['micro'], filename=filename_micro, key=key, style=('k', '-'))

            # log files as artifacts
            mlflow.log_artifact(filename_macro, 'fresh_scores_plots')
            mlflow.log_artifact(filename_micro, 'fresh_scores_plots')

        # get the number of anchors which provided the max mean accuracy
        max_mean_accuracy_n_anchors = torch.argmax(
            torch.tensor([a['mean'] for a in accuracies.values()])).item() + min_n_anchors
        # generate confusion matrixes output file paths
        cm_max_filename = os.path.join(tmpdir, 'conf_matrix_max_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))
        cm_min_filename = os.path.join(tmpdir, 'conf_matrix_min_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))

        # plot confusion matrixes to file
        plot_confusion_matrix(confusion_matrixes[str(max_mean_accuracy_n_anchors)]['max'],
                              filename=cm_max_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)
        plot_confusion_matrix(confusion_matrixes[str(max_mean_accuracy_n_anchors)]['min'],
                              filename=cm_min_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)

        # log confusion matrixes files as artifacts
        mlflow.log_artifact(cm_max_filename, 'fresh_scores_plots')
        mlflow.log_artifact(cm_min_filename, 'fresh_scores_plots')


def plot_fresh_results(predictions_json_path):  # path where to find the json file containing the model predictions
    """ Plot 'micro' averaged, 'macro' averaged and per-family AUC score trends resulting from the evaluation of the
    model using the Fresh Dataset on the Family Prediction task.

    Args:
        predictions_json_path: Path where to find the json file containing the model predictions
    """

    # open model predictions json file in read mode
    with open(predictions_json_path, 'r') as infile:
        # read model predictions from file as json object
        predictions = json.load(infile)

    # initialize values dict
    values = {
        'roc_auc': {
            'macro': {},
            'micro': {}
        }
    }

    families = None

    # for all predictions in the 'predictions' json object
    for n_anchors in predictions.keys():
        # if it is the first cycle
        if families is None:
            # get the families of interest from the predictions object
            families = predictions[n_anchors][0]['families']

            # for each family
            for key in families:
                # initialize the corresponding roc auc dict
                values['roc_auc'][key] = {}
                # values['roc'][key] = {}

        # initialize current values dict
        curr_values = {
            'roc_auc': {'micro': [], 'macro': []}
        }

        # initialize current values dict
        curr_values['roc_auc'].update({key: [] for key in families})

        # for all the predictions for the current number of anchors
        for curr_preds in predictions[n_anchors]:

            # binarize the labels for the current prediction
            binarized_labels = label_binarize(curr_preds['labels'], classes=range(len(families)))

            fpr = {}
            tpr = {}
            roc_auc = {}
            # for all families
            for i, fam in enumerate(families):
                # compute roc curve (false positive rates and true positive rates)
                fpr[fam], tpr[fam], _ = roc_curve(binarized_labels[:, i],
                                                  torch.tensor(curr_preds['probabilities'])[:, i])
                # compute AUC score
                roc_auc[fam] = auc(fpr[fam], tpr[fam])

                # append auc score to the 'curr_values' dict
                curr_values['roc_auc'][str(fam)].append(roc_auc[fam])

            # compute micro-average ROC curve and ROC area
            fpr['micro'], tpr["micro"], _ = roc_curve(binarized_labels.ravel(),
                                                      torch.tensor(curr_preds['probabilities']).ravel())
            # compute micro averaged AUC score
            roc_auc['micro'] = auc(fpr["micro"], tpr["micro"])

            # append micro averaged auc score to the 'curr_values' dict
            curr_values['roc_auc']['micro'].append(roc_auc['micro'])

            # get all unique false positive rates
            all_fpr = np.unique(np.concatenate([fpr[fam] for fam in families]))

            # interpolate all ROC curves at these points
            mean_tpr = np.zeros_like(all_fpr)
            for fam in families:
                mean_tpr += interp(all_fpr, fpr[fam], tpr[fam])

            # average the computed true positive rates
            mean_tpr /= len(families)

            # save computed macro averaged roc curve
            fpr["macro"] = all_fpr
            tpr["macro"] = mean_tpr
            # compute macro averaged AUC score
            roc_auc["macro"] = auc(fpr["macro"], tpr["macro"])

            # append macro averaged auc score to the 'curr_values' dict
            curr_values['roc_auc']['macro'].append(roc_auc['macro'])

        # compute the mean and standard deviation of the macro averaged AUC score
        values['roc_auc']['macro'][n_anchors] = {
            'mean': float(np.mean(curr_values['roc_auc']['macro'], dtype=np.float32)),
            'std': float(np.std(curr_values['roc_auc']['macro'], dtype=np.float32))
        }
        # log macro averaged AUC score as metric
        mlflow.log_metric('mean_roc_auc_macro',
                          float(np.mean(curr_values['roc_auc']['macro'], dtype=np.float32)),
                          int(n_anchors))

        # compute the mean and standard deviation of the micro averaged AUC score
        values['roc_auc']['micro'][n_anchors] = {
            'mean': float(np.mean(curr_values['roc_auc']['micro'], dtype=np.float32)),
            'std': float(np.std(curr_values['roc_auc']['micro'], dtype=np.float32))
        }
        # log micro averaged AUC score as metric
        mlflow.log_metric('mean_roc_auc_micro',
                          float(np.mean(curr_values['roc_auc']['micro'], dtype=np.float32)),
                          int(n_anchors))

        # for all families
        for key in families:
            # compute the AUC score for the current family
            values['roc_auc'][key][n_anchors] = {
                'mean': float(np.mean(curr_values['roc_auc'][key], dtype=np.float32)),
                'std': float(np.std(curr_values['roc_auc'][key], dtype=np.float32))
            }
            # log AUC score as metric
            mlflow.log_metric('mean_roc_auc_{}'.format(key),
                              float(np.mean(curr_values['roc_auc'][key], dtype=np.float32)),
                              int(n_anchors))

    # create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # create result file paths
        auc_macro_filename = os.path.join(tmpdir, 'auc_roc_macro.png')
        auc_micro_filename = os.path.join(tmpdir, 'auc_roc_micro.png')

        # plot micro and macro AUC score trends
        plot_score_trend(values['roc_auc']['macro'], filename=auc_macro_filename, key='auc-roc_macro', style=('k', '-'))
        plot_score_trend(values['roc_auc']['micro'], filename=auc_micro_filename, key='auc-roc_micro', style=('k', '-'))

        # log files as artifacts
        mlflow.log_artifact(auc_macro_filename, 'fresh_scores_plots')
        mlflow.log_artifact(auc_micro_filename, 'fresh_scores_plots')

        # for all families
        for fam in families:
            # create result file path
            auc_f_filename = os.path.join(tmpdir, 'auc_roc_{}.png'.format(fam))

            # plot per family AUC score trend
            plot_score_trend(values['roc_auc'][fam], filename=auc_f_filename, key='auc-roc_{}'.format(fam),
                             style=('k', '-'))

            # log file as artifact
            mlflow.log_artifact(auc_f_filename, 'fresh_scores_plots')


@baker.command
def compute_all_fresh_results(results_file):  # path of the json file where to find the model results
    """ Compute model results on the family prediction task.

    Args:
        results_file: Path of the json file where to find the model results
    """

    # start mlflow run
    with mlflow.start_run():
        # compute fresh scores
        compute_fresh_scores(predictions_json_path=results_file)

        # plot fresh score trends
        plot_fresh_results(predictions_json_path=results_file)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
