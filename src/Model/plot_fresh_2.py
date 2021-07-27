import json
import os
import tempfile

import baker
import mlflow
import numpy as np
import torch
from matplotlib import pyplot as plt
from numpy import interp
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.metrics import roc_curve, auc
from sklearn.preprocessing import label_binarize

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


score_functions = {
    'accuracy': accuracy_score,
    'precision': precision_score,
    'recall': recall_score,
    'f1_score': f1_score,
    'confusion_matrix': confusion_matrix
}


def plot_score_trend(values_dict,
                     filename,
                     key,
                     style,
                     std_alpha=.2):

    # if the style was not defined (it is None)
    if style is None:
        raise ValueError('No default style information is available for f-way {} score;'
                         ' please provide (linestyle, color)'.format(key))
    else:  # otherwise (the style was defined)
        color, linestyle = style  # get linestyle and color from style

    x = np.array([k for k in values_dict.keys()])
    y_mean = np.array([v['mean'] for v in values_dict.values()])
    y_std = np.array([v['std'] for v in values_dict.values()])

    # create a new figure of size 12 x 12
    plt.figure(figsize=(12, 12))

    plt.plot(x, y_mean, color + linestyle, linewidth=2.0)

    # fill uncertainty area around ROC curve
    plt.fill_between(x,
                     y_mean - y_std,
                     y_mean + y_std,
                     color=color,
                     alpha=std_alpha)

    plt.legend()  # place legend on the axes
    plt.xlabel(key)  # set the label for the x-axis
    plt.ylabel('number of anchors')  # set the label for the y-axis
    plt.title("f-way {} results".format(key))  # set plot title
    plt.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def plot_confusion_matrix(cm,
                          filename,
                          n_anchors,
                          families):

    fig, ax = plt.subplots()
    im = ax.imshow(cm)

    threshold = im.norm(cm.max()) / 2
    textcolors = ("black", "white")

    # We want to show all ticks...
    ax.set_xticks(np.arange(len(families)))
    ax.set_yticks(np.arange(len(families)))
    # ... and label them with the respective list entries
    ax.set_xticklabels(families)
    ax.set_yticklabels(families)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right",
             rotation_mode="anchor")

    # Loop over data dimensions and create text annotations.
    for i in range(len(families)):
        for j in range(len(families)):
            text = ax.text(j, i, cm[i, j],
                           ha="center", va="center", color=textcolors[int(im.norm(cm[i, j]) > threshold)])

    ax.set_title("Confusion matrix with {} anchors".format(n_anchors))
    fig.tight_layout(pad=0.5)
    plt.savefig(filename)  # save the current figure to file
    plt.clf()  # clear the current figure


def compute_fresh_scores(predictions_json_path):
    with open(predictions_json_path, 'r') as infile:
        predictions = json.load(infile)

    families = None
    scores = {'macro': {}, 'micro': {}}
    accuracies = {}
    confusion_matrixes = {}
    for n_anchors in predictions.keys():
        if families is None:
            families = predictions[n_anchors][0]['families']

        curr_accuracy = []
        curr_scores = {
            'precision': {'macro': [], 'micro': []},
            'recall': {'macro': [], 'micro': []},
            'f1_score': {'macro': [], 'micro': []},
        }
        curr_confusion_matrix = []

        for curr_preds in predictions[n_anchors]:
            for key, val in curr_scores.items():
                if key == 'accuracy':
                    curr_accuracy.append(score_functions[key](curr_preds['labels'], curr_preds['predictions']))
                if key == 'confusion_matrix':
                    curr_confusion_matrix.append(score_functions[key](curr_preds['labels'], curr_preds['predictions']))
                else:
                    curr_scores[key]['macro'].append(score_functions[key](curr_preds['labels'],
                                                                          curr_preds['predictions'], average='macro'))
                    curr_scores[key]['micro'].append(score_functions[key](curr_preds['labels'],
                                                                          curr_preds['predictions'], average='micro'))

        accuracies[n_anchors] = {
            'mean': float(np.mean(curr_accuracy, dtype=np.float32)),
            'std': float(np.std(curr_accuracy, dtype=np.float32))
        }
        confusion_matrixes[n_anchors] = {
            'max': curr_confusion_matrix[torch.argmax(torch.tensor(curr_accuracy))],
            'min': curr_confusion_matrix[torch.argmin(torch.tensor(curr_accuracy))]
        }
        for key, val in curr_scores.items():
            scores['macro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['macro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['macro'], dtype=np.float32))
            }
            scores['micro'][n_anchors] = {
                'mean': float(np.mean(curr_scores[key]['micro'], dtype=np.float32)),
                'std': float(np.std(curr_scores[key]['micro'], dtype=np.float32))
            }

    with tempfile.TemporaryDirectory() as tmpdir:
        acc_filename = os.path.join(tmpdir, 'accuracy.png')
        plot_score_trend(accuracies, filename=acc_filename, key='accuracy', style=('k', '-'))
        mlflow.log_artifact(acc_filename, 'fresh_scores_plots')

        for key, val in scores.items():
            filename_macro = os.path.join(tmpdir, '{}_macro.png'.format(key))
            filename_micro = os.path.join(tmpdir, '{}_micro.png'.format(key))

            plot_score_trend(val['macro'], filename=filename_macro, key=key, style=('k', '-'))
            plot_score_trend(val['micro'], filename=filename_micro, key=key, style=('k', '-'))

            mlflow.log_artifact(filename_macro, 'fresh_scores_plots')
            mlflow.log_artifact(filename_micro, 'fresh_scores_plots')

        max_mean_accuracy_n_anchors = torch.argmax(torch.tensor([a['mean'] for a in accuracies]))
        cm_max_filename = os.path.join(tmpdir, 'conf_matrix_max_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))
        cm_min_filename = os.path.join(tmpdir, 'conf_matrix_min_acc_anchors_{}.png'.format(max_mean_accuracy_n_anchors))

        plot_confusion_matrix(confusion_matrixes[max_mean_accuracy_n_anchors]['max'],
                              filename=cm_max_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)
        plot_confusion_matrix(confusion_matrixes[max_mean_accuracy_n_anchors]['min'],
                              filename=cm_min_filename,
                              n_anchors=max_mean_accuracy_n_anchors,
                              families=families)

        mlflow.log_artifact(cm_max_filename, 'fresh_scores_plots')
        mlflow.log_artifact(cm_min_filename, 'fresh_scores_plots')


def get_mean_tprs(fpr_values,
                  tpr_values):

    all_fpr = np.unique(np.concatenate([fpr for fpr in fpr_values]))
    # Then interpolate all ROC curves at this points
    mean_tpr = np.zeros_like(all_fpr)
    for j in range(len(fpr_values)):
        mean_tpr += interp(all_fpr, fpr_values[j], tpr_values[j])
    # Finally average it and compute AUC
    mean_tpr /= len(fpr_values)

    return all_fpr, mean_tpr


def plot_fresh_results(predictions_json_path):
    with open(predictions_json_path, 'r') as infile:
        predictions = json.load(infile)

    values = {'roc_auc': {}}
    families = None
    for n_anchors in predictions.keys():
        if families is None:
            families = predictions[n_anchors][0]['families']

        curr_values = {
            'fpr': {'micro': [], 'macro': []},
            'tpr': {'micro': [], 'macro': []},
            'roc_auc': {'micro': [], 'macro': []}
        }
        curr_values['fpr'].update({key: [] for key in families})
        curr_values['tpr'].update({key: [] for key in families})
        curr_values['roc_auc'].update({key: [] for key in families})

        for curr_preds in predictions[n_anchors]:

            binarized_labels = label_binarize(curr_preds['labels'], classes=range(len(families)))

            fpr = {}
            tpr = {}
            roc_auc = {}
            for fam in families:
                fpr[fam], tpr[fam], _ = roc_curve(binarized_labels[:, fam], curr_preds['probabilities'][:, fam])
                roc_auc[fam] = auc(fpr[fam], tpr[fam])

                curr_values['fpr'][str(fam)].append(fpr[fam])
                curr_values['tpr'][str(fam)].append(fpr[fam])
                curr_values['roc_auc'][str(fam)].append(fpr[fam])

            # Compute micro-average ROC curve and ROC area
            fpr['micro'], tpr["micro"], _ = roc_curve(binarized_labels.ravel(), curr_preds['probabilities'].ravel())
            roc_auc['micro'] = auc(fpr["micro"], tpr["micro"])

            curr_values['fpr']['micro'].append(fpr['micro'])
            curr_values['tpr']['micro'].append(fpr['micro'])
            curr_values['roc_auc']['micro'].append(fpr['micro'])

            all_fpr = np.unique(np.concatenate([fpr[fam] for fam in families]))

            # Then interpolate all ROC curves at this points
            mean_tpr = np.zeros_like(all_fpr)
            for fam in families:
                mean_tpr += interp(all_fpr, fpr[fam], tpr[fam])

            # Finally average it and compute AUC
            mean_tpr /= len(families)

            fpr["macro"] = all_fpr
            tpr["macro"] = mean_tpr
            roc_auc["macro"] = auc(fpr["macro"], tpr["macro"])

            curr_values['fpr']['macro'].append(fpr['macro'])
            curr_values['tpr']['macro'].append(fpr['macro'])
            curr_values['roc_auc']['macro'].append(fpr['macro'])

        values['roc_auc']['macro'][n_anchors] = {
            'mean': np.mean(curr_values['roc_auc']['macro'], dtype=np.float32),
            'std': np.std(curr_values['roc_auc']['macro'], dtype=np.float32)
        }
        values['roc_auc']['micro'][n_anchors] = {
            'mean': np.mean(curr_values['roc_auc']['micro'], dtype=np.float32),
            'std': np.std(curr_values['roc_auc']['micro'], dtype=np.float32)
        }

        all_macro_fpr, mean_macro_tpr = get_mean_tprs(curr_values['fpr']['macro'], curr_values['tpr']['macro'])
        values['roc']['macro'][n_anchors] = {
            'fpr': all_macro_fpr,
            'tpr': mean_macro_tpr
        }

        all_micro_fpr, mean_micro_tpr = get_mean_tprs(curr_values['fpr']['micro'], curr_values['tpr']['micro'])
        values['roc']['micro'][n_anchors] = {
            'fpr': all_micro_fpr,
            'tpr': mean_micro_tpr
        }

        for key in families:
            values['roc_auc'][key][n_anchors] = {
                'mean': np.mean(curr_values['roc_auc'][key], dtype=np.float32),
                'std': np.std(curr_values['roc_auc'][key], dtype=np.float32)
            }

            all_f_fpr, mean_f_tpr = get_mean_tprs(curr_values['fpr'][key], curr_values['tpr'][key])
            values['roc'][key][n_anchors] = {
                'fpr': all_f_fpr,
                'tpr': mean_f_tpr
            }

    with tempfile.TemporaryDirectory() as tmpdir:
        auc_macro_filename = os.path.join(tmpdir, 'auc_roc_macro.png')
        auc_micro_filename = os.path.join(tmpdir, 'auc_roc_micro.png')
        plot_score_trend(values['roc_auc']['macro'], filename=auc_macro_filename, key='auc-roc_macro', style=('k', '-'))
        plot_score_trend(values['roc_auc']['micro'], filename=auc_micro_filename, key='auc-roc_micro', style=('k', '-'))

        mlflow.log_artifact(auc_macro_filename, 'fresh_scores_plots')
        mlflow.log_artifact(auc_micro_filename, 'fresh_scores_plots')

        for fam in families:
            auc_f_filename = os.path.join(tmpdir, 'auc_roc_{}.png'.format(fam))
            plot_score_trend(values['roc_auc'][fam], filename=auc_f_filename, key='auc-roc_{}'.format(fam),
                             style=('k', '-'))

            mlflow.log_artifact(auc_f_filename, 'fresh_scores_plots')


@baker.command
def compute_all_fresh_results(results_file):
    # start mlflow run
    with mlflow.start_run():
        compute_fresh_scores(predictions_json_path=results_file)

        plot_fresh_results(predictions_json_path=results_file)


if __name__ == '__main__':
    # start baker in order to make it possible to run the script and use function names and parameters
    # as the command line interface, using ``optparse``-style options
    baker.run()
